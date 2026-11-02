# SPDX-FileCopyrightText: 2026 Forschungszentrum Jülich GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Update the 3D Station Calibration Ice server to the newest release tag.
#
# The updater:
#   - refuses to run when the Git working tree is dirty,
#   - fetches tags and selects the newest tag matching -TagPattern,
#   - stops the NSSM service,
#   - checks out that tag and reinstalls the package,
#   - starts the service and checks the TCP endpoint,
#   - rolls back to the previous tag/commit when the update fails.
#
# Run it manually with:
#   powershell -NoProfile -ExecutionPolicy Bypass `
#     -File C:\3DSC\app\deploy\windows\Update-3DSC.ps1 -DryRun

[CmdletBinding()]
param(
    [string]$AppDir = "C:\3DSC\app",
    [string]$VenvDir = "C:\3DSC\.venv",
    [string]$ServiceName = "3DSC-IceServer",
    [string]$Remote = "origin",
    [string]$TagPattern = "v[0-9]*",
    [string]$LogFile = "C:\ProgramData\3DSC\logs\update.log",
    [string]$HealthHost = "127.0.0.1",
    [int]$HealthPort = 10000,
    [int]$HealthTimeoutSeconds = 60,
    [switch]$AllowLightweightTags,
    [switch]$RequireSignedTag,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$script:Python = Join-Path $VenvDir "Scripts\python.exe"
$script:ServerExe = Join-Path $VenvDir "Scripts\3dsc-ice-server.exe"
$script:Git = $null


function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")][string]$Level = "INFO"
    )

    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    try {
        Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    } catch {
        Write-Warning "Could not write update log '$LogFile': $($_.Exception.Message)"
    }
}


function Get-GitExe {
    $command = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Git\cmd\git.exe"
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $candidates += Join-Path $programFilesX86 "Git\cmd\git.exe"
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Git\cmd\git.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "git.exe was not found. Install Git and make it available on PATH."
}


function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    # Windows PowerShell turns native stderr into ErrorRecords when it is
    # redirected. Do not let a successful git command that writes progress to
    # stderr (for example git fetch) terminate the updater.
    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $script:Git @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }

    if ($exitCode -ne 0) {
        $text = ($output | Out-String).Trim()
        throw ("git {0} failed with exit code {1}: {2}" -f (
            $Arguments -join " "), $exitCode, $text)
    }
    return $output
}


function Get-ReleaseVersionKey {
    param([Parameter(Mandatory = $true)][string]$Tag)

    # Accept both the current vYYYY.MM.DD.N form and legacy vYYYY.MM.DD tags.
    # A missing revision counts as 0, so the two spellings compare as equal.
    if ($Tag -notmatch '^v([0-9]{4}\.[0-9]{2}\.[0-9]{2})(?:\.([0-9]+))?$') {
        return $null
    }

    $date = $Matches[1]
    $revision = if ($Matches[2]) { [int]$Matches[2] } else { 0 }
    return ("{0}.{1:D6}" -f $date, $revision)
}


function Get-ServerVersion {
    if (-not (Test-Path -LiteralPath $script:ServerExe)) {
        return "not installed"
    }

    $savedErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $script:ServerExe --version 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }

    if ($exitCode -ne 0) {
        return "unavailable"
    }
    return (($output | Out-String).Trim())
}


function Install-Project {
    param([switch]$Force)

    Push-Location $AppDir
    try {
        $arguments = @("-m", "pip", "install", "--upgrade")
        if ($Force) {
            $arguments += @("--force-reinstall", "--no-deps")
        }
        $arguments += @("-e", ".[ice]")

        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $script:Python @arguments
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        if ($exitCode -ne 0) {
            throw "pip install exited with code $exitCode"
        }
    } finally {
        Pop-Location
    }
}


function Wait-ServiceState {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$State,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if ($service -and $service.Status.ToString() -eq $State) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "Service '$Name' did not reach state '$State' within $TimeoutSeconds seconds."
}


