[CmdletBinding()]
param(
    [switch]$SkipRefresh,
    [switch]$NoWait,
    [string]$CommitMessage = "Publish latest backtest dashboard"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$refreshScript = Join-Path $PSScriptRoot "refresh_backtest_dashboard.ps1"
$workflowName = "backtest-dashboard-pages.yml"
$publishPaths = @(
    ".github/workflows/backtest-dashboard-pages.yml",
    "backtest-dashboard",
    "publish_backtest_dashboard.bat",
    "scripts/export_backtest_dashboard_data.py",
    "scripts/generate_buyhold_dashboard_charts.py",
    "scripts/publish_backtest_dashboard_pages.ps1",
    "scripts/refresh_backtest_dashboard.ps1",
    "tests/test_export_backtest_dashboard_data.py",
    "tests/test_static_backtest_dashboard.py"
)

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git -C $repoRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

function Get-GitHubHeaders {
    $credentialInput = "protocol=https`nhost=github.com`n`n"
    $credentialLines = $credentialInput | git credential fill
    if ($LASTEXITCODE -ne 0 -or -not $credentialLines) {
        throw "No GitHub credential is available. Sign in through Git Credential Manager first."
    }
    $credential = @{}
    foreach ($line in $credentialLines) {
        if ($line -match "^(?<key>[^=]+)=(?<value>.*)$") {
            $credential[$Matches.key] = $Matches.value
        }
    }
    if (-not $credential.username -or -not $credential.password) {
        throw "GitHub credential is incomplete. Sign in through Git Credential Manager first."
    }
    $basic = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("$($credential.username):$($credential.password)")
    )
    $credential.password = $null
    return @{
        Authorization = "Basic $basic"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
}

function Get-GitHubRepository {
    $remoteUrl = (& git -C $repoRoot remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or $remoteUrl -notmatch "github\.com[:/](?<repo>[^/]+/[^/]+?)(?:\.git)?$") {
        throw "The origin remote is not a recognizable GitHub repository URL."
    }
    return $Matches.repo
}

Push-Location $repoRoot
try {
    $branch = (& git branch --show-current).Trim()
    if ($branch -ne "main") {
        throw "Publishing must run from main. Current branch: $branch"
    }

    if (-not $SkipRefresh) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $refreshScript
        if ($LASTEXITCODE -ne 0) {
            throw "Dashboard refresh or validation failed."
        }
    }

    Write-Host "Checking GitHub main for concurrent changes..."
    Invoke-Git fetch origin main
    $counts = (& git rev-list --left-right --count "HEAD...origin/main").Trim() -split "\s+"
    if ($counts.Count -ne 2) {
        throw "Unable to compare local and remote main branches."
    }
    $localOnly = [int]$counts[0]
    $remoteOnly = [int]$counts[1]
    if ($remoteOnly -gt 0) {
        throw "origin/main has $remoteOnly newer commit(s). Sync main before publishing; no files were staged or pushed."
    }

    & git add -- @publishPaths
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to stage Backtest Dashboard files."
    }
    $dashboardChanges = @(& git diff --cached --name-only -- @publishPaths)
    if ($dashboardChanges.Count -gt 0) {
        & git commit --only -m $CommitMessage -- @publishPaths
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to commit Backtest Dashboard files."
        }
    } else {
        Write-Host "No new Backtest Dashboard changes to commit. Redeploying the current main snapshot."
    }

    Invoke-Git push origin main
    $headSha = (& git rev-parse HEAD).Trim()
    $repository = Get-GitHubRepository
    $headers = Get-GitHubHeaders
    $dispatchStarted = [DateTimeOffset]::UtcNow.AddMinutes(-1)
    $dispatchBody = @{ ref = "main" } | ConvertTo-Json
    $workflowUri = "https://api.github.com/repos/$repository/actions/workflows/$workflowName"
    Invoke-WebRequest -Method Post -Uri "$workflowUri/dispatches" -Headers $headers -ContentType "application/json" -Body $dispatchBody | Out-Null
    Write-Host "GitHub Pages deployment started."

    if ($NoWait) {
        Write-Host "Deployment was dispatched without waiting for completion."
        exit 0
    }

    $run = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $runs = Invoke-RestMethod -Method Get -Uri "$workflowUri/runs?branch=main&event=workflow_dispatch&per_page=10" -Headers $headers
        $run = $runs.workflow_runs |
            Where-Object { $_.head_sha -eq $headSha -and [DateTimeOffset]$_.created_at -ge $dispatchStarted } |
            Sort-Object created_at -Descending |
            Select-Object -First 1
        if ($run -and $run.status -eq "completed") {
            break
        }
        Start-Sleep -Seconds 6
    }
    if (-not $run -or $run.status -ne "completed") {
        throw "Deployment is still running or could not be located. Check the repository Actions page."
    }
    if ($run.conclusion -ne "success") {
        throw "GitHub Pages deployment failed: $($run.html_url)"
    }
    $pages = Invoke-RestMethod -Method Get -Uri "https://api.github.com/repos/$repository/pages" -Headers $headers
    Write-Host "Published successfully: $($pages.html_url)"
    Write-Host "Local dashboard remains at: $repoRoot\backtest-dashboard\site\index.html"
}
finally {
    Pop-Location
}
