[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (git rev-parse --show-toplevel).Trim()
if (-not $repoRoot) {
    throw 'Run this script from inside the mlfund Git repository.'
}
Set-Location $repoRoot

# Git attributes are versioned; this local setting tells Git which program to
# invoke when those attributes are encountered during a pull or merge.
git config merge.backtest-run-history.name 'Append-only backtest run-history union'
git config merge.backtest-run-history.driver 'python scripts/merge_backtest_run_history.py %O %A %B'

Write-Host 'Configured the backtest run-history merge driver for this clone.'
