<#
.SYNOPSIS
    Floor Tiling — Windows EXE build script

.DESCRIPTION
    Produces:  dist\floor-tiling\floor-tiling.exe  (+ supporting files)

.PARAMETER Model
    SAM2 model variant to bundle: tiny (default) | small | base_plus | large | all

.EXAMPLE
    .\build_exe.ps1                # tiny model (default)
    .\build_exe.ps1 -Model small
    .\build_exe.ps1 -Model base_plus
    .\build_exe.ps1 -Model large
    .\build_exe.ps1 -Model all     # copies all four models

.NOTES
    Prerequisites (run once):
        pip install pyinstaller cython setuptools cryptography
    Can be run from any directory — automatically targets client\.
#>
param(
    [ValidateSet("tiny", "small", "base_plus", "large", "all")]
    [string]$Model = "tiny"
)

$ErrorActionPreference = "Stop"

# ── Change to client/ regardless of where the script is invoked from ─────────
$ClientDir = Join-Path $PSScriptRoot ".."
Set-Location $ClientDir

$DistDir = "dist\floor-tiling"

$ModelFiles = @{
    tiny      = "sam2.1_hiera_tiny.pt"
    small     = "sam2.1_hiera_small.pt"
    base_plus = "sam2.1_hiera_base_plus.pt"
    large     = "sam2.1_hiera_large.pt"
    all       = ""
}

# Variant written into settings.py — 'all' keeps tiny as the active model
$Variant = if ($Model -eq "all") { "tiny" } else { $Model }

Write-Host ""
Write-Host "========================================================"
Write-Host " Floor Tiling -- EXE build"
Write-Host "========================================================"

# ── Step 1: Cython compile ───────────────────────────────────────────────────
Write-Host ""
Write-Host "[1/5] Compiling Cython extensions (.pyd) ..."
python setup_cython.py build_ext --inplace
if ($LASTEXITCODE -ne 0) { throw "Cython compilation failed." }
Write-Host "OK  Cython done."

# ── Step 2: Patch settings.py, run PyInstaller, restore ──────────────────────
Write-Host ""
Write-Host "[2/5] Running PyInstaller  (model variant: $Variant) ..."

$SettingsPath = "config\settings.py"
$OriginalContent = Get-Content $SettingsPath -Raw

