<#
.SYNOPSIS
    Floor Tiling - Run the app in Docker + open Chrome

.DESCRIPTION
    Starts the floor-tiling Docker container, waits for the health check,
    opens Chrome in kiosk mode, and stops the container when the browser closes.

.PARAMETER Tag
    Image tag to run (required).

.PARAMETER Port
    Host port to bind (default: 8000).

.EXAMPLE
    .\run_docker.ps1 -Tag 1.0.0
    .\run_docker.ps1 -Tag latest -Port 9000
#>
param(
    [string]$Tag = "latest",

    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ImageName     = "floor-tiling"
$ContainerName = "floor-tiling-app"
$Url           = "http://localhost:$Port"
$LicenseUsbPath= "D:\license"

# Convert Windows path to Docker-compatible mount (forward slashes)
$DockerMount = $LicenseUsbPath -replace '\\', '/'

Write-Host ""
Write-Host "=========================================="
Write-Host " Floor Tiling -- Docker Run"
Write-Host "=========================================="
Write-Host "  Image   : ${ImageName}:${Tag}"
Write-Host "  Port    : $Port"
Write-Host "  License : $LicenseUsbPath"
Write-Host "=========================================="
Write-Host ""

# Save the original location
$origLocation = Get-Location
Push-Location (Join-Path $PSScriptRoot "..")

try {
    # ── Stop any existing container with the same name ───────────────────────────
    try { docker stop $ContainerName 2>$null | Out-Null } catch {}
    try { docker rm   $ContainerName 2>$null | Out-Null } catch {}

    # ── Start container ──────────────────────────────────────────────────────────
    Write-Host "Starting container ..."
    docker run `
        --rm --detach `
        --name $ContainerName `
        -v "${DockerMount}:/license:ro" `
        -p "${Port}:8000" `
        "${ImageName}:${Tag}"

    if ($LASTEXITCODE -ne 0) { throw "Docker run failed." }

    # ── Wait for health check ───────────────────────────────────────────────────
    Write-Host "Waiting for server at $Url/health ..."
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }

    if (-not $ready) {
        Write-Host "Server did not respond within 120 s. Check: docker logs $ContainerName" -ForegroundColor Red
        exit 1
    }
    Write-Host "Server ready." -ForegroundColor Green

    # ── Open Chrome in kiosk mode ────────────────────────────────────────────────
    $PF86 = [System.Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$PF86\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($chrome) {
        Write-Host "Opening Chrome in kiosk mode ..."
        # Temp profile so Chrome starts as a new standalone process
        $tempProfile = Join-Path $env:TEMP "floor-tiling-chrome-$(Get-Random)"
        $chromeProc = Start-Process -FilePath $chrome -ArgumentList `
            "--kiosk $Url --incognito --user-data-dir=`"$tempProfile`" --disable-extensions --no-first-run --remote-debugging-port=0 --disable-features=Translate,TranslateUI --disable-translate" `
            -PassThru
    } else {
        Write-Host "Chrome not found -- opening default browser."
        Start-Process $Url
        $chromeProc = $null
    }

    # ── Keep running until browser closes or user presses Enter ──────────────────
    Write-Host ""
    Write-Host " App is running at $Url"
    if ($chromeProc) {
        Write-Host " Close the browser window or press Ctrl+C to stop."
        try { Wait-Process -Id $chromeProc.Id -ErrorAction Stop } catch {}
    } else {
        Write-Host " Press Enter to stop the container."
        Read-Host
    }

    # ── Cleanup ──────────────────────────────────────────────────────────────────
    Write-Host "Stopping container ..."
    docker stop $ContainerName 2>$null | Out-Null
    if ($tempProfile -and (Test-Path $tempProfile)) {
        Remove-Item $tempProfile -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Done." -ForegroundColor Green
} finally {
    Pop-Location
    Set-Location $origLocation
}