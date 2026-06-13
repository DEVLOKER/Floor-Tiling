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
