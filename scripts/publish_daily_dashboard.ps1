[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$automationDir = Join-Path $repoRoot "outputs\reports\automation"
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $automationDir "daily-publish-$runStamp.log"
$summaryPath = Join-Path $automationDir "daily-publish-$runStamp.json"
$syncResultPath = Join-Path $automationDir "dashboard-sync-$runStamp.json"
$dashboardRepository = "tklim/fund-signal-dashboard"
$productionUrl = "https://fund-signal-dashboard.ltkiat.workers.dev"
$requiredChecks = @("Build and rendered HTML tests", "Workers Builds: fund-signal-dashboard")
$mutex = $null
$ownsMutex = $false
$transcriptStarted = $false
$stage = "initializing"
$summary = [ordered]@{
    started_at = (Get-Date).ToString("o")
    finished_at = $null
    status = "running"
    stage = $stage
    snapshot_status = $null
    branch = $null
    pull_request = $null
    merge_commit = $null
    dashboard_cleanup = $null
    error = $null
    log_path = $logPath
}

function Write-RunSummary {
    $summary.finished_at = (Get-Date).ToString("o")
    $summary.stage = $stage
    New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
    Set-Content -LiteralPath $summaryPath -Value ($summary | ConvertTo-Json -Depth 5) -Encoding utf8
}

function Invoke-Checked {
    param(
        [string]$Command,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $repoRoot
    )

    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Get-GitHubToken {
    $credentialInput = "protocol=https`nhost=github.com`n`n"
    $credentialLines = $credentialInput | & git credential fill
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub credential lookup failed."
    }
    $tokenLine = $credentialLines | Where-Object { $_ -like "password=*" } | Select-Object -First 1
    if (-not $tokenLine) {
        throw "No GitHub credential is available for automated dashboard publishing."
    }
    return $tokenLine.Substring(9)
}

function Invoke-GitHubApi {
    param(
        [string]$Token,
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $headers = @{
        "User-Agent" = "MLFundDailyPublisher"
        "Authorization" = "Bearer $Token"
        "Accept" = "application/vnd.github+json"
    }
    $parameters = @{
        Method = $Method
        Uri = "https://api.github.com/repos/$dashboardRepository$Path"
        Headers = $headers
    }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = $Body | ConvertTo-Json -Depth 5
    }
    return Invoke-RestMethod @parameters
}

function Wait-ForChecks {
    param(
        [string]$Token,
        [string]$CommitSha,
        [string]$Description
    )

    $deadline = (Get-Date).AddMinutes(30)
    while ((Get-Date) -lt $deadline) {
        $checks = Invoke-GitHubApi -Token $Token -Method "GET" -Path "/commits/$CommitSha/check-runs"
        $runsByName = @{}
        foreach ($run in $checks.check_runs) {
            $runsByName[$run.name] = $run
        }
        $missing = @($requiredChecks | Where-Object { -not $runsByName.ContainsKey($_) })
        $failed = @($requiredChecks | Where-Object {
            $run = $runsByName[$_]
            $run -and $run.status -eq "completed" -and $run.conclusion -ne "success"
        })
        if ($failed.Count -gt 0) {
            throw "$Description failed required checks: $($failed -join ', ')."
        }
        $pending = @($requiredChecks | Where-Object {
            $run = $runsByName[$_]
            -not $run -or $run.status -ne "completed" -or $run.conclusion -ne "success"
        })
        if ($missing.Count -eq 0 -and $pending.Count -eq 0) {
            return
        }
        Start-Sleep -Seconds 15
    }
    throw "Timed out waiting for $Description checks."
}

function Wait-ForMergeablePullRequest {
    param(
        [string]$Token,
        [int]$PullRequestNumber
    )

    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline) {
        $pullRequest = Invoke-GitHubApi -Token $Token -Method "GET" -Path "/pulls/$PullRequestNumber"
        if ($pullRequest.mergeable -eq $true -and $pullRequest.mergeable_state -eq "clean") {
            return $pullRequest
        }
        if ($pullRequest.mergeable -eq $false) {
            throw "Dashboard pull request #$PullRequestNumber is not mergeable."
        }
        Start-Sleep -Seconds 10
    }
    throw "Timed out waiting for dashboard pull request #$PullRequestNumber to become mergeable."
}

function Confirm-ProductionDeployment {
    param(
        [string]$Token,
        [string]$MergeCommit
    )

    Wait-ForChecks -Token $Token -CommitSha $MergeCommit -Description "production deployment"
    $response = Invoke-WebRequest -Uri ("$productionUrl?daily-publish=" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -ne 200) {
        throw "Production dashboard returned HTTP $($response.StatusCode)."
    }
}

