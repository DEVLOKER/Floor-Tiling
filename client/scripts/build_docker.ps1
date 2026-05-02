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
    .\build_docker.ps1 -ModelSource local      # local model (make sure .dockerignore allows it)
#>
param(
    [string]$Tag = "latest",
    [ValidateSet("download", "local")]
    [string]$ModelSource = "download"
)

$ErrorActionPreference = "Stop"


# Save the original location
$origLocation = Get-Location
# Move two levels up: from client/scripts to project root
Push-Location (Join-Path $PSScriptRoot "../..")

try {

    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../.." )).Path
    Set-Location $RepoRoot

    $ImageName = "floor-tiling"

    if ($ModelSource -eq "local") {
        Write-Warning "Local model mode -- make sure 'mask2former/models/*.safetensors' is NOT excluded in .dockerignore"
    }

    Write-Host ""
    Write-Host "Building ${ImageName}:${Tag}  (MODEL_SOURCE=$ModelSource) ..."
    Write-Host ""

    docker build `
        --build-arg MODEL_SOURCE=$ModelSource `
        --tag "${ImageName}:${Tag}" `
        --file client/Dockerfile `
        .

    if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }

    Write-Host ""
    Write-Host "Build complete: ${ImageName}:${Tag}" -ForegroundColor Green
    Write-Host ""
    Write-Host "Run with:"
    Write-Host "  .\run_docker.ps1 -Tag $Tag"
    Write-Host "  docker run -p 8000:8000 ${ImageName}:${Tag}"
} finally {
    Pop-Location
    Set-Location $origLocation
}