<#
.SYNOPSIS
    Floor Tiling - Build Docker image

.DESCRIPTION
    Builds the floor-tiling Docker image from the repo-root Dockerfile.
    Two models are used (loaded offline at runtime):
      • Segmentation : facebook/mask2former-swin-large-ade-semantic
      • Depth        : depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf

.PARAMETER Tag
    Image tag (default: latest).

.PARAMETER ModelSource
    'download' (default) → fetch model weights from Hugging Face at build time.
    'local'             → use weights bundled in the build context
                          (.dockerignore keeps client/*/models/model.safetensors).
    'volume'            → ship NO weights; mount a writable volume at /models and
                          let the app download once into it (see docker-compose.yml).

.EXAMPLE
    .\build_docker.ps1                         # floor-tiling:latest (download)
    .\build_docker.ps1 -Tag 1.0.0              # floor-tiling:1.0.0  (download)
    .\build_docker.ps1 -ModelSource local      # bundle local weights
    .\build_docker.ps1 -ModelSource volume     # lean image, weights via volume
#>
param(
    [string]$Tag = "latest",
    [ValidateSet("download", "local", "volume")]
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
        Write-Warning "Local model mode -- make sure the weights exist at client/models/mask2former/model.safetensors and client/models/depth/model.safetensors (kept by .dockerignore negations)."
    }
    if ($ModelSource -eq "volume") {
        Write-Host "Volume mode -- image ships without weights; provide them via a /models volume at runtime (see docker-compose.yml)." -ForegroundColor Yellow
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
} finally {
    Pop-Location
    Set-Location $origLocation
}
