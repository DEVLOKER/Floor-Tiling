<#
.SYNOPSIS
    Build the Floor Tiling Visualizer Docker image — no prompts, sensible defaults,
    everything overridable by an argument.

.DESCRIPTION
    Wraps `docker build` for the two model modes. Run with no args to build the
    default image (baked "fast" profile). Pass any switch to change a default.

.EXAMPLE
    .\docker-build.ps1
        → floortiling:fast  (models baked, offline runtime)

.EXAMPLE
    .\docker-build.ps1 -Profile quality
        → floortiling:quality

.EXAMPLE
    .\docker-build.ps1 -WithModels:$false
        → floortiling:fast-nomodels  (no weights; downloaded at runtime into a volume)

.EXAMPLE
    .\docker-build.ps1 -Profile fast -Sam base -Depth large -Tag floortiling:custom
        → fast profile but SAM=base, Depth=large
#>
[CmdletBinding()]
param(
    # Model profile baked/used: fast | balanced | quality | custom
    [ValidateSet('fast', 'balanced', 'quality', 'custom')]
    [Alias('p')]
    [string]$Profile = 'fast',

    # $true  → bake the profile's models into the image (offline runtime)
    # $false → lean image; models downloaded at runtime into a mounted volume
    [bool]$WithModels = $true,

    # Image tag. Default: floortiling:<profile>  (or floortiling:<profile>-nomodels when no models)
    [string]$Tag,

    # 1 = offline runtime, 0 = allow HF downloads. Default tracks -WithModels.
    [ValidateSet('0', '1')]
    [string]$HfOffline,

    # Optional per-model size overrides (blank = use the profile's value).
    [string]$Mask2former,
    [string]$Oneformer,
    [string]$Depth,
    [string]$YoloWorld,
    [string]$GroundingDino,
    [string]$Sam,
    [string]$Vitmatte,

    # Build without the layer cache.
    [switch]$NoCache,

    # Print the docker command instead of running it.
    [switch]$DryRun,

    # Opt-in guided menu (off by default → the no-prompt path stays the default).
    # Pressing Enter at any prompt accepts the shown default / current value.
    [Alias('i')]
    [switch]$Interactive
)

$ErrorActionPreference = 'Stop'

# ── Optional interactive menu ────────────────────────────────────────────────
# Only runs when -Interactive is passed. Each prompt pre-fills the value already
# resolved (a default, or whatever was passed on the command line), so Enter
# keeps it. This never appears in the default, no-args flow.
# Tag rule (one source of truth): always carries the profile; no-models gets a
# "-nomodels" suffix so baked vs volume images never collide.
function Get-DefaultTag([string]$Prof, [bool]$Models) {
    if ($Models) { "floortiling:$Prof" } else { "floortiling:$Prof-nomodels" }
}

# Run with no arguments at all → guided menu (so the user is "able to prompt").
# Pass any flag → fully scripted, no prompts. -Interactive forces the menu.
if ($PSBoundParameters.Count -eq 0) { $Interactive = $true }

