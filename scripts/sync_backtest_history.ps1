[CmdletBinding()]
param(
    [string]$Message = 'Sync backtest sources and run history'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (git rev-parse --show-toplevel).Trim()
if (-not $repoRoot) {
    throw 'Run this script from inside the mlfund Git repository.'
}
Set-Location $repoRoot

& "$PSScriptRoot\setup_git_sync.ps1"
$history = 'outputs/tunings/backtest_run_history.csv'
$syncPaths = @(
    '.gitignore'
    'GITHUB_SYNC.md'
    '*.sh'
    'scripts/backtest-ema-ga10-index.py'
    'scripts/merge_backtest_run_history.py'
    'scripts/setup_git_sync.ps1'
    'scripts/sync_backtest_history.ps1'
    $history
)

# Refuse to pull over unrelated working-tree edits. This preserves work from
# either machine; commit, stash, or resolve those edits separately first.
$otherChanges = @(
    git status --porcelain=v1 --untracked-files=all |
        Where-Object {
            $path = if ($_.Length -ge 4) { $_.Substring(3) } else { $_ }
            ($path -notlike '*.sh') -and ($path -notin @(
                '.gitignore',
                'GITHUB_SYNC.md',
                'scripts/backtest-ema-ga10-index.py',
                'scripts/merge_backtest_run_history.py',
                'scripts/setup_git_sync.ps1',
                'scripts/sync_backtest_history.ps1',
                $history
            ))
        }
)
if ($otherChanges.Count -gt 0) {
    Write-Error "Refusing to sync over unrelated working-tree changes. Preserve them first, then rerun.\n$($otherChanges -join "`n")"
}

git add -- $syncPaths
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m $Message
}

# A normal merge (not --ff-only) activates the row-union driver if both
# machines appended records since their common ancestor.
git pull --no-rebase
git push
