"""Application settings and configuration"""

# Upload size limit
MAX_SIZE = 1024 * 1024 * 10  # 10 MB

# CORS origins
CORS_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

# SAM2 Model configuration
MODEL_CONFIG = {
    "variant": "tiny",
    "device": "cpu",
}

# Tile rendering constants
DEFAULT_REAL_WIDTH_CM = 400.0
DEFAULT_TILE_WIDTH = 30.0
DEFAULT_TILE_HEIGHT = 30.0
DEFAULT_GROUT_H_THICKNESS = 1
DEFAULT_GROUT_V_THICKNESS = 1
DEFAULT_PATTERN = "grid"

# Tile size constraints
TILE_WIDTH_MIN = 5.0
TILE_WIDTH_MAX = 200.0
TILE_HEIGHT_MIN = 5.0
TILE_HEIGHT_MAX = 200.0
GROUT_THICKNESS_MIN = 1
GROUT_THICKNESS_MAX = 20

# Depth calculation
DEPTH_MIN_CM = 50
DEPTH_MAX_CM = 800   # was probably 800+ — bring it down
DEPTH_FAR_RATIO_MIN = 0.05
DEPTH_FAR_RATIO_MAX = 0.99

# Image encoding
JPEG_QUALITY = 95
JPEG_SCALE_MAX_WIDTH = 1000
