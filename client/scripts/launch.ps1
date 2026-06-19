# ── Floor Tiling — Launcher (dev only) ──────────────────────────────────
# Usage:
#   .\launch.ps1

# ── Configuration ────────────────────────────────────────────────────────────
$AppPort         = 8000
$AppUrl          = "http://localhost:$AppPort"
$ExePath         = Join-Path $PSScriptRoot "floor-tiling.exe"
$ClientDir       = Join-Path $PSScriptRoot ".."

# Save the original location
$origLocation = Get-Location
Push-Location $ClientDir
try {
    Write-Host "Starting Floor Tiling ..."
    # src/ layout: make the floor_tiling package importable, then run it.
    $env:PYTHONPATH = (Resolve-Path (Join-Path $ClientDir "src")).Path
    python -m floor_tiling
} finally {
    Pop-Location
    Set-Location $origLocation
    Write-Host ""
    Write-Host "Server stopped. Press Enter to continue."
    Read-Host
}