# Replace the variant value inside MODEL_CONFIG
$PatchedContent = $OriginalContent -replace '("variant"\s*:\s*)"[^"]*"', "`$1`"$Variant`""
Set-Content $SettingsPath $PatchedContent -NoNewline
Write-Host "   Patched MODEL_CONFIG variant -> '$Variant'"

# install PyInstaller if not already installed; check version
# python -m pip install pyinstaller; python -m PyInstaller --version
try {
    pyinstaller floor_tiling.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
} finally {
    # Always restore settings.py, even on failure
    Set-Content $SettingsPath $OriginalContent -NoNewline
    Write-Host "   settings.py restored."
}
Write-Host "OK  PyInstaller done."

# ── Step 2.5: Obfuscate dist output with PyArmor ─────────────────────────────
Write-Host ""
Write-Host "[2.5/5] Obfuscating dist output with PyArmor ..."
$DistServer = Join-Path $DistDir "server.py"
if (Test-Path $DistServer) {
    pyarmor gen $DistServer -O $DistDir
    if ($LASTEXITCODE -ne 0) { throw "PyArmor obfuscation failed for dist/server.py." }
    # Copy PyArmor runtime if present
    $runtime = Join-Path $DistDir "pyarmor_runtime_000000"
    if (Test-Path $runtime) {
        Copy-Item $runtime $DistDir -Recurse -Force
    }
}
Write-Host "OK  PyArmor dist obfuscation done."

# ── Step 3: Copy SAM2 model(s) ───────────────────────────────────────────────
Write-Host ""
Write-Host "[3/5] Copying SAM2 model(s) [$Model] -> $DistDir\sam2\models\ ..."
$ModelsOut = Join-Path $DistDir "sam2\models"
New-Item -ItemType Directory -Force $ModelsOut | Out-Null

if ($Model -eq "all") {
    $pts = Get-ChildItem "sam2\models\*.pt" -ErrorAction SilentlyContinue
    if ($pts) {
        $pts | Copy-Item -Destination $ModelsOut
    } else {
        Write-Warning "No .pt files found in sam2\models\"
    }
} else {
    $PtFile = "sam2\models\$($ModelFiles[$Model])"
    if (Test-Path $PtFile) {
        Copy-Item $PtFile $ModelsOut
    } else {
        Write-Warning "Model file not found: $PtFile"
    }
}
Write-Host "OK  Models in dist:"
Get-ChildItem $ModelsOut | Format-Table Name, @{N="Size";E={"{0:N1} MB" -f ($_.Length/1MB)}} -AutoSize

# ── Step 4: Clean Cython artefacts ───────────────────────────────────────────
Write-Host ""
Write-Host "[4/5] Cleaning Cython build artefacts ..."
$CythonDirs = @("config","core","ml_models","patterns","processors","utils")
foreach ($dir in $CythonDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Recurse -Include "*.pyd","*.c" | Remove-Item -Force
        Get-ChildItem $dir -Recurse -Directory -Filter "build" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}
# Also clean shared modules .c files
$SharedDirs = @("..\shared\utils", "..\shared\config")
foreach ($dir in $SharedDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Recurse -Include "*.c" | Remove-Item -Force
    }
}
Write-Host "OK  Clean."

# ── Step 5: Copy customer launcher ───────────────────────────────────────────
Write-Host ""
Write-Host "[5/5] Copying launch.ps1 -> $DistDir\ ..."
$LaunchSrc = if (Test-Path (Join-Path $PSScriptRoot "launch.ps1")) {
    Join-Path $PSScriptRoot "launch.ps1"
} elseif (Test-Path "launch.ps1") {
    "launch.ps1"
} else { $null }

if ($LaunchSrc) {
    Copy-Item $LaunchSrc (Join-Path $DistDir "launch.ps1") -Force
    Write-Host "OK  launch.ps1 copied."
} else {
    Write-Warning "launch.ps1 not found -- customers will need to run floor-tiling.exe manually."
}

# ── Step 5.5: Sign the EXE (optional, requires signtool) ───────────────
$ExePath = Join-Path $DistDir "floor-tiling.exe"
if (Test-Path $ExePath) {
    Write-Host ""
    Write-Host "[5.5/5] Signing EXE ..."
    $SignTool = "C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
    if (Test-Path $SignTool) {
        # Update the following with your actual certificate path and password
        $CertPath = "C:\path\to\your\certificate.pfx"  # <-- EDIT THIS
        $CertPass = "your-cert-password"                  # <-- EDIT THIS
        if (Test-Path $CertPath) {
            & $SignTool sign /f $CertPath /p $CertPass /tr http://timestamp.digicert.com /td sha256 /fd sha256 $ExePath
            if ($LASTEXITCODE -eq 0) {
                Write-Host "OK  EXE signed."
            } else {
                Write-Warning "signtool failed to sign the EXE."
            }
        } else {
            Write-Warning "Certificate file not found: $CertPath. Skipping signing."
        }
    } else {
        Write-Warning "signtool.exe not found. Skipping code signing."
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
$DistSize = "{0:N0} MB" -f ((Get-ChildItem $DistDir -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "========================================================"
Write-Host "OK  Build complete!"
Write-Host ""
Write-Host "  Model  : $Model  ($($ModelFiles[$Variant]))"
Write-Host "  Output : $DistDir\"
Write-Host "  Size   : $DistSize"
Write-Host ""
Write-Host "  To build with a different model:"
Write-Host "    .\build_exe.ps1                  # tiny (default, ~40 MB)"
Write-Host "    .\build_exe.ps1 -Model small"
Write-Host "    .\build_exe.ps1 -Model base_plus"
Write-Host "    .\build_exe.ps1 -Model large"
Write-Host "    .\build_exe.ps1 -Model all"
Write-Host ""
Write-Host "  Ship the entire  $DistDir\  folder to the customer."
Write-Host "  They also need  floor_tiling.lic  on a USB drive."
Write-Host ""
Write-Host "  Customer runs:"
Write-Host "    Right-click launch.ps1 -> Run with PowerShell"
Write-Host "========================================================"
