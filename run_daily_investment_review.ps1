param(
    [switch]$SkipDownload,
    [string]$PrimaryHorizon = "6M",
    [double]$UpsideTarget = 0.15,
    [double]$DownsideRisk = -0.08,
    [string[]]$ExtraArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dailyScript = Join-Path $repoRoot "scripts\daily_investment_review.py"

if (-not (Test-Path $dailyScript)) {
    throw "Daily investment review script not found: $dailyScript"
}

$argsList = @(
    $dailyScript,
    "--primary-horizon", $PrimaryHorizon,
    "--upside-target", "$UpsideTarget",
    "--downside-risk", "$DownsideRisk"
)

if ($SkipDownload) {
    $argsList += "--skip-download"
}

$argsList += $ExtraArgs

Write-Host "Running daily investment review"
Write-Host "Command: python $($argsList -join ' ')"

Push-Location $repoRoot
try {
    & python @argsList
    if ($LASTEXITCODE -ne 0) {
        throw "Daily investment review failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
