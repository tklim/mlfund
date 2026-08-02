[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$appRoot = Join-Path $repoRoot "backtest-dashboard"
$siteRoot = Join-Path $appRoot "site"
$exporter = Join-Path $PSScriptRoot "export_backtest_dashboard_data.py"
$allowedPrefixes = @("backtest-dashboard/site/")

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

& python -m unittest tests.test_export_backtest_dashboard_data tests.test_static_backtest_dashboard
if ($LASTEXITCODE -ne 0) { throw "Standalone dashboard tests failed." }

Write-Host "Backtest dashboard snapshot refreshed and validated."
Write-Host "Open locally: $([System.IO.Path]::GetFullPath((Join-Path $siteRoot 'index.html')))"
