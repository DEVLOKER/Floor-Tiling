# Floor Tiling Tools - Install dependencies
# Usage: powershell -ExecutionPolicy Bypass -File install_deps.ps1

$ErrorActionPreference = "Stop"

pip install pyinstaller cryptography
Write-Host "Installing required Python packages from requirements.txt..."

$ReqFile = Join-Path $PSScriptRoot "..\requirements.txt"
if (-not (Test-Path $ReqFile)) {
	Write-Host "ERROR: requirements.txt not found at $ReqFile" -ForegroundColor Red
	exit 1
}

pip install -r $ReqFile

Write-Host "All dependencies installed."