function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$TargetHost,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne(2000) -and $client.Connected) {
                return $true
            }
        } catch {
            # Retry until the timeout expires.
        } finally {
            $client.Close()
        }
        Start-Sleep -Seconds 1
    }

    return $false
}


function Restore-PreviousRelease {
    param(
        [Parameter(Mandatory = $true)][string]$Target
    )

    Write-Log "Rolling back to $Target" "WARN"

    try {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status.ToString() -ne "Stopped") {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Wait-ServiceState -Name $ServiceName -State "Stopped" -TimeoutSeconds 30
        }
    } catch {
        Write-Log "Could not stop the service during rollback: $($_.Exception.Message)" "ERROR"
    }

    try {
        Invoke-Git -Arguments @("-c", "advice.detachedHead=false", "checkout", $Target) |
            Out-Null
        Install-Project -Force
        Write-Log "Checked out and reinstalled $Target" "WARN"
    } catch {
        Write-Log "Rollback checkout/install failed: $($_.Exception.Message)" "ERROR"
    }

    try {
        Start-Service -Name $ServiceName -ErrorAction Stop
        Wait-ServiceState -Name $ServiceName -State "Running" -TimeoutSeconds 60
        if (-not (Test-TcpPort -TargetHost $HealthHost -Port $HealthPort `
                    -TimeoutSeconds $HealthTimeoutSeconds)) {
            throw "TCP health check failed on $HealthHost`:$HealthPort"
        }
        Write-Log "Rollback complete; the service is healthy" "WARN"
    } catch {
        Write-Log "Rollback restart/health check failed: $($_.Exception.Message)" "ERROR"
    }
}


$logDirectory = Split-Path -Parent $LogFile
if ($logDirectory) {
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
}

$script:Git = Get-GitExe

if (-not (Test-Path -LiteralPath $AppDir)) {
    throw "Application directory not found: $AppDir"
}
if (-not (Test-Path -LiteralPath $script:Python)) {
    throw "Virtual-environment Python not found: $script:Python"
}

# The scheduled task may run as SYSTEM while the checkout is owned by the
# administrator who cloned it. Trust this specific checkout, and fail instead of
# waiting for an interactive credential prompt.
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "safe.directory"
$env:GIT_CONFIG_VALUE_0 = $AppDir
$env:GIT_TERMINAL_PROMPT = "0"
$env:GCM_INTERACTIVE = "Never"

$mutex = New-Object System.Threading.Mutex($false, "Global\3DSC-IceServer-Update")
$acquired = $false

