# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Register (or replace) the scheduled task that runs Update-3DSC.ps1.
#
# Example:
#   powershell -NoProfile -ExecutionPolicy Bypass `
#     -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
#     -Schedule Daily -Time 03:00
#
# For a dedicated account (the helper prompts for its password):
#   powershell -NoProfile -ExecutionPolicy Bypass `
#     -File C:\3DSC\app\deploy\windows\Register-UpdateTask.ps1 `
#     -RunAs "DOMAIN\svc-3dsc" -Schedule Daily -Time 03:00

[CmdletBinding()]
param(
    [string]$TaskName = "3DSC-IceServer-Update",
    [string]$Updater = "",
    [string]$RunAs = "SYSTEM",
    [System.Management.Automation.PSCredential]$Credential,
    [string]$AppDir = "C:\3DSC\app",
    [string]$VenvDir = "C:\3DSC\.venv",
    [string]$ServiceName = "3DSC-IceServer",
    [string]$HealthHost = "127.0.0.1",
    [int]$HealthPort = 10000,
    [string]$TagPattern = "v[0-9]*",
    [switch]$AllowLightweightTags,
    [switch]$RequireSignedTag,
    [ValidateSet("Daily", "Weekly")]
    [string]$Schedule = "Daily",
    [string]$Time = "03:00",
    [ValidateSet(
        "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
    )]
    [string]$Day = "Sunday"
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is not available in Windows PowerShell 2.0 and can be empty in
# some hosts. Resolve the companion updater without relying on it alone.
if (-not $Updater) {
    $scriptDirectory = $PSScriptRoot
    if (-not $scriptDirectory -and $PSCommandPath) {
        $scriptDirectory = Split-Path -Parent $PSCommandPath
    }
    if (-not $scriptDirectory -and $MyInvocation.MyCommand.Path) {
        $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    if (-not $scriptDirectory) {
        throw "Cannot determine the script directory. Pass -Updater explicitly."
    }
    $Updater = Join-Path $scriptDirectory "Update-3DSC.ps1"
}

if (-not (Test-Path -LiteralPath $Updater)) {
    throw "Updater script not found: $Updater"
}

$updaterArgument = @(
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$Updater`"",
    "-AppDir", "`"$AppDir`"",
    "-VenvDir", "`"$VenvDir`"",
    "-ServiceName", "`"$ServiceName`"",
    "-HealthHost", "`"$HealthHost`"",
    "-HealthPort", "$HealthPort",
    "-TagPattern", "`"$TagPattern`""
)
if ($AllowLightweightTags) {
    $updaterArgument += "-AllowLightweightTags"
}
if ($RequireSignedTag) {
    $updaterArgument += "-RequireSignedTag"
}
$updaterArgument = $updaterArgument -join " "

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $updaterArgument

if ($Schedule -eq "Weekly") {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
} else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$registerArgs = @{
    TaskName    = $TaskName
    Action      = $action
    Trigger     = $trigger
    Settings    = $settings
    Description = "Update the 3D Station Calibration Ice server to the newest release tag."
    Force       = $true
}

$builtInAccounts = @("SYSTEM", "NetworkService", "LocalService")
if ($RunAs -in $builtInAccounts) {
    $registerArgs["Principal"] = New-ScheduledTaskPrincipal `
        -UserId $RunAs `
        -LogonType ServiceAccount `
        -RunLevel Highest
    $accountText = $RunAs
} else {
    if (-not $Credential) {
        $Credential = Get-Credential `
            -UserName $RunAs `
            -Message "Password for the scheduled update account"
    }
    if (-not $Credential) {
        throw "No credential was supplied for '$RunAs'."
    }

    $registerArgs["User"] = $Credential.UserName
    $registerArgs["Password"] = $Credential.GetNetworkCredential().Password
    $registerArgs["RunLevel"] = "Highest"
    $accountText = $Credential.UserName
}

Register-ScheduledTask @registerArgs | Out-Null

$scheduleText = if ($Schedule -eq "Weekly") {
    "Weekly on $Day at $Time"
} else {
    "Daily at $Time"
}

Write-Host "Registered scheduled task '$TaskName'."
Write-Host "Updater: $Updater"
Write-Host "Account: $accountText"
Write-Host "Schedule: $scheduleText"
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Status:   Get-ScheduledTaskInfo -TaskName '$TaskName'"
