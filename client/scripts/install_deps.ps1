<#
.SYNOPSIS
    Floor Tiling Client - Install all dependencies

.DESCRIPTION
    1. Installs system dependencies (Docker Desktop + Google Chrome) via winget or Chocolatey
    2. Creates a Python virtual environment (if needed)
    3. Installs pip packages from requirements.txt (including PyTorch)

.PARAMETER SkipSystem
    Skip Docker + Chrome installation (only do Python packages).

.PARAMETER NoVenv
    Skip virtual-environment creation and install globally.

.PARAMETER Gpu
    Install PyTorch with CUDA 12.1 support instead of CPU-only.

.EXAMPLE
    .\install_deps.ps1                   # everything: system + venv + pip (CPU)
    .\install_deps.ps1 -Gpu              # everything with CUDA PyTorch
    .\install_deps.ps1 -SkipSystem       # only Python packages
    .\install_deps.ps1 -NoVenv           # system + global pip install
#>
param(
    [switch]$SkipSystem,
    [switch]$NoVenv,
    [switch]$Gpu
)

$ErrorActionPreference = "Stop"
$ClientDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReqFile   = Join-Path $ClientDir "requirements.txt"
$VenvDir   = Join-Path $ClientDir ".venv"

Write-Host ""
Write-Host "=========================================="
Write-Host " Floor Tiling -- Install Dependencies"
Write-Host "=========================================="
Write-Host ""

# ── Helpers ──────────────────────────────────────────────────────────────────
function Test-CommandExists([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# ══════════════════════════════════════════════════════════════════════════════
# PART 1: System dependencies (Docker + Chrome)
# ══════════════════════════════════════════════════════════════════════════════
if (-not $SkipSystem) {

Write-Host "[1/2] System dependencies (Docker + Chrome)" -ForegroundColor Cyan
Write-Host ""

# ── Determine package manager ────────────────────────────────────────────────
$UseWinget = Test-CommandExists "winget"
$UseChoco  = Test-CommandExists "choco"

if (-not $UseWinget -and -not $UseChoco) {
    Write-Host "Neither winget nor Chocolatey found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install manually:"
    Write-Host "  Docker Desktop : https://www.docker.com/products/docker-desktop/"
    Write-Host "  Google Chrome  : https://www.google.com/chrome/"
    exit 1
}

$Mgr = if ($UseWinget) { "winget" } else { "choco" }
Write-Host "Using $Mgr ..."
Write-Host ""

# ── Docker Desktop ───────────────────────────────────────────────────────────
if (Test-CommandExists "docker") {
    Write-Host "Docker already installed: $(docker --version)" -ForegroundColor Green
} else {
    Write-Host "Installing Docker Desktop ..."
    if ($UseWinget) {
        winget install --id Docker.DockerDesktop -e --silent --accept-package-agreements --accept-source-agreements
    } else {
        choco install docker-desktop -y
    }
    if ($LASTEXITCODE -ne 0) { Write-Warning "Docker install may have failed." }
    else { Write-Host "Docker Desktop installed." -ForegroundColor Green }
}

# Enable Docker autostart via registry
Write-Host "Enabling Docker Desktop to start at login ..."
$DockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
try {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
        -Name "Docker Desktop" -Value "`"$DockerExe`"" -ErrorAction Stop
    Write-Host "Docker will start at login." -ForegroundColor Green
} catch {
    Write-Warning "Could not set registry key. Enable it in Docker Desktop -> Settings -> General."
}

# ── Google Chrome ────────────────────────────────────────────────────────────
$ChromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$([System.Environment]::GetEnvironmentVariable('ProgramFiles(x86)'))\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$ChromeFound = $ChromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($ChromeFound) {
    Write-Host "Google Chrome already installed." -ForegroundColor Green
} else {
    Write-Host "Installing Google Chrome ..."
    if ($UseWinget) {
        winget install --id Google.Chrome -e --silent --accept-package-agreements --accept-source-agreements
    } else {
        choco install googlechrome -y
    }
    if ($LASTEXITCODE -ne 0) { Write-Warning "Chrome install may have failed." }
    else { Write-Host "Google Chrome installed." -ForegroundColor Green }
}

} else {
    Write-Host "[1/2] Skipping system dependencies (-SkipSystem)" -ForegroundColor DarkGray
}

# ══════════════════════════════════════════════════════════════════════════════
# PART 2: Python virtual environment + pip packages
# ══════════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "[2/2] Python packages" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $ReqFile)) {
    Write-Host "ERROR: requirements.txt not found at $ReqFile" -ForegroundColor Red
    exit 1
}

# ── Virtual environment ──────────────────────────────────────────────────────
if (-not $NoVenv) {
    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating virtual environment at $VenvDir ..."
        python -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to create venv." }
        Write-Host "Virtual environment created." -ForegroundColor Green
    }

    $ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (Test-Path $ActivateScript) {
        Write-Host "Activating venv ..."
        & $ActivateScript
    } else {
        Write-Host "WARNING: Activate script not found, installing into current Python." -ForegroundColor Yellow
    }
}

# ── pip install ──────────────────────────────────────────────────────────────
Write-Host "Upgrading pip ..."
python -m pip install --upgrade pip

if ($Gpu) {
    Write-Host "Installing PyTorch with CUDA 12.1 ..." -ForegroundColor Cyan
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
} else {
    Write-Host "Installing PyTorch (CPU-only) ..." -ForegroundColor Cyan
    python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
}
if ($LASTEXITCODE -ne 0) { throw "PyTorch install failed." }

Write-Host "Installing remaining packages from requirements.txt ..."
python -m pip install -r $ReqFile
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=========================================="
Write-Host "All done." -ForegroundColor Green
if (-not $SkipSystem) {
    Write-Host "  docker --version"
    Write-Host "  chrome                (or open from Start menu)"
}
if (-not $NoVenv) {
    Write-Host "  Activate venv:  $VenvDir\Scripts\Activate.ps1"
}
Write-Host "=========================================="
