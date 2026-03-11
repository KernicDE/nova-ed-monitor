#Requires -Version 5.1
<#
.SYNOPSIS
    NOVA — Navigation, Operations, and Vessel Assistance
    Launcher script for Windows

.DESCRIPTION
    Installs Python and NOVA if not present, then launches NOVA.
    Run with -Update to force a NOVA update check.

.PARAMETER Update
    Check for and install the latest NOVA update before launching.

.EXAMPLE
    .\nova.ps1
    .\nova.ps1 -Update
#>

param(
    [switch]$Update
)

$ErrorActionPreference = "Stop"

$NOVA_URL = "git+https://github.com/KernicDE/nova-ed-monitor.git"
$NOVA_PKG = "nova-ed-monitor"
$PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
$PYTHON_VERSION_LABEL = "3.12.7"

function Write-Info    { param($Msg) Write-Host "  $Msg" -ForegroundColor Cyan }
function Write-Success { param($Msg) Write-Host "  $Msg" -ForegroundColor Green }
function Write-Warn    { param($Msg) Write-Host "  $Msg" -ForegroundColor Yellow }
function Write-Err     { param($Msg) Write-Host "  $Msg" -ForegroundColor Red }

# ── Banner ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  #  #   ###   #   #   ##  " -ForegroundColor Cyan
Write-Host "  ## #  #   #  #   #  #  # " -ForegroundColor Cyan
Write-Host "  # ##  #   #  #   #  #  # " -ForegroundColor Cyan
Write-Host "  #  #  #   #   # #   #  # " -ForegroundColor Cyan
Write-Host "  #  #   ###     #     ##  " -ForegroundColor Cyan
Write-Host ""
Write-Host "  Navigation, Operations, and Vessel Assistance" -ForegroundColor White
Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── Find Python 3.11+ ─────────────────────────────────────────────────────────

function Get-Python {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        try {
            $result = & $cmd -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $result -eq "True") {
                return $cmd
            }
        } catch {}
    }
    # Try 'py' launcher (Windows Python Launcher)
    try {
        $result = & py -3 -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $result -eq "True") { return "py -3" }
    } catch {}
    return $null
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"
}

$Python = Get-Python

if (-not $Python) {
    Write-Warn "Python 3.11+ not found. Downloading Python $PYTHON_VERSION_LABEL..."
    Write-Host ""

    $installer = Join-Path $env:TEMP "python-installer.exe"

    try {
        Write-Info "Downloading from python.org..."
        Invoke-WebRequest -Uri $PYTHON_INSTALLER_URL -OutFile $installer -UseBasicParsing
    } catch {
        Write-Err "Download failed: $_"
        Write-Err "Please install Python 3.11+ manually from https://www.python.org/downloads/"
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Info "Installing Python (this takes about a minute)..."
    $proc = Start-Process -FilePath $installer `
        -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1" `
        -Wait -PassThru
    Remove-Item $installer -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Write-Err "Python installer exited with code $($proc.ExitCode)."
        Write-Err "Please install Python 3.11+ manually from https://www.python.org/downloads/"
        Read-Host "Press Enter to exit"
        exit 1
    }

    Refresh-Path

    $Python = Get-Python
    if (-not $Python) {
        Write-Err "Python was installed but is not yet in PATH."
        Write-Err "Please close this window, reopen it, and run nova.ps1 again."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host ""
}

$pyver = & $Python --version 2>&1
Write-Success "Python: $pyver"

# ── Install or update NOVA ────────────────────────────────────────────────────

$installed = & $Python -m pip show $NOVA_PKG 2>$null
$isInstalled = ($LASTEXITCODE -eq 0)

if (-not $isInstalled) {
    Write-Warn "NOVA not installed — installing now..."
    & $Python -m pip install $NOVA_URL
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Installation failed. Check your internet connection."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Success "NOVA installed successfully!"
    Write-Host ""
} elseif ($Update) {
    Write-Info "Checking for NOVA updates..."
    & $Python -m pip install --upgrade $NOVA_URL
    Write-Success "NOVA updated."
    Write-Host ""
} else {
    Write-Success "NOVA is installed."
    Write-Info "Tip: run with -Update to check for updates."
    Write-Host ""
}

# ── Launch NOVA ───────────────────────────────────────────────────────────────

Write-Info "Starting NOVA..."
Write-Host ""

# Refresh PATH in case nova was just installed
Refresh-Path

$novaCmd = Get-Command nova -ErrorAction SilentlyContinue
if ($novaCmd) {
    & nova
} else {
    & $Python -m ed_monitor
}
