# ── Floor Tiling — Launcher (dev only) ──────────────────────────────────
# Usage:
#   .\launch.ps1

# ── Configuration ────────────────────────────────────────────────────────────
$AppPort         = 8000
$AppUrl          = "http://localhost:$AppPort"
$ExePath         = Join-Path $PSScriptRoot "floor-tiling.exe"
$ServerDir       = Join-Path $PSScriptRoot ".."
$ServerPy        = Join-Path $ServerDir "server.py"

# Save the original location
$origLocation = Get-Location
Push-Location (Join-Path $PSScriptRoot "..")
try {
    Write-Host "Starting Floor Tiling ..."
    python server.py
} finally {
    Pop-Location
    Set-Location $origLocation
    Write-Host ""
    Write-Host "Server stopped. Press Enter to continue."
    Read-Host
}
