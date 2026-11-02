# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Parse the deployment scripts without executing them. Use this locally or in
# CI to catch syntax errors before a release.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$files = @(
    (Join-Path $root "deploy/windows/Update-3DSC.ps1"),
    (Join-Path $root "deploy/windows/Register-UpdateTask.ps1")
)

$failed = $false
foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path -LiteralPath $file),
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null

    if ($errors.Count -gt 0) {
        Write-Host "PowerShell parse errors in ${file}:"
        $errors | ForEach-Object { Write-Host "  $($_.Message)" }
        $failed = $true
    } else {
        Write-Host "OK: $file"
    }
}

if ($failed) {
    exit 1
}
