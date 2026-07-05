"""Application settings & configuration.

All tunables live here. Sections:

    1. SERVER & I/O            — uploads, CORS, image encoding
    2. AI MODEL SIZES          — speed↔quality variant of every model (one place)
    3. SURFACE SEGMENTATION    — which segmenter(s) detect floor/wall/ceiling
    4. OBJECT EXCLUSION (semantic) — keep wall objects out of painting
    5. OBJECT EXCLUSION (open-vocab) — catch objects ADE20K can't name (AC, …)
    6. WALL PAINTING           — colour, finish, matting, edge snapping
    7. FLOOR TILING            — tile/grout defaults & limits
    8. DEPTH GEOMETRY (tiling) — depth→distance mapping for perspective tiles

Changing any model VARIANT (section 2) re-downloads that model on next start;
unknown values fall back to the manager's default.

Every model-size knob (DETECTION_PROFILE + the per-model *_VARIANT values) and the
key feature flags can be overridden by an environment variable of the same name.
This is what lets a Docker image be built/run for a chosen profile without editing
this file (see the project Dockerfile / docker-compose files).
"""

import os


def _env(name: str, default: str) -> str:
    """Read a string from the environment, treating empty/whitespace as absent.

    Docker exposes every declared ARG to RUN as an environment variable — an
    unset one arrives as "" — so a plain os.environ.get would read "" and wipe
    out the intended default. Coalescing empty → default avoids that trap.
    """
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    return val.strip()


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean from the environment ("1/true/yes/on" → True)."""
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ═════════════════════════════════════════════════════════════════════════════
# 1. SERVER & I/O
# ═════════════════════════════════════════════════════════════════════════════
MAX_UPLOAD_SIZE_BYTES = 1024 * 1024 * 10  # 10 MB upload limit

CORS_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://127.0.0.1:8000",
    "https://localhost:8000",
]

# Output JPEG quality, and the max width images are processed/returned at.
JPEG_QUALITY = 95
JPEG_SCALE_MAX_WIDTH = 1000


# ═════════════════════════════════════════════════════════════════════════════
# 2. AI MODEL SIZES  (the speed ↔ quality dial — bigger = better, slower)
# ═════════════════════════════════════════════════════════════════════════════
# ONE dial sets every model's size at once. Changing it re-downloads the affected
# models on next server start.
#   "fast"     — smallest models, quickest detection
#   "balanced" — mid sizes, good speed/quality trade-off
#   "quality"  — largest models, best masks (slowest)
#   "custom"   — ignore the profile and use the per-model *_VARIANT values below
# (env override: DETECTION_PROFILE)
DETECTION_PROFILE = _env("DETECTION_PROFILE", "quality")  # "fast" | "balanced" | "quality" | "custom"

# Per-model size variants. Used as-is when DETECTION_PROFILE = "custom";
# OVERWRITTEN by the chosen profile otherwise (see the override block below).
# Each can also be overridden by an env var of the same name.
MASK2FORMER_VARIANT = _env("MASK2FORMER_VARIANT", "tiny")      # "tiny" | "small" | "base" | "large"   (floor/wall/ceiling)
ONEFORMER_VARIANT = _env("ONEFORMER_VARIANT", "tiny")          # "tiny" | "large" | "dinat_large"      (dinat needs `natten`)
DEPTH_VARIANT = _env("DEPTH_VARIANT", "base")                  # "small" | "base" | "large"            (wall-plane split)
YOLO_WORLD_VARIANT = _env("YOLO_WORLD_VARIANT", "x")           # "s" | "m" | "l" | "x"                 (x≈140MB best recall, s≈25MB fastest)
GROUNDING_DINO_VARIANT = _env("GROUNDING_DINO_VARIANT", "tiny")  # "tiny" | "base"                     (only if detector=grounding_dino)
SAM_VARIANT = _env("SAM_VARIANT", "slim77")                    # "slim50" | "slim77" (tiny/fast) | "base" | "large" | "huge"
VITMATTE_VARIANT = _env("VITMATTE_VARIANT", "small")           # "small" | "base"                      (paint-edge matting)

# Profile presets — each maps every model to a size. Edit a preset to retune it.
_DETECTION_PROFILES = {
    "fast": {
        "MASK2FORMER_VARIANT": "tiny",  "ONEFORMER_VARIANT": "tiny",
        "DEPTH_VARIANT": "small",       "YOLO_WORLD_VARIANT": "s",
        "GROUNDING_DINO_VARIANT": "tiny", "SAM_VARIANT": "slim50",
        "VITMATTE_VARIANT": "small",
    },
    "balanced": {
        "MASK2FORMER_VARIANT": "base",  "ONEFORMER_VARIANT": "tiny",
        "DEPTH_VARIANT": "base",        "YOLO_WORLD_VARIANT": "m",
        "GROUNDING_DINO_VARIANT": "tiny", "SAM_VARIANT": "slim77",
        "VITMATTE_VARIANT": "small",
    },
    "quality": {
        "MASK2FORMER_VARIANT": "large", "ONEFORMER_VARIANT": "large",
        "DEPTH_VARIANT": "large",       "YOLO_WORLD_VARIANT": "x",
        "GROUNDING_DINO_VARIANT": "base", "SAM_VARIANT": "base",
        "VITMATTE_VARIANT": "base",
    },
}
# Apply the profile (a known name overrides the per-model values above; "custom"
# or any unknown value leaves them untouched). An explicit per-model env var still
# wins over the profile, so e.g. DETECTION_PROFILE=fast + SAM_VARIANT=base works.
if DETECTION_PROFILE in _DETECTION_PROFILES:
    for _k, _v in _DETECTION_PROFILES[DETECTION_PROFILE].items():
        globals()[_k] = _env(_k, _v)


# ═════════════════════════════════════════════════════════════════════════════
# 3. SURFACE SEGMENTATION  (which model(s) detect floor / wall / ceiling)
# ═════════════════════════════════════════════════════════════════════════════

# ── Master switch ─────────────────────────────────────────────────────────────
# Set False to disable ALL wall and ceiling painting (detection, plane splitting,
# object exclusion, paint router). Only floor tiling remains active.
# Wall/ceiling detection is still imperfect — flip this back to True once the
# quality is good enough to ship.
WALL_PAINT_ENABLED = _env_bool("WALL_PAINT_ENABLED", True)

# Restart the server after changing. (Sizes are in section 2.)
#   both True → ensemble (union of the two) — best wall coverage, slower
#   one True  → that model alone
SEG_USE_MASK2FORMER = _env_bool("SEG_USE_MASK2FORMER", True)
SEG_USE_ONEFORMER = _env_bool("SEG_USE_ONEFORMER", True)


# ═════════════════════════════════════════════════════════════════════════════
# 4. OBJECT EXCLUSION — semantic  (keep wall objects out of painting)
# ═════════════════════════════════════════════════════════════════════════════
# When painting walls/ceiling, never cover objects mounted on them. We detect
# these ADE20K classes by label keyword and subtract them from the wall/ceiling
# masks. Add/remove keywords to tune (matched as case-insensitive substrings).
PAINT_IGNORE_WALL_OBJECTS = _env_bool("PAINT_IGNORE_WALL_OBJECTS", True)
WALL_OBJECT_KEYWORDS = (
    "window", "door", "curtain", "blind", "painting", "mirror",
    "lamp", "light", "chandelier", "sconce", "fan", "radiator",
    "switch", "air conditioner", "fireplace", "television", "screen",
    "clock", "shelf", "bookcase", "stairs", "stairway",
    # Built-in furniture & fixtures that occlude a wall and must never be
    # painted over (kitchen/bath especially).
    "cabinet", "wardrobe", "closet", "counter", "sink", "stove",
    "oven", "microwave", "refrigerator", "hood", "towel", "railing",
    "kitchen island",
)
# Of the excluded classes above, these are the "openings" (doors & windows and
# their coverings) — a SEPARATE paint category from the wall objects/fixtures, so
# the UI can offer two independent "paint anyway" toggles. Matched as substrings;
# must be a subset of WALL_OBJECT_KEYWORDS. Everything else excluded above is the
# "objects/fixtures" category.
OPENING_KEYWORDS = ("window", "door", "curtain", "blind")
# Grow detected objects slightly (fraction of the image's long edge) so their
# frames/edges (e.g. window casing) are excluded too.
WALL_OBJECT_DILATE_FRAC = 0.003
# After detection, grow wall planes into the unpainted gaps around objects (tile
# between the wall mask and an object, or wall the model missed) up to this many
# px, bounded by the TIGHT object mask / floor / ceiling. Fixes the unpainted
# halos around objects on textured walls. 0 disables.
WALL_FILL_GAPS_PX = 18


# ═════════════════════════════════════════════════════════════════════════════
# 5. OBJECT EXCLUSION — open-vocabulary  (objects ADE20K has no class for)
# ═════════════════════════════════════════════════════════════════════════════
# ADE20K segmentation lacks classes for many wall objects (air conditioner, pipe,
# socket, thermostat, vent…). An open-vocab detector finds anything named in the
# prompt below; SAM turns each detection into a pixel-perfect mask. Offline.
# NOTE: this is DETECTION (for showing/excluding). Whether they're skipped while
# painting is PAINT_IGNORE_WALL_OBJECTS (section 4). Set False to skip loading the
# detector + SAM (faster start, semantic objects only). Sizes are in section 2.
USE_OPEN_VOCAB_OBJECTS = _env_bool("USE_OPEN_VOCAB_OBJECTS", True)
# Which detector finds the objects:
#   "yolo_world"     → YOLO-World, ~0.8 s/image on CPU (fast, default)
#   "grounding_dino" → Grounding DINO, ~7 s/image (slightly higher recall)
OPEN_VOCAB_DETECTOR = _env("OPEN_VOCAB_DETECTOR", "yolo_world")
# YOLO-World confidence gate (its scores run lower than Grounding DINO's). Kept
# low for recall on small fixtures (sockets); the semantic model + box-area
# filter guard against the occasional false box.
YOLO_WORLD_CONF = 0.05
# Lower-case, period-separated phrases. ONLY list things the semantic segmenter
# CAN'T (no ADE20K class) — lamps/mirrors/tv/fan/radiator/clock are already in
# WALL_OBJECT_KEYWORDS, so listing them here just adds false positives (e.g. a
# lit ceiling soffit grounded as "wall lamp"). Keep this to the real gaps.
OPEN_VOCAB_OBJECT_PROMPT = (
    "air conditioner. electric socket. power outlet. light switch. "
    "thermostat. air vent. wall vent. exhaust vent. pipe. water pipe. "
    "drain pipe. conduit. smoke detector. fuse box. electrical panel. "
    "junction box. intercom. doorbell. speaker. towel rail."
)
# Grounding DINO confidence gates (box / text).
OPEN_VOCAB_BOX_THRESHOLD = 0.30
OPEN_VOCAB_TEXT_THRESHOLD = 0.25
# Drop any single detection covering more than this fraction of the image — a
# huge box is almost always a mis-grounding onto the whole wall.
OPEN_VOCAB_MAX_BOX_FRAC = 0.45


# ═════════════════════════════════════════════════════════════════════════════
# 6. WALL PAINTING
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_PAINT_COLOR = "#C8D6E5"
DEFAULT_PAINT_FINISH = "matte"
PAINT_FINISHES = ("matte", "satin", "gloss")

# ── Edge matting (ViTMatte) ──────────────────────────────────────────────────
# Semantic masks can't resolve fine foliage, so painting can leave faint "ghost"
# leaf edges. ViTMatte refines the wall mask into a soft alpha that captures thin
# edges; the paint route composites with it so foliage stays clean. The alpha
# depends only on image+mask (not colour), so it's cached across recolours.
# (Model size = VITMATTE_VARIANT in section 2.)
PAINT_REFINE_MATTING = _env_bool("PAINT_REFINE_MATTING", False)
MATTING_MAX_SIDE = 768          # matte at this long-side px (CPU speed vs detail)
MATTING_FG_ERODE = 9            # sure-foreground erosion (px)
# Keep the boundary "unknown" band SMALL so hard-edged objects (sockets, frames)
# on textured walls stay crisp instead of getting a soft colour rim. Foliage is
# handled by the colour cue below, not a wide band.
MATTING_BG_DILATE = 5
# LAB colour distance: pixels inside the mask this far from the wall's own colour
# are demoted to "unknown" so ViTMatte can carve out foliage detached from the
# boundary (ghost leaves) — this, not the band, is what fixes ghost leaves.
# 0 disables. Higher = only stronger outliers demoted.
MATTING_COLOR_DEMOTE_T = 22.0

# ── Architectural edge snapping ──────────────────────────────────────────────
# After edge-aware refinement, snap the wall/ceiling mask boundaries onto the
# straight architectural lines detected by M-LSD (wall↔ceiling, wall↔floor,
# corners). Removes residual wavy boundaries on textureless walls without
# bridging real openings (moves are distance-clamped).
SNAP_EDGES_TO_LINES = True


# ═════════════════════════════════════════════════════════════════════════════
# 7. FLOOR TILING
# ═════════════════════════════════════════════════════════════════════════════
# Defaults
DEFAULT_REAL_WIDTH_CM = 300.0   # assumed real-world width of the floor (scale ref)
DEFAULT_TILE_WIDTH = 30.0       # cm
DEFAULT_TILE_HEIGHT = 30.0      # cm
DEFAULT_GROUT_THICKNESS = 1
DEFAULT_PATTERN = "grid"
DEFAULT_ROTATION = 0.0
DEFAULT_TRANSLATE_X = 0.0
DEFAULT_TRANSLATE_Y = 0.0
# Perspective compression (0.0 = natural/linear perspective, 1.0 = maximum).
# Default 0.0 keeps real-world foreshortening — tiles shrink naturally into
# depth. Higher values enlarge tiles & reduce row count, which reads as fake
# (giant tiles, flat-looking floor), so it's opt-in via the UI slider.
DEFAULT_PERSPECTIVE_COMPRESSION = 50.0

# UI constraints (slider ranges)
TILE_WIDTH_MIN = 5.0
TILE_WIDTH_MAX = 200.0
TILE_HEIGHT_MIN = 5.0
TILE_HEIGHT_MAX = 200.0
GROUT_THICKNESS_MIN = 0
GROUT_THICKNESS_MAX = 20


# ═════════════════════════════════════════════════════════════════════════════
# 8. DEPTH GEOMETRY  (depth→distance mapping for perspective tiling)
# ═════════════════════════════════════════════════════════════════════════════
DEPTH_MIN_CM = 50
DEPTH_MAX_CM = 900   # depth_ratio ceiling is 2.5 × DEFAULT_REAL_WIDTH_CM (300 cm)
DEPTH_FAR_RATIO_MIN = 0.05
DEPTH_FAR_RATIO_MAX = 0.99
