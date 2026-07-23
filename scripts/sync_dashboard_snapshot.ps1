[CmdletBinding()]
param(
    [switch]$NoPush,
    [string]$ResultPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedRemote = "https://github.com/tklim/fund-signal-dashboard.git"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$dashboardPath = Join-Path $repoRoot "dashboard"
$snapshotRelativePath = "app/fund-data.generated.ts"
$snapshotPath = Join-Path $dashboardPath $snapshotRelativePath
$exporterPath = Join-Path $repoRoot "scripts/export_dashboard_data.py"

function Get-GitOutput {
    param([string[]]$GitArguments)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & git @GitArguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "git $($GitArguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return $output
}

function Invoke-Checked {
    param(
        [string]$Command,
        [string[]]$CommandArguments,
        [string]$WorkingDirectory
    )

    Push-Location $WorkingDirectory
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $Command @CommandArguments
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw "$Command $($CommandArguments -join ' ') failed with exit code $exitCode."
    }
}

function Get-MeaningfulSnapshot {
    param([string]$Content)

    return [regex]::Replace(
        $Content,
        '(?m)^export const snapshotGeneratedAt = .*\r?\n?',
        ''
    )
}

function Get-ChangedPaths {
    $status = Get-GitOutput @("-C", $dashboardPath, "status", "--porcelain=v1", "--untracked-files=all")
    return @(
        $status |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object {
                if ($_.Length -lt 4) {
                    throw "Unexpected Git status entry: $_"
                }
                $_.Substring(3).Trim('"')
            }
    )
}

function Write-SyncResult {
    param([hashtable]$Result)

    $json = $Result | ConvertTo-Json -Compress
    if ($ResultPath) {
        $parent = Split-Path -Parent $ResultPath
        if ($parent) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Set-Content -LiteralPath $ResultPath -Value $json -Encoding utf8
    }
    Write-Output $json
}

if (-not (Test-Path -LiteralPath $dashboardPath -PathType Container)) {
    throw "Dashboard repository is missing. Run scripts/setup_dashboard_repo.ps1 first."
}
if (-not (Test-Path -LiteralPath $exporterPath -PathType Leaf)) {
    throw "Dashboard exporter is missing: $exporterPath"
}
if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
    throw "Dashboard snapshot is missing: $snapshotPath"
}

$topLevel = (Get-GitOutput @("-C", $dashboardPath, "rev-parse", "--show-toplevel") | Select-Object -First 1).Trim()
if ([System.IO.Path]::GetFullPath($topLevel) -ne [System.IO.Path]::GetFullPath($dashboardPath)) {
    throw "Dashboard path is not an independent Git repository."
}

