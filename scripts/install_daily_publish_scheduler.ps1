[CmdletBinding()]
param(
    [string]$TaskName = "ManulifeFundDaily",
    [string]$Time = "18:30",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$publisherPath = Join-Path $repoRoot "scripts\publish_daily_dashboard.ps1"
if (-not (Test-Path -LiteralPath $publisherPath -PathType Leaf)) {
    throw "Daily publisher is missing: $publisherPath"
}

try {
    $at = [DateTime]::ParseExact($Time, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "Time must use 24-hour HH:mm format, for example 18:30."
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$publisherPath`""
if ($DryRun) {
    Write-Host "DRY RUN: would replace task '$TaskName' with: powershell.exe $arguments"
    Write-Host "DRY RUN: daily at $Time, interactive current user, IgnoreNew, 72-hour limit, StartWhenAvailable enabled"
    exit 0
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $at
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType InteractiveToken -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 72) -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Installed daily dashboard publisher task '$TaskName' at $Time for $currentUser."
