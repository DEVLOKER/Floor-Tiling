<#
.SYNOPSIS
    Floor Tiling Admin - Install Python dependencies

.DESCRIPTION
    Installs the admin panel's pip dependencies from requirements.txt.
    By default installs into the current Python environment.
    Use -Venv to create and install into a virtual environment.

.PARAMETER Venv
    Create a virtual environment and install into it.

.EXAMPLE
    .\install_deps.ps1          # install into current Python environment
    .\install_deps.ps1 -Venv    # create venv + install
#>
param(
    [switch]$Venv
)

$ErrorActionPreference = "Stop"
$AdminDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReqFile  = Join-Path $AdminDir "requirements.txt"
$VenvDir  = Join-Path $AdminDir ".venv"

if (-not (Test-Path $ReqFile)) {
    Write-Host "ERROR: requirements.txt not found at $ReqFile" -ForegroundColor Red
    exit 1
}

# ── Virtual environment (opt-in) ────────────────────────────────────────────────
if ($Venv) {
    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating virtual environment at $VenvDir ..."
        python -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "Failed to create venv." }
        Write-Host "Virtual environment created." -ForegroundColor Green
    }

    # Activate
    $ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (Test-Path $ActivateScript) {
        Write-Host "Activating venv ..."
        & $ActivateScript
    } else {
        Write-Host "WARNING: Activate script not found, installing into current Python." -ForegroundColor Yellow
    }
}

# ── Install dependencies ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installing dependencies from $ReqFile ..."
python -m pip install --upgrade pip
python -m pip install -r $ReqFile
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }

Write-Host ""
Write-Host "All dependencies installed." -ForegroundColor Green
if ($Venv) {
    Write-Host "Activate the venv with:  $VenvDir\Scripts\Activate.ps1"
}
