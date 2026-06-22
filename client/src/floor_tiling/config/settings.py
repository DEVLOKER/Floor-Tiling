"""Application settings and configuration"""
# Upload size limit
MAX_UPLOAD_SIZE_BYTES = 1024 * 1024 * 10  # 10 MB
# CORS origins
CORS_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://127.0.0.1:8000",
    "https://localhost:8000",
]
# ── Segmentation model selection (A/B testing) ──────────────────────────────
# Toggle which segmentation model(s) feed detection, then restart the server.
#   both True  → ensemble (union of the two) — best coverage
#   one True   → use that model alone
SEG_USE_MASK2FORMER = False
SEG_USE_ONEFORMER = True

# ── Wall-object exclusion (painting) ────────────────────────────────────────
# When painting walls/ceiling, never cover objects mounted on them. We detect
# these ADE20K classes by label keyword and subtract them from the wall/ceiling
# masks. Add/remove keywords to tune (matched as case-insensitive substrings).
PAINT_IGNORE_WALL_OBJECTS = True
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

# ── Open-vocabulary wall-object exclusion (Grounding DINO + SAM) ─────────────
# ADE20K segmentation lacks classes for many wall objects (air conditioner,
# pipe, socket, thermostat, vent…), so they get painted over. Grounding DINO
# detects anything named in the prompt below; SAM turns each detection into a
# pixel-perfect mask that is excluded from painting (no halo). Offline models.
USE_OPEN_VOCAB_OBJECTS = True
# Which open-vocab detector finds the objects (SAM then cuts them precisely):
#   "yolo_world"     → YOLO-World, ~0.8 s/image on CPU (fast, default)
#   "grounding_dino" → Grounding DINO, ~7 s/image (slightly higher recall)
OPEN_VOCAB_DETECTOR = "yolo_world"
# YOLO-World confidence gate (its scores run lower than Grounding DINO's). Kept
# low for recall on small fixtures (sockets); the semantic model + box-area
# filter guard against the occasional false box.
YOLO_WORLD_CONF = 0.05
# Lower-case, period-separated phrases. Focus on wall-mounted things that the
# semantic segmenter misses or cuts poorly.
OPEN_VOCAB_OBJECT_PROMPT = (
    "air conditioner. radiator. heater. electric socket. power outlet. "
    "light switch. thermostat. wall vent. pipe. television. picture frame. "
    "mirror. wall clock. speaker. smoke detector. wall lamp. sconce. "
    "fan. fuse box. intercom. towel rail."
)
# Grounding DINO confidence gates (box / text).
OPEN_VOCAB_BOX_THRESHOLD = 0.30
OPEN_VOCAB_TEXT_THRESHOLD = 0.25
# Drop any single detection covering more than this fraction of the image — a
# huge box is almost always a mis-grounding onto the whole wall.
OPEN_VOCAB_MAX_BOX_FRAC = 0.45

# ── Paint edge matting (ViTMatte) ───────────────────────────────────────────
# Semantic masks can't resolve fine foliage, so painting leaves faint "ghost"
# leaf edges. ViTMatte refines the wall mask into a soft alpha that captures
# thin edges; the paint route composites with it so foliage stays clean. The
# alpha depends only on image+mask (not colour), so it's cached across recolours.
PAINT_REFINE_MATTING = True
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

# ── Architectural edge snapping (painting) ──────────────────────────────────
# After edge-aware refinement, snap the wall/ceiling mask boundaries onto the
# straight architectural lines detected by M-LSD (wall↔ceiling, wall↔floor,
# corners). This removes the residual wavy boundaries on textureless walls
# without bridging real openings (moves are distance-clamped).
SNAP_EDGES_TO_LINES = True

# Tile rendering constants
DEFAULT_REAL_WIDTH_CM = 300.0
DEFAULT_TILE_WIDTH = 30.0
DEFAULT_TILE_HEIGHT = 30.0
DEFAULT_GROUT_THICKNESS = 1
DEFAULT_PATTERN = "grid"
DEFAULT_ROTATION = 0.0
DEFAULT_TRANSLATE_X = 0.0
DEFAULT_TRANSLATE_Y = 0.0
# Perspective compression (0.0 = natural/linear perspective, 1.0 = maximum).
# Default 0.0 keeps real-world foreshortening — tiles shrink naturally into
# depth.  Higher values enlarge tiles & reduce row count, which reads as fake
# (giant tiles, flat-looking floor), so it's opt-in via the UI slider.
DEFAULT_PERSPECTIVE_COMPRESSION = 0.0
# Tile size constraints
TILE_WIDTH_MIN = 5.0
TILE_WIDTH_MAX = 200.0
TILE_HEIGHT_MIN = 5.0
TILE_HEIGHT_MAX = 200.0
GROUT_THICKNESS_MIN = 0
GROUT_THICKNESS_MAX = 20
# Wall painting
DEFAULT_PAINT_COLOR = "#C8D6E5"
DEFAULT_PAINT_FINISH = "matte"
PAINT_FINISHES = ("matte", "satin", "gloss")
# Depth calculation
DEPTH_MIN_CM = 50
DEPTH_MAX_CM = 900   # depth_ratio ceiling is 2.5 × DEFAULT_REAL_WIDTH_CM (300 cm)
DEPTH_FAR_RATIO_MIN = 0.05
DEPTH_FAR_RATIO_MAX = 0.99
# Image encoding
JPEG_QUALITY = 95
JPEG_SCALE_MAX_WIDTH = 1000
