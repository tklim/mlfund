[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$appRoot = Join-Path $repoRoot "backtest-dashboard"
$exporter = Join-Path $PSScriptRoot "export_backtest_dashboard_data.py"
$allowedPrefixes = @(
    "backtest-dashboard/app/backtest-data.generated.ts",
    "backtest-dashboard/public/backtests/"
)

function Get-ChangedPaths {
    return @(
        & git -C $repoRoot status --porcelain=v1 --untracked-files=all |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_.Substring(3).Replace("\", "/") }
    )
}

if (-not (Test-Path -LiteralPath $appRoot -PathType Container)) {
    throw "Standalone backtest dashboard is missing: $appRoot"
}

$before = @(Get-ChangedPaths)
& python $exporter
if ($LASTEXITCODE -ne 0) { throw "Backtest dashboard export failed." }

$after = @(Get-ChangedPaths)
$newPaths = @($after | Where-Object { $_ -notin $before })
$unexpected = @($newPaths | Where-Object {
    $path = $_
    -not ($allowedPrefixes | Where-Object { $path -eq $_ -or $path.StartsWith($_) })
})
if ($unexpected.Count -gt 0) {
    throw "Refresh changed unexpected paths: $($unexpected -join ', ')"
}

Push-Location $appRoot
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Standalone dashboard build failed." }
    & node --test tests/rendered-html.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "Standalone dashboard tests failed." }
} finally {
    Pop-Location
}

Write-Host "Backtest dashboard snapshot refreshed and validated."
