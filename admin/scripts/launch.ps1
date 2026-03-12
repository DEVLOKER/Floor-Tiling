<#
.SYNOPSIS
    Floor Tiling Admin - Launch the admin panel

.DESCRIPTION
    Installs dependencies (first run), starts the FastAPI admin dashboard
    (license management UI), and opens a browser.

.PARAMETER Port
    Port to bind (default: 9000).

.PARAMETER Install
    Install dependencies before starting (creates venv + pip install).

.PARAMETER NoBrowser
    Don't open the browser automatically.

.PARAMETER NoReload
    Disable uvicorn auto-reload.

.EXAMPLE
    .\launch.ps1                       # start + open browser
    .\launch.ps1 -Install              # install deps + start + open browser
    .\launch.ps1 -Port 8080            # custom port
    .\launch.ps1 -NoBrowser            # headless (no browser)
    .\launch.ps1 -NoBrowser -NoReload  # production-like
#>
param(
    [int]$Port = 9000,
    [switch]$Install,
    [switch]$NoBrowser,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$AdminDir   = (Resolve-Path (Join-Path $ScriptsDir "..")).Path
$VenvDir    = Join-Path $AdminDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ServerPy   = Join-Path $AdminDir "server.py"
$Url        = "https://localhost:$Port"

if (-not (Test-Path $ServerPy)) {
    Write-Host "ERROR: server.py not found at $ServerPy" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=========================================="
Write-Host " Floor Tiling -- Admin Panel"
Write-Host "=========================================="
Write-Host "  URL  : $Url"
Write-Host "  Mode : $(if ($NoReload) { 'production' } else { 'development (auto-reload)' })"
Write-Host "=========================================="
Write-Host ""

# ── Step 1: Install deps (only with -Install) ──────────────────────────────
if ($Install) {
    Write-Host "[1/3] Installing dependencies ..."
    & (Join-Path $ScriptsDir "install_deps.ps1")
    if ($LASTEXITCODE -ne 0) { throw "install_deps.ps1 failed." }
} else {
    Write-Host "[1/3] Skipping install (use -Install to install dependencies)."
}

# Activate venv
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    Write-Host "Activating venv ..."
    & $ActivateScript
}

# ── Step 2: Start server (foreground — logs appear in this shell) ────────────
Write-Host "[2/3] Starting admin server on port $Port ..."
Push-Location $AdminDir

# Prefer venv python if it exists, otherwise fall back to system python
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

$Url = "http://localhost:$Port"
# $Url = "https://localhost:$Port"

# ── Step 3: Wait for server + open browser (background job) ─────────────────
if (-not $NoBrowser) {
    Write-Host "[3/3] Will open browser once server is ready ..."
    $null = Start-Job -ScriptBlock {
        param($TargetUrl)

        # Bypass self-signed cert
        try {
            if (-not ([System.Management.Automation.PSTypeName]'TrustAll').Type) {
                Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAll : ICertificatePolicy {
    public bool CheckValidationResult(
        ServicePoint sp, X509Certificate cert,
        WebRequest req, int problem) { return true; }
}
"@
            }
            [System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAll
        } catch {}

        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            try {
                $r = Invoke-WebRequest -Uri "$TargetUrl/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
                if ($r.StatusCode -eq 200) {
                    # Open in default browser
                    Start-Process $TargetUrl
                    return
                }
            } catch {}
        }
    } -ArgumentList $Url
} else {
    Write-Host "[3/3] Headless mode (no browser)."
}

# Run server in foreground — logs stream here, Ctrl+C stops it
Write-Host ""
Write-Host "Server logs below. Press Ctrl+C to stop."
Write-Host "==========================================" 
Write-Host ""
try {
    & $PythonExe $ServerPy
} finally {
    Pop-Location
}
