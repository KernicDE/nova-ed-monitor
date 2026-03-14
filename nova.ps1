#Requires -Version 5.1
<#
.SYNOPSIS
    NOVA — Navigation, Operations, and Vessel Assistance
    Launcher script for Windows

.DESCRIPTION
    Auto-updates itself and NOVA from GitHub, then launches NOVA.
    Installs Python and NOVA automatically if not present.

.PARAMETER NoSelfUpdate
    Skip the self-update check (used internally after auto-update).

.PARAMETER Uninstall
    Completely remove NOVA (venv, config, event log). Does not touch
    Elite Dangerous journal files.

.EXAMPLE
    .\nova.ps1
    .\nova.ps1 -Uninstall
#>

param(
    [switch]$NoSelfUpdate,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$NOVA_URL             = "git+https://github.com/KernicDE/nova-ed-monitor.git"
$NOVA_PKG             = "nova-ed-monitor"
$PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
$VENV_DIR             = Join-Path $env:LOCALAPPDATA "nova\venv"
$SCRIPT_URL           = "https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1"
$GH_API_URL           = "https://api.github.com/repos/KernicDE/nova-ed-monitor/releases/latest"

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
Write-Host "  ---------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

$ScriptPath = $MyInvocation.MyCommand.Path
$NovaCfgDir = Join-Path $env:USERPROFILE ".config\nova"

# ── Uninstall ─────────────────────────────────────────────────────────────────

if ($Uninstall) {
    Write-Host ""
    Write-Host "  This will permanently remove:" -ForegroundColor Yellow
    Write-Host "    $VENV_DIR\.." -ForegroundColor Yellow
    Write-Host "    $NovaCfgDir" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Elite Dangerous journal files will NOT be touched." -ForegroundColor Green
    Write-Host ""
    $answer = Read-Host "  Confirm uninstall? [y/N]"
    if ($answer -eq "y" -or $answer -eq "Y") {
        $novaDataDir = Split-Path $VENV_DIR -Parent
        if (Test-Path $novaDataDir)  { Remove-Item $novaDataDir  -Recurse -Force }
        if (Test-Path $NovaCfgDir)   { Remove-Item $NovaCfgDir   -Recurse -Force }
        Write-Success "NOVA uninstalled."
        Write-Host ""
        Write-Host "  nova.ps1 and nova.bat can be deleted manually." -ForegroundColor DarkGray
    } else {
        Write-Host "  Cancelled." -ForegroundColor DarkGray
    }
    exit 0
}

# ── Self-update ───────────────────────────────────────────────────────────────

if (-not $NoSelfUpdate -and $ScriptPath) {
    try {
        $tmp = [System.IO.Path]::GetTempFileName() + ".ps1"
        Invoke-WebRequest -Uri $SCRIPT_URL -OutFile $tmp -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop

        $oldHash = (Get-FileHash $ScriptPath -Algorithm SHA256).Hash
        $newHash = (Get-FileHash $tmp        -Algorithm SHA256).Hash

        if ($oldHash -ne $newHash) {
            Write-Info "Script update found - applying..."
            Copy-Item $tmp $ScriptPath -Force
            Write-Success "Script updated. Restarting..."
            Write-Host ""
            & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -NoSelfUpdate
            exit
        }
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    } catch {
        # No internet or download failed — continue without self-update
    }
}

# ── Find Python 3.11+ ─────────────────────────────────────────────────────────

function Get-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $r = & $cmd -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $r -eq "True") { return $cmd }
        } catch {}
    }
    return $null
}

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH","User")
}

$Python = Get-Python

if (-not $Python) {
    Write-Warn "Python 3.11+ not found. Downloading Python 3.12.7..."
    Write-Host ""

    $installer = Join-Path $env:TEMP "python-installer.exe"
    try {
        Write-Info "Downloading from python.org..."
        Invoke-WebRequest -Uri $PYTHON_INSTALLER_URL -OutFile $installer -UseBasicParsing
    } catch {
        Write-Err "Download failed: $_"
        Write-Err "Please install Python 3.11+ manually from https://www.python.org/downloads/"
        Read-Host "Press Enter to exit"; exit 1
    }

    Write-Info "Installing Python (this takes about a minute)..."
    $proc = Start-Process $installer `
        -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1" `
        -Wait -PassThru
    Remove-Item $installer -Force -ErrorAction SilentlyContinue

    if ($proc.ExitCode -ne 0) {
        Write-Err "Python installer failed (code $($proc.ExitCode))."
        Read-Host "Press Enter to exit"; exit 1
    }

    Refresh-Path
    $Python = Get-Python
    if (-not $Python) {
        Write-Err "Python installed but not in PATH. Please reopen this window."
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Host ""
}

Write-Success "Python: $(& $Python --version 2>&1)"

# ── Set up virtual environment ────────────────────────────────────────────────

$VenvPip  = Join-Path $VENV_DIR "Scripts\pip.exe"
$VenvNova = Join-Path $VENV_DIR "Scripts\nova.exe"

if (-not (Test-Path $VENV_DIR)) {
    Write-Info "Creating NOVA virtual environment at $VENV_DIR ..."
    & $Python -m venv $VENV_DIR
    Write-Success "Virtual environment created."
}

# ── Install or auto-update NOVA ───────────────────────────────────────────────

$pipShow = & $VenvPip show $NOVA_PKG 2>&1
$isInstalled = ($LASTEXITCODE -eq 0)

if (-not $isInstalled) {
    Write-Warn "NOVA not installed - installing now..."
    & $VenvPip install --quiet --upgrade pip
    & $VenvPip install $NOVA_URL
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Installation failed. Check your internet connection."
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Success "NOVA installed successfully!"
    Write-Host ""
} else {
    # Compare installed version with latest GitHub release
    $installedVer = ($pipShow | Select-String "^Version:").ToString().Split(" ")[1].Trim()
    $latestVer    = ""
    try {
        $release  = Invoke-RestMethod -Uri $GH_API_URL -TimeoutSec 8 -ErrorAction Stop
        $latestVer = $release.tag_name.TrimStart("v")
    } catch {}

    if ($latestVer -and $installedVer -ne $latestVer) {
        Write-Info "Update available: $installedVer -> $latestVer - updating..."
        & $VenvPip install --upgrade $NOVA_URL
        Write-Success "NOVA updated to $latestVer."
        Write-Host ""
    } else {
        Write-Success "NOVA $installedVer is up to date."
        Write-Host ""
    }
}

# ── Launch NOVA ───────────────────────────────────────────────────────────────

Write-Info "Starting NOVA..."
Write-Host ""

& $VenvNova
