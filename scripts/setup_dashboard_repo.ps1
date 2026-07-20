[CmdletBinding()]
param(
    [string]$DashboardPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedRemote = "https://github.com/tklim/fund-signal-dashboard.git"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($DashboardPath)) {
    $DashboardPath = Join-Path $repoRoot "dashboard"
}
$DashboardPath = [System.IO.Path]::GetFullPath($DashboardPath)

function Invoke-Git {
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

if (Test-Path -LiteralPath $DashboardPath) {
    $item = Get-Item -LiteralPath $DashboardPath
    if (-not $item.PSIsContainer) {
        throw "Dashboard path exists but is not a directory: $DashboardPath"
    }

    $topLevel = (Invoke-Git @("-C", $DashboardPath, "rev-parse", "--show-toplevel") | Select-Object -First 1).Trim()
    if ([System.IO.Path]::GetFullPath($topLevel) -ne $DashboardPath) {
        throw "Dashboard path is not an independent Git repository: $DashboardPath"
    }

    $actualRemote = (Invoke-Git @("-C", $DashboardPath, "remote", "get-url", "origin") | Select-Object -First 1).Trim()
    if (-not [string]::Equals($actualRemote, $expectedRemote, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected dashboard origin. Expected '$expectedRemote' but found '$actualRemote'."
    }

    Write-Host "Dashboard repository is correctly configured at $DashboardPath"
    exit 0
}

$parentPath = Split-Path -Parent $DashboardPath
if (-not (Test-Path -LiteralPath $parentPath)) {
    throw "Dashboard parent directory does not exist: $parentPath"
}

Invoke-Git @(
    "clone",
    "--origin", "origin",
    "--branch", "main",
    "--single-branch",
    $expectedRemote,
    $DashboardPath
) | ForEach-Object { Write-Host $_ }

$clonedRemote = (Invoke-Git @("-C", $DashboardPath, "remote", "get-url", "origin") | Select-Object -First 1).Trim()
if (-not [string]::Equals($clonedRemote, $expectedRemote, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Cloned dashboard origin did not match the expected remote."
}

Write-Host "Dashboard repository cloned to $DashboardPath"
