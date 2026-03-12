# ── Floor Tiling — Launcher (dev + prod) ──────────────────────────────────
# Default: prod (runs floor-tiling.exe next to this script)
# Pass -Dev to run in dev mode (python client/server.py)
#
# Examples:
#   .\launch.ps1          # prod
#   .\launch.ps1 -Dev     # dev
#
# USB license drive:
#   By default this script looks for the license file at E:\license\floor_tiling.lic
#   Change $UsbDrive below to match your USB drive letter.
# ─────────────────────────────────────────────────────────────────────────────
param(
    [switch]$Dev
)

# ── Configuration ────────────────────────────────────────────────────────────
$UsbDrive        = "D"
$LicenseUsbPath  = "${UsbDrive}:\license"
$AppPort         = 8000
$AppUrl          = "https://localhost:$AppPort"
$ExePath         = Join-Path $PSScriptRoot "floor-tiling.exe"
$LicenseFile     = "$LicenseUsbPath\floor_tiling.lic"
$ServerDir       = Join-Path $PSScriptRoot ".."
$ServerPy        = Join-Path $ServerDir "server.py"

# ── Resolve mode ─────────────────────────────────────────────────────────────
if ($Dev) {
    $Mode = "dev"
    if (-not (Test-Path $ServerPy)) {
        Write-Host ""
        Write-Host " ERROR: client\server.py not found at $ServerPy"
        Write-Host " Make sure you are running from the client\scripts\ folder in the repo."
        Write-Host ""
        Read-Host " Press Enter to exit"
        exit 1
    }
}
else {
    $Mode = "prod"
    if (-not (Test-Path $ExePath)) {
        Write-Host ""
        Write-Host " ERROR: floor-tiling.exe not found at $ExePath"
        Write-Host " Build first with .\build_exe.ps1 or run with -Dev for dev mode."
        Write-Host ""
        Read-Host " Press Enter to exit"
        exit 1
    }
}

Write-Host ""
Write-Host " Mode: $Mode"

# ── Verify license file exists before starting ───────────────────────────────
if (-not (Test-Path $LicenseFile)) {
    Write-Host ""
    Write-Host " ERROR: License file not found at $LicenseFile"
    Write-Host ""
    Write-Host " Make sure your USB drive is plugged in and the drive letter is ${UsbDrive}:"
    Write-Host " To use a different drive letter, edit `$UsbDrive in this file."
    Write-Host ""
    Read-Host " Press Enter to exit"
    exit 1
}

# ── Start the app server in background ───────────────────────────────────────
Write-Host "Starting Floor Tiling ..."
$env:LICENSE_USB_PATH = $LicenseUsbPath

if ($Mode -eq "prod") {
    $proc = Start-Process -FilePath $ExePath -PassThru -WindowStyle Hidden
}
else {
    $proc = Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory $ServerDir -PassThru
}

# ── Wait for server to be ready ──────────────────────────────────────────────
# Skip self-signed cert validation for health check (PS 5.1 compatible)
if (-not ([System.Management.Automation.PSTypeName]'TrustAll').Type) {
    Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAll : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate cert,
        WebRequest req, int problem) { return true; }
}
"@
}
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAll

Write-Host "Waiting for server ..."
while ($true) {
    Start-Sleep -Seconds 2
    try {
        $resp = Invoke-WebRequest -Uri "$AppUrl/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) { break }
    } catch { }
}
Write-Host "Server ready."

# ── Open Chrome in kiosk mode ────────────────────────────────────────────────
$PF86 = [System.Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
    "$PF86\Google\Chrome\Application\chrome.exe"
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

$chromeArgs = "--kiosk $AppUrl --incognito --disable-extensions --no-first-run --remote-debugging-port=0"

if ($chrome) {
    Start-Process -FilePath $chrome -ArgumentList $chromeArgs
}
else {
    Write-Host "Chrome not found - opening default browser."
    Start-Process $AppUrl
}

# ── Keep window open / wait ───────────────────────────────────────────────────
Write-Host ""
Write-Host " App is running at $AppUrl"
Write-Host " Close this window to stop the server."
Write-Host ""
Read-Host " Press Enter to stop"

# ── Shutdown ─────────────────────────────────────────────────────────────────
Write-Host "Stopping Floor Tiling ..."
if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