if ($Interactive) {
    function Read-Default([string]$Prompt, [string]$Default) {
        $ans = Read-Host "$Prompt [$Default]"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $Default }
        return $ans.Trim()
    }
    Write-Host "Floor Tiling — Docker build (interactive)" -ForegroundColor Cyan

    do {
        $Profile = Read-Default 'Profile (fast/balanced/quality/custom)' $Profile
    } until ($Profile -in 'fast', 'balanced', 'quality', 'custom')

    $wm = Read-Default 'Bake models into the image? (y/n)' $(if ($WithModels) { 'y' } else { 'n' })
    $WithModels = $wm -match '^(y|yes|true|1)$'

    if (-not $WithModels) {
        Write-Host "  No-models image: the profile/sizes you pick are RUNTIME DEFAULTS." -ForegroundColor DarkYellow
        Write-Host "  Change them anytime without rebuilding, e.g.:" -ForegroundColor DarkYellow
        Write-Host "    docker run -e DETECTION_PROFILE=quality -e SAM_VARIANT=base -v ftmodels:/app/models ..." -ForegroundColor DarkYellow
        Write-Host "  The chosen models download into the mounted volume on first use." -ForegroundColor DarkYellow
    }

    $defTag = if ($Tag) { $Tag } else { Get-DefaultTag $Profile $WithModels }
    $Tag = Read-Default 'Image tag' $defTag

    $defHf = if ($HfOffline) { $HfOffline } elseif ($WithModels) { '1' } else { '0' }
    $HfOffline = Read-Default 'HF offline at runtime? (1=offline, 0=allow downloads)' $defHf

    # Per-model sizes only matter for the "custom" profile; fast/balanced/quality
    # already define every model. (Power users can still override an individual
    # model on any profile via the command-line flags, e.g. -Sam base.)
    if ($Profile -eq 'custom') {
        Write-Host "  Custom profile — set each model size (Enter = settings.py default):" -ForegroundColor DarkGray
        $Mask2former   = Read-Default '  Mask2Former (tiny/small/base/large)' $Mask2former
        $Oneformer     = Read-Default '  OneFormer (tiny/large/dinat_large)' $Oneformer
        $Depth         = Read-Default '  Depth (small/base/large)' $Depth
        $YoloWorld     = Read-Default '  YOLO-World (s/m/l/x)' $YoloWorld
        $GroundingDino = Read-Default '  Grounding DINO (tiny/base)' $GroundingDino
        $Sam           = Read-Default '  SAM (slim50/slim77/base/large/huge)' $Sam
        $Vitmatte      = Read-Default '  ViTMatte (small/base)' $Vitmatte
    }

    if ((Read-Default 'Build without cache? (y/n)' $(if ($NoCache) { 'y' } else { 'n' })) -match '^(y|yes)$') {
        $NoCache = $true
    }
}

# ── Derive defaults that depend on other args ────────────────────────────────
if (-not $Tag) {
    $Tag = Get-DefaultTag $Profile $WithModels
}
if (-not $HfOffline) {
    $HfOffline = if ($WithModels) { '1' } else { '0' }
}
$withModelsArg = if ($WithModels) { 'true' } else { 'false' }

# ── Assemble docker build arguments ──────────────────────────────────────────
$dockerArgs = @(
    'build',
    '--build-arg', "WITH_MODELS=$withModelsArg",
    '--build-arg', "DETECTION_PROFILE=$Profile",
    '--build-arg', "HF_HUB_OFFLINE=$HfOffline"
)

# Per-model overrides — only forwarded when provided.
$overrides = [ordered]@{
    MASK2FORMER_VARIANT    = $Mask2former
    ONEFORMER_VARIANT      = $Oneformer
    DEPTH_VARIANT          = $Depth
    YOLO_WORLD_VARIANT     = $YoloWorld
    GROUNDING_DINO_VARIANT = $GroundingDino
    SAM_VARIANT            = $Sam
    VITMATTE_VARIANT       = $Vitmatte
}
foreach ($k in $overrides.Keys) {
    if ($overrides[$k]) {
        $dockerArgs += @('--build-arg', "$k=$($overrides[$k])")
    }
}

if ($NoCache) { $dockerArgs += '--no-cache' }
$dockerArgs += @('-t', $Tag, '.')

# ── Run ──────────────────────────────────────────────────────────────────────
Write-Host "Building $Tag" -ForegroundColor Cyan
Write-Host "  profile=$Profile  with_models=$withModelsArg  hf_offline=$HfOffline" -ForegroundColor DarkGray
Write-Host "docker $($dockerArgs -join ' ')" -ForegroundColor DarkGray

if ($DryRun) { return }

& docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE)" }
Write-Host "Built $Tag" -ForegroundColor Green
