#!/usr/bin/env bash
# Build the Floor Tiling Visualizer Docker image — no prompts, sensible defaults,
# everything overridable by a flag.
#
#   ./docker-build.sh                       # floortiling:fast (models baked)
#   ./docker-build.sh -p quality            # floortiling:quality
#   ./docker-build.sh --no-models           # floortiling:fast-nomodels (download at runtime)
#   ./docker-build.sh -p fast --sam base --depth large -t floortiling:custom
#
# Flags:
#   -p, --profile      fast|balanced|quality|custom   (default: fast)
#       --no-models    build lean image (no weights baked; runtime download)
#   -t, --tag          image tag (default: floortiling:<profile> | :<profile>-nomodels)
#       --hf-offline   0|1 (default: 1 when models baked, else 0)
#       --mask2former / --oneformer / --depth / --yolo-world /
#       --grounding-dino / --sam / --vitmatte   per-model size override
#       --no-cache     build without the layer cache
#       --dry-run      print the docker command and exit
#   -i, --interactive  opt-in guided menu (off by default; Enter keeps the value)
set -euo pipefail

PROFILE=fast
WITH_MODELS=true
TAG=""
HF_OFFLINE=""
NO_CACHE=""
DRY_RUN=""
INTERACTIVE=""
declare -A OV=()

# No arguments at all → guided menu (so the user is "able to prompt"). Pass any
# flag → fully scripted, no prompts. -i/--interactive forces the menu.
[[ $# -eq 0 ]] && INTERACTIVE=1

# Tag rule (one source of truth): always carries the profile; no-models adds a
# "-nomodels" suffix so baked vs volume images never collide.
default_tag() { [[ "$1" == "true" ]] && echo "floortiling:$2" || echo "floortiling:$2-nomodels"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile)        PROFILE="$2"; shift 2 ;;
    --no-models)         WITH_MODELS=false; shift ;;
    -t|--tag)            TAG="$2"; shift 2 ;;
    --hf-offline)        HF_OFFLINE="$2"; shift 2 ;;
    --mask2former)       OV[MASK2FORMER_VARIANT]="$2"; shift 2 ;;
    --oneformer)         OV[ONEFORMER_VARIANT]="$2"; shift 2 ;;
    --depth)             OV[DEPTH_VARIANT]="$2"; shift 2 ;;
    --yolo-world)        OV[YOLO_WORLD_VARIANT]="$2"; shift 2 ;;
    --grounding-dino)    OV[GROUNDING_DINO_VARIANT]="$2"; shift 2 ;;
    --sam)               OV[SAM_VARIANT]="$2"; shift 2 ;;
    --vitmatte)          OV[VITMATTE_VARIANT]="$2"; shift 2 ;;
    --no-cache)          NO_CACHE=1; shift ;;
    --dry-run)           DRY_RUN=1; shift ;;
    -i|--interactive)    INTERACTIVE=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Optional guided menu (only with -i; Enter keeps the current/default value).
if [[ -n "$INTERACTIVE" ]]; then
  ask() { local p="$1" d="$2" a; read -r -p "$p [$d]: " a; echo "${a:-$d}"; }
  echo "Floor Tiling — Docker build (interactive)"
  while :; do PROFILE="$(ask 'Profile (fast/balanced/quality/custom)' "$PROFILE")"
    case "$PROFILE" in fast|balanced|quality|custom) break ;; esac; done
  wm="$(ask 'Bake models into the image? (y/n)' "$([[ $WITH_MODELS == true ]] && echo y || echo n)")"
  [[ "$wm" =~ ^(y|yes|true|1)$ ]] && WITH_MODELS=true || WITH_MODELS=false
  if [[ "$WITH_MODELS" == "false" ]]; then
    echo "  No-models image: the profile/sizes you pick are RUNTIME DEFAULTS."
    echo "  Change them anytime without rebuilding, e.g.:"
    echo "    docker run -e DETECTION_PROFILE=quality -e SAM_VARIANT=base -v ftmodels:/app/models ..."
    echo "  The chosen models download into the mounted volume on first use."
  fi
  TAG="$(ask 'Image tag' "${TAG:-$(default_tag "$WITH_MODELS" "$PROFILE")}")"
  defhf="${HF_OFFLINE:-$([[ $WITH_MODELS == true ]] && echo 1 || echo 0)}"
  HF_OFFLINE="$(ask 'HF offline at runtime? (1=offline, 0=allow downloads)' "$defhf")"
  # Per-model sizes only matter for "custom"; fast/balanced/quality already
  # define every model. (Override an individual model on any profile via flags,
  # e.g. --sam base.)
  if [[ "$PROFILE" == "custom" ]]; then
    echo "  Custom profile — set each model size (Enter = settings.py default):"
    OV[MASK2FORMER_VARIANT]="$(ask '  Mask2Former (tiny/small/base/large)' "${OV[MASK2FORMER_VARIANT]:-}")"
    OV[ONEFORMER_VARIANT]="$(ask '  OneFormer (tiny/large/dinat_large)' "${OV[ONEFORMER_VARIANT]:-}")"
    OV[DEPTH_VARIANT]="$(ask '  Depth (small/base/large)' "${OV[DEPTH_VARIANT]:-}")"
    OV[YOLO_WORLD_VARIANT]="$(ask '  YOLO-World (s/m/l/x)' "${OV[YOLO_WORLD_VARIANT]:-}")"
    OV[GROUNDING_DINO_VARIANT]="$(ask '  Grounding DINO (tiny/base)' "${OV[GROUNDING_DINO_VARIANT]:-}")"
    OV[SAM_VARIANT]="$(ask '  SAM (slim50/slim77/base/large/huge)' "${OV[SAM_VARIANT]:-}")"
    OV[VITMATTE_VARIANT]="$(ask '  ViTMatte (small/base)' "${OV[VITMATTE_VARIANT]:-}")"
    # Drop any that were left blank so they don't override the profile.
    for k in "${!OV[@]}"; do [[ -z "${OV[$k]}" ]] && unset 'OV[$k]'; done
  fi
  nc="$(ask 'Build without cache? (y/n)' "$([[ -n $NO_CACHE ]] && echo y || echo n)")"
  [[ "$nc" =~ ^(y|yes)$ ]] && NO_CACHE=1 || NO_CACHE=""
fi

# Derived defaults.
if [[ -z "$TAG" ]]; then
  TAG="$(default_tag "$WITH_MODELS" "$PROFILE")"
fi
if [[ -z "$HF_OFFLINE" ]]; then
  [[ "$WITH_MODELS" == "true" ]] && HF_OFFLINE=1 || HF_OFFLINE=0
fi

ARGS=(build
  --build-arg "WITH_MODELS=$WITH_MODELS"
  --build-arg "DETECTION_PROFILE=$PROFILE"
  --build-arg "HF_HUB_OFFLINE=$HF_OFFLINE")
for k in "${!OV[@]}"; do ARGS+=(--build-arg "$k=${OV[$k]}"); done
[[ -n "$NO_CACHE" ]] && ARGS+=(--no-cache)
ARGS+=(-t "$TAG" .)

echo "Building $TAG (profile=$PROFILE with_models=$WITH_MODELS hf_offline=$HF_OFFLINE)"
echo "docker ${ARGS[*]}"
[[ -n "$DRY_RUN" ]] && exit 0

docker "${ARGS[@]}"
echo "Built $TAG"
