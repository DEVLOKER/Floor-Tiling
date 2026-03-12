<#
.SYNOPSIS
    Floor Tiling - Build Docker image

.DESCRIPTION
    Builds the floor-tiling Docker image from client/Dockerfile.

.PARAMETER Tag
    Image tag (default: latest).

.PARAMETER ModelSource
    'download' (default) fetches SAM2 model from Meta CDN at build time.
    'local' copies from ./sam2/models/ in the build context
    (remove 'sam2/models/*.pt' from .dockerignore first).

.EXAMPLE
    .\build_docker.ps1                         # floor-tiling:latest (download)
    .\build_docker.ps1 -Tag 1.0.0              # floor-tiling:1.0.0  (download)
    .\build_docker.ps1 -Tag latest -ModelSource local   # local model
#>
param(
    [string]$Tag = "latest",
    [ValidateSet("download", "local")]
    [string]$ModelSource = "download"
)

$ErrorActionPreference = "Stop"

$ClientDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ClientDir

$ImageName = "floor-tiling"

if ($ModelSource -eq "local") {
    Write-Warning "Local model mode -- make sure 'sam2/models/*.pt' is NOT excluded in .dockerignore"
}

Write-Host ""
Write-Host "Building ${ImageName}:${Tag}  (MODEL_SOURCE=$ModelSource) ..."
Write-Host ""

docker build `
    --build-arg MODEL_SOURCE=$ModelSource `
    --tag "${ImageName}:${Tag}" `
    --file Dockerfile `
    .

if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }

Write-Host ""
Write-Host "Build complete: ${ImageName}:${Tag}" -ForegroundColor Green
Write-Host ""
Write-Host "Run with:"
Write-Host "  .\run_docker.ps1 -Tag $Tag"
Write-Host "  docker run -p 8000:8000 ${ImageName}:${Tag}"
