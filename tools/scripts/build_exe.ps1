<#
.SYNOPSIS
    Floor Tiling Tools - Build standalone Windows EXE
.DESCRIPTION
    Produces:  dist\tools-panel\tools-panel.exe  (+ supporting files)
    Bundles the fingerprint generator into a single distributable folder using PyInstaller.
.EXAMPLE
    .\build_exe.ps1            # build the tools exe
.NOTES
    Prerequisites (run once):
        pip install pyinstaller cryptography
    Can be run from any directory - automatically targets tools\.
#>

$ErrorActionPreference = "Stop"

# ── Resolve paths ────────────────────────────────────────────────────────────
$ScriptsDir = $PSScriptRoot
$ToolsDir   = (Resolve-Path (Join-Path $ScriptsDir ".."))
$SpecFile   = Join-Path $ToolsDir "tools_panel.spec"
$DistDir    = Join-Path $ToolsDir "dist\tools-panel"

if (-not (Test-Path $SpecFile)) {
    Write-Host "ERROR: tools_panel.spec not found at $SpecFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================================"
Write-Host " Floor Tiling Tools -- EXE build"
Write-Host "========================================================"
Write-Host ""

# ── Step 1: Check prerequisites ─────────────────────────────────────────────
Write-Host "[1/3] Checking prerequisites ..."
try {
    $pyiVersion = & python -m PyInstaller --version 2>&1
    Write-Host "  PyInstaller: $pyiVersion"
} catch {
    Write-Host "ERROR: PyInstaller not found. Install with: pip install pyinstaller" -ForegroundColor Red
    exit 1
}


# ── Step 2: Cythonize and Obfuscate ─────────────────────────────────────────
Write-Host ""
Write-Host "[2/3] Cythonizing and obfuscating Python files ..."
$BuildDir = Join-Path $ToolsDir "build_cython"
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# Cythonize all .py files in tools (except __init__.py)
$pyFiles = Get-ChildItem $ToolsDir -Filter *.py | Where-Object { $_.Name -ne "__init__.py" }
foreach ($py in $pyFiles) {
    $pyName = $py.Name
    $pyBase = [System.IO.Path]::GetFileNameWithoutExtension($pyName)
    # Note: --obfuscate is only available in Cython Pro. Standard Cython provides basic protection.
    python -m cython -3 $py.FullName
    if ($LASTEXITCODE -ne 0) { throw "Cythonization failed for $pyName." }
}
Write-Host "OK  Cythonization done." -ForegroundColor Green

# ── Step 3: Run PyInstaller ─────────────────────────────────────────────────
Write-Host ""
Write-Host "[3/3] Running PyInstaller ..."
Push-Location $ToolsDir
try {
    pyinstaller tools_panel.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
} finally {
    Pop-Location
}
Write-Host "OK  PyInstaller done." -ForegroundColor Green

# ── Step 4: (PyArmor EXE obfuscation removed; not supported) ────────────────
Write-Host ""
Write-Host "[4/4] Skipping PyArmor EXE obfuscation (not supported) ..."
Write-Host "OK  Skipped PyArmor EXE obfuscation."

# ── Summary ─────────────────────────────────────────────────────────────────
Write-Host ""
$DistSize = "{0:N0} MB" -f ((Get-ChildItem $DistDir -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "========================================================"
Write-Host "  Output : $DistDir\"
Write-Host "  Size   : $DistSize"
Write-Host "  Run    : .\tools-panel.exe"
Write-Host "========================================================"