$actualRemote = (Get-GitOutput @("-C", $dashboardPath, "remote", "get-url", "origin") | Select-Object -First 1).Trim()
if (-not [string]::Equals($actualRemote, $expectedRemote, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected dashboard origin. Expected '$expectedRemote' but found '$actualRemote'."
}

$gitDirectory = (Get-GitOutput @("-C", $dashboardPath, "rev-parse", "--absolute-git-dir") | Select-Object -First 1).Trim()
foreach ($operationPath in @("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")) {
    if (Test-Path -LiteralPath (Join-Path $gitDirectory $operationPath)) {
        throw "Dashboard repository has an unfinished Git operation: $operationPath"
    }
}

$initialChanges = @(Get-ChangedPaths)
if ($initialChanges.Count -ne 0) {
    throw "Dashboard repository must be clean before refresh. Changed paths: $($initialChanges -join ', ')"
}

$currentBranch = (Get-GitOutput @("-C", $dashboardPath, "branch", "--show-current") | Select-Object -First 1).Trim()
if ($currentBranch -ne "main") {
    throw "Dashboard must be on main before refresh; current branch is '$currentBranch'."
}

Get-GitOutput @("-C", $dashboardPath, "fetch", "origin", "main") | ForEach-Object { Write-Host $_ }
$localCommit = (Get-GitOutput @("-C", $dashboardPath, "rev-parse", "main") | Select-Object -First 1).Trim()
$remoteCommit = (Get-GitOutput @("-C", $dashboardPath, "rev-parse", "origin/main") | Select-Object -First 1).Trim()
$mergeBase = (Get-GitOutput @("-C", $dashboardPath, "merge-base", "main", "origin/main") | Select-Object -First 1).Trim()

if ($localCommit -ne $remoteCommit) {
    if ($mergeBase -eq $localCommit) {
        Get-GitOutput @("-C", $dashboardPath, "merge", "--ff-only", "origin/main") | ForEach-Object { Write-Host $_ }
    } elseif ($mergeBase -eq $remoteCommit) {
        throw "Local dashboard main is ahead of origin/main. Publish or reconcile it before refreshing."
    } else {
        throw "Dashboard main has diverged from origin/main. Reconcile it before refreshing."
    }
}

$refreshBranch = "codex/data-refresh-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Get-GitOutput @("-C", $dashboardPath, "switch", "-c", $refreshBranch, "origin/main") | ForEach-Object { Write-Host $_ }

$beforeSnapshot = Get-Content -Raw -LiteralPath $snapshotPath
Invoke-Checked -Command "python" -CommandArguments @($exporterPath) -WorkingDirectory $repoRoot
$afterSnapshot = Get-Content -Raw -LiteralPath $snapshotPath

if ((Get-MeaningfulSnapshot $beforeSnapshot) -eq (Get-MeaningfulSnapshot $afterSnapshot)) {
    Get-GitOutput @("-C", $dashboardPath, "restore", "--", $snapshotRelativePath) | Out-Null
    Get-GitOutput @("-C", $dashboardPath, "switch", "main") | Out-Null
    Get-GitOutput @("-C", $dashboardPath, "branch", "-D", $refreshBranch) | Out-Null
    Write-Host "Dashboard data is unchanged; no branch or commit was kept."
    Write-SyncResult @{
        status = "unchanged"
        branch = $null
        snapshot_commit = $null
        compare_url = $null
        source_commit = (Get-GitOutput @("-C", $repoRoot, "rev-parse", "--short", "HEAD") | Select-Object -First 1).Trim()
    }
    return
}

$changedPaths = @(Get-ChangedPaths)
if ($changedPaths.Count -ne 1 -or $changedPaths[0] -ne $snapshotRelativePath) {
    throw "Refresh changed unexpected dashboard paths: $($changedPaths -join ', ')"
}

$npmCommand = if (Get-Command "npm.cmd" -ErrorAction SilentlyContinue) { "npm.cmd" } else { "npm" }
Invoke-Checked -Command $npmCommand -CommandArguments @("run", "build") -WorkingDirectory $dashboardPath
Invoke-Checked -Command "node" -CommandArguments @("--test", "tests/rendered-html.test.mjs") -WorkingDirectory $dashboardPath

$postValidationPaths = @(Get-ChangedPaths)
if ($postValidationPaths.Count -ne 1 -or $postValidationPaths[0] -ne $snapshotRelativePath) {
    throw "Validation changed unexpected dashboard paths: $($postValidationPaths -join ', ')"
}

Get-GitOutput @("-C", $dashboardPath, "add", "--", $snapshotRelativePath) | Out-Null
$stagedPaths = @(
    Get-GitOutput @("-C", $dashboardPath, "diff", "--cached", "--name-only") |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
)
if ($stagedPaths.Count -ne 1 -or $stagedPaths[0].Trim() -ne $snapshotRelativePath) {
    throw "Refusing to commit unexpected staged paths: $($stagedPaths -join ', ')"
}

$sourceCommit = (Get-GitOutput @("-C", $repoRoot, "rev-parse", "--short", "HEAD") | Select-Object -First 1).Trim()
$sourceState = if (@(Get-GitOutput @("-C", $repoRoot, "status", "--porcelain=v1")).Count -gt 0) { "dirty" } else { "clean" }
$snapshotDate = Get-Date -Format "yyyy-MM-dd"
Get-GitOutput @(
    "-C", $dashboardPath,
    "commit",
    "-m", "Refresh dashboard snapshot $snapshotDate",
    "-m", "Source mlfund: $sourceCommit ($sourceState)"
) | ForEach-Object { Write-Host $_ }

$snapshotCommit = (Get-GitOutput @("-C", $dashboardPath, "rev-parse", "HEAD") | Select-Object -First 1).Trim()
$encodedBranch = [System.Uri]::EscapeDataString($refreshBranch)
$pullRequestUrl = "https://github.com/tklim/fund-signal-dashboard/compare/main...${encodedBranch}?expand=1"

if ($NoPush) {
    Write-Host "Snapshot committed locally on $refreshBranch. Push was skipped."
    Write-SyncResult @{
        status = "changed_not_pushed"
        branch = $refreshBranch
        snapshot_commit = $snapshotCommit
        compare_url = $pullRequestUrl
        source_commit = $sourceCommit
    }
    return
}

Get-GitOutput @("-C", $dashboardPath, "push", "--set-upstream", "origin", $refreshBranch) | ForEach-Object { Write-Host $_ }
Write-Host "Snapshot branch pushed. Open the pull request:"
Write-Host $pullRequestUrl
Write-SyncResult @{
    status = "changed"
    branch = $refreshBranch
    snapshot_commit = $snapshotCommit
    compare_url = $pullRequestUrl
    source_commit = $sourceCommit
}