try {
    try {
        $acquired = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }

    if (-not $acquired) {
        Write-Log "Another update is already running; exiting." "WARN"
        return
    }

    Push-Location $AppDir
    $rollbackNeeded = $false
    $previous = $null

    try {
        $status = (Invoke-Git -Arguments @("status", "--porcelain") | Out-String).Trim()
        if ($status) {
            throw "The Git working tree is not clean. Commit, stash, or remove local changes first."
        }

        Invoke-Git -Arguments @(
            "fetch", "--tags", "--prune", "--prune-tags", $Remote
        ) | Out-Null

        $tagLines = @(Invoke-Git -Arguments @("tag", "--list", $TagPattern))
        $tagLines = @($tagLines | ForEach-Object { $_.Trim() } | Where-Object { $_ })

        # Keep only calendar-version tags. This prevents an unrelated v-prefixed
        # tag (for example a vendor tag) from being installed as a release.
        $candidates = @(
            foreach ($tag in $tagLines) {
                $key = Get-ReleaseVersionKey -Tag $tag
                if ($key) {
                    [pscustomobject]@{
                        Tag = $tag
                        Key = $key
                        ExplicitRevision = ($tag -match '^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]+$')
                    }
                }
            }
        )
        # Prefer an explicit vYYYY.MM.DD.N tag when a legacy vYYYY.MM.DD tag
        # carries the same date and revision.
        $candidates = @($candidates | Sort-Object -Property Key, ExplicitRevision -Descending)
        if ($candidates.Count -eq 0) {
            throw "No calendar-version release tags (vYYYY.MM.DD[.N]) match '$TagPattern'."
        }

        $latest = $candidates[0].Tag

        $objectType = ((Invoke-Git -Arguments @("cat-file", "-t", $latest)) | Out-String).Trim()
        if ($objectType -ne "tag") {
            if (-not $AllowLightweightTags) {
                throw "Tag '$latest' is lightweight. Release tags must be annotated; use scripts/release.py or 'git tag -a'."
            }
            Write-Log "Tag '$latest' is lightweight; continuing because -AllowLightweightTags is set." "WARN"
        }

        if ($RequireSignedTag) {
            $savedErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                $signatureOutput = & $script:Git tag -v $latest 2>&1
                $signatureExitCode = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $savedErrorActionPreference
            }
            if ($signatureExitCode -ne 0) {
                $detail = ($signatureOutput | Out-String).Trim()
                throw "Tag '$latest' does not have a valid trusted signature: $detail"
            }
            Write-Log "Verified the signature of $latest"
        }

        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $described = & $script:Git describe --tags --exact-match HEAD 2>$null
            $describeExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }

        if ($describeExitCode -eq 0 -and $described) {
            $previous = (($described | Out-String).Trim())
        } else {
            $previous = ((Invoke-Git -Arguments @("rev-parse", "HEAD")) | Out-String).Trim()
        }

        $headCommit = ((Invoke-Git -Arguments @("rev-parse", "HEAD")) | Out-String).Trim()
        $latestCommit = ((Invoke-Git -Arguments @(
            "rev-parse", "$latest^{commit}"
        )) | Out-String).Trim()

        $currentVersion = Get-ServerVersion
        Write-Log "Current: $currentVersion ($previous); latest tag: $latest"

        if ($headCommit -eq $latestCommit) {
            Write-Log "Already up to date."
            return
        }
        if ($DryRun) {
            Write-Log "Dry run: would update $previous -> $latest"
            return
        }

        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        $rollbackNeeded = $true

        Write-Log "Stopping service '$ServiceName'"
        if ($service.Status.ToString() -ne "Stopped") {
            Stop-Service -Name $ServiceName -Force -ErrorAction Stop
        }
        Wait-ServiceState -Name $ServiceName -State "Stopped" -TimeoutSeconds 30

        Write-Log "Checking out $latest"
        Invoke-Git -Arguments @(
            "-c", "advice.detachedHead=false", "checkout", $latest
        ) | Out-Null

        Write-Log "Reinstalling the package"
        Install-Project

        $newVersion = Get-ServerVersion
        if ($newVersion -eq $currentVersion -or
                $newVersion -eq "unavailable" -or
                $newVersion -eq "not installed") {
            Write-Log "Version did not change; forcing a reinstall" "WARN"
            Install-Project -Force
            $newVersion = Get-ServerVersion
        }
        if ($newVersion -eq "unavailable" -or $newVersion -eq "not installed") {
            throw "New server version check failed: $newVersion"
        }
        Write-Log "Installed: $newVersion"

        Write-Log "Starting service '$ServiceName'"
        Start-Service -Name $ServiceName -ErrorAction Stop
        Wait-ServiceState -Name $ServiceName -State "Running" -TimeoutSeconds 60

        if (-not (Test-TcpPort -TargetHost $HealthHost -Port $HealthPort `
                    -TimeoutSeconds $HealthTimeoutSeconds)) {
            throw "TCP health check failed on $HealthHost`:$HealthPort"
        }

        $rollbackNeeded = $false
        Write-Log "Update complete: $previous -> $latest"
    } catch {
        Write-Log "Update failed: $($_.Exception.Message)" "ERROR"
        if ($rollbackNeeded -and $previous) {
            Restore-PreviousRelease -Target $previous
        }
        throw
    } finally {
        Pop-Location
    }
} finally {
    if ($acquired) {
        try {
            $mutex.ReleaseMutex()
        } catch {
            # The process may already have released it.
        }
    }
    $mutex.Dispose()
}