function Restore-DashboardMain {
    $dashboardPath = Join-Path $repoRoot "dashboard"
    if (-not (Test-Path -LiteralPath $dashboardPath -PathType Container)) {
        return
    }
    $status = & git -C $dashboardPath status --porcelain=v1 --untracked-files=all
    if ($LASTEXITCODE -ne 0 -or @($status).Count -ne 0) {
        return
    }
    $branch = (& git -C $dashboardPath branch --show-current | Select-Object -First 1).Trim()
    if ($branch -like "codex/data-refresh-*") {
        & git -C $dashboardPath switch main | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $summary.dashboard_cleanup = "switched to main"
        }
    }
}

if ($DryRun) {
    Write-Host "DRY RUN: would run python scripts/operate.py daily"
    Write-Host "DRY RUN: would run scripts/sync_dashboard_snapshot.ps1 and read $syncResultPath"
    Write-Host "DRY RUN: would create, validate, merge, and verify a dashboard snapshot pull request only when data changed"
    exit 0
}

try {
    New-Item -ItemType Directory -Force -Path $automationDir | Out-Null
    $createdNew = $false
    $mutex = New-Object System.Threading.Mutex($false, "MLFundDailyDashboardPublisher", [ref]$createdNew)
    if (-not $createdNew) {
        throw "Another daily dashboard publisher is already running."
    }
    $ownsMutex = $true
    Start-Transcript -Path $logPath -Append | Out-Null
    $transcriptStarted = $true

    $stage = "daily pipeline"
    Invoke-Checked -Command "python" -Arguments @("scripts/operate.py", "daily")

    $stage = "dashboard snapshot"
    Invoke-Checked -Command "powershell.exe" -Arguments @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\sync_dashboard_snapshot.ps1"), "-ResultPath", $syncResultPath
    )
    if (-not (Test-Path -LiteralPath $syncResultPath)) {
        throw "Dashboard snapshot workflow did not write its structured result."
    }
    $syncResult = Get-Content -Raw -LiteralPath $syncResultPath | ConvertFrom-Json
    $summary.snapshot_status = $syncResult.status
    if ($syncResult.status -eq "unchanged") {
        $stage = "complete"
        $summary.status = "unchanged"
        Write-Host "Dashboard data is unchanged; production remains on the current valid release."
        exit 0
    }
    if ($syncResult.status -ne "changed") {
        throw "Unexpected dashboard snapshot status '$($syncResult.status)'."
    }
    $summary.branch = $syncResult.branch

    $stage = "dashboard pull request"
    $token = Get-GitHubToken
    $pullRequest = Invoke-GitHubApi -Token $token -Method "POST" -Path "/pulls" -Body @{
        title = "Refresh dashboard snapshot $(Get-Date -Format 'yyyy-MM-dd')"
        head = $syncResult.branch
        base = "main"
        body = "Automated daily snapshot refresh. Contains only app/fund-data.generated.ts."
    }
    $summary.pull_request = $pullRequest.number

    $stage = "dashboard pull request checks"
    Wait-ForChecks -Token $token -CommitSha $pullRequest.head.sha -Description "dashboard pull request #$($pullRequest.number)"
    $mergeablePullRequest = Wait-ForMergeablePullRequest -Token $token -PullRequestNumber $pullRequest.number

    $stage = "dashboard merge"
    $mergeResult = Invoke-GitHubApi -Token $token -Method "PUT" -Path "/pulls/$($pullRequest.number)/merge" -Body @{
        commit_title = "Publish dashboard snapshot $(Get-Date -Format 'yyyy-MM-dd')"
        sha = $mergeablePullRequest.head.sha
        merge_method = "merge"
    }
    if (-not $mergeResult.merged) {
        throw "Dashboard pull request #$($pullRequest.number) was not merged: $($mergeResult.message)"
    }
    $summary.merge_commit = $mergeResult.sha

    $stage = "production deployment"
    Confirm-ProductionDeployment -Token $token -MergeCommit $mergeResult.sha
    $stage = "complete"
    $summary.status = "published"
    Write-Host "Dashboard snapshot published to Cloudflare production."
}
catch {
    $summary.status = "failed"
    $summary.error = $_.Exception.Message
    Write-Error "Daily dashboard publisher failed during ${stage}: $($summary.error)"
    throw
}
finally {
    Restore-DashboardMain
    Write-RunSummary
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
    if ($mutex -and $ownsMutex) {
        $mutex.ReleaseMutex() | Out-Null
    }
    if ($mutex) { $mutex.Dispose() }
}
