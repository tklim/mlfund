param(
    [switch]$SkipBacktest,
    [switch]$RunFinalBacktest,
    [string[]]$BacktestExtraArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backtestRunner = Join-Path $repoRoot "run.ps1"
$strategyReview = Join-Path $repoRoot "scripts\fund_strategy_review.py"
$finalBacktest = Join-Path $repoRoot "scripts\final_backtest_from_summary.py"

Push-Location $repoRoot
try {
    if (-not $SkipBacktest) {
        if (-not (Test-Path $backtestRunner)) {
            throw "Backtest runner not found: $backtestRunner"
        }
        Write-Host "Running weekly strategy backtest refresh"
        & $backtestRunner -ExtraArgs $BacktestExtraArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Weekly backtest refresh failed with exit code $LASTEXITCODE"
        }
    }

    if (-not (Test-Path $strategyReview)) {
        throw "Strategy review script not found: $strategyReview"
    }
    Write-Host "Generating strategy review dashboard"
    & python $strategyReview
    if ($LASTEXITCODE -ne 0) {
        throw "Strategy review failed with exit code $LASTEXITCODE"
    }

    if ($RunFinalBacktest) {
        if (-not (Test-Path $finalBacktest)) {
            throw "Final backtest script not found: $finalBacktest"
        }
        Write-Host "Generating final fixed-parameter backtest charts"
        & python $finalBacktest
        if ($LASTEXITCODE -ne 0) {
            throw "Final backtest failed with exit code $LASTEXITCODE"
        }
    }
}
finally {
    Pop-Location
}
