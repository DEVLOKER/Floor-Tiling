from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = 10 * 1024 * 1024  # 10 MB
"""Floor Tile Visualizer API

A FastAPI application for interactive floor tile visualization using
Mask2Former for floor segmentation and perspective-correct homography-based tile rendering.
"""
import asyncio
import json
import io
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import numpy as np
import cv2
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse, Response, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import torch
from typing import Optional

from config.settings import (
    MAX_SIZE,
    CORS_ORIGINS,
    TILE_WIDTH_MIN,
    TILE_WIDTH_MAX,
    TILE_HEIGHT_MIN,
    TILE_HEIGHT_MAX,
    GROUT_THICKNESS_MIN,
    GROUT_THICKNESS_MAX,
    DEFAULT_GROUT_THICKNESS,
    DEFAULT_TILE_WIDTH,
    DEFAULT_TILE_HEIGHT,
    DEFAULT_TRANSLATE_X,
    DEFAULT_TRANSLATE_Y,
    DEFAULT_ROTATION,
    JPEG_QUALITY,
    DEFAULT_PATTERN
)
from utils import verify_license, LicenseError
from mask2former.mask2former import get_mask2former_predictor
from processors import apply_perspective_tiles
from patterns import PATTERN_FUNCTIONS

# Add repo root to sys.path so `shared` package is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# Configure logging so logger.info() messages actually show up
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# License dependency — runs on EVERY request
# ─────────────────────────────────────────────────────────────────────────────

async def require_license():
    """FastAPI dependency: re-verify USB license on every API call."""
    try:
        # verify_license()
        pass
    except LicenseError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

# ─────────────────────────────────────────────────────────────────────────────
# Application Setup
# ─────────────────────────────────────────────────────────────────────────────

# Predictors — populated after license check passes
mask2former_predictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mask2former_predictor

    # ── 1. License check ──────────────────────────────────────────────────────
    try:
        verify_license()
    except LicenseError as exc:
        logger.critical("License check failed: %s", exc)
        sys.exit(1)

    # ── 2. Load Models ────────────────────────────────────────────────────────
    try:
        mask2former_predictor = await asyncio.to_thread(get_mask2former_predictor)
        logger.info("Mask2Former model ready.")
    except Exception as e:
        logger.error("Failed to load Mask2Former: %s", e, exc_info=True)

    yield  # ── server is running ─────────────────────────────────────────────


app = FastAPI(
    title="Floor Tile Visualizer",
    description="Floor segmentation and tile visualization",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(require_license)],
)

# Configure upload size limit
app.state.limit_max_request_body = MAX_SIZE

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (CSS, JS, images) under /static
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────


# Enhanced endpoint: use both SAM and Mask2Former for robust wall detection
@app.post("/api/auto-detect")
async def auto_detect_features(
    image: UploadFile = File(...)
):
    image_data = await image.read()

    async def event_stream():
        import struct, gzip, base64

        def sse(obj):
            return f"data: {json.dumps(obj)}\n\n"

        try:
            yield sse({'step': 1, 'total': 3, 'message': "Chargement de l'image…"})

            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np = np.array(pil_image)
            h, w = image_np.shape[:2]

            # ── Stage 1: Mask2Former ─────────────────────────────────────────
            yield sse({'step': 2, 'total': 3, 'message': 'Détection sémantique (Mask2Former)…'})

            floor_mask, wall_mask = await asyncio.to_thread(
                mask2former_predictor.predict, image_np
            )

            # ── Stage 2: Post-processing ────────────────────────────────────
            yield sse({'step': 3, 'total': 3, 'message': 'Finalisation…'})

            def get_centroid(mask):
                coords = np.argwhere(mask > 0)
                if len(coords) == 0:
                    return None
                y, x = np.mean(coords, axis=0)
                return {"x": float(x), "y": float(y)}

            labels = []
            floor_center = get_centroid(floor_mask)
            if floor_center:
                labels.append({"text": "Floor", "x": floor_center["x"], "y": floor_center["y"], "type": "floor", "id": "floor"})

            num_labels, labeled_walls, stats, centroids = cv2.connectedComponentsWithStats(
                wall_mask.astype(np.uint8), connectivity=8
            )
            for i in range(1, num_labels):
                if stats[i, cv2.CC_STAT_AREA] < 500:
                    continue
                labels.append({
                    "text": "Wall",
                    "x": float(centroids[i][0]),
                    "y": float(centroids[i][1]),
                    "type": "wall",
                    "id": str(i)
                })

            # ── Build binary payload ────────────────────────────────────────
            labels_json = json.dumps(labels).encode("utf-8")
            floor_bytes = floor_mask.astype(np.uint8).tobytes()
            wall_bytes = labeled_walls.astype(np.uint8).tobytes()
            header = struct.pack("<III", len(labels_json), h, w)
            raw = header + labels_json + floor_bytes + wall_bytes
            compressed = gzip.compress(raw, compresslevel=1)
            b64 = base64.b64encode(compressed).decode("ascii")

            yield sse({'step': 'done', 'binary': b64})

        except Exception as e:
            logger.error("Auto-detect error: %s", e, exc_info=True)
            yield sse({'step': 'error', 'message': str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/apply-tiles")
async def apply_tiles(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    tile_width: float = Form(DEFAULT_TILE_WIDTH),
    tile_height: float = Form(DEFAULT_TILE_HEIGHT),
    tile_size: float = Form(None),
    tile_color: str = Form("#E8D1B5"),
    tile_color2: str = Form("#333333"),
    grout_color: str = Form("#A9A9A9"),
    grout_thickness: int = Form(DEFAULT_GROUT_THICKNESS),
    translate_x: float = Form(DEFAULT_TRANSLATE_X),
    translate_y: float = Form(DEFAULT_TRANSLATE_Y),
    rotation: float = Form(DEFAULT_ROTATION),
    pattern: str = Form(DEFAULT_PATTERN),
    tile_texture: Optional[UploadFile] = File(None),
    tile_texture2: Optional[UploadFile] = File(None),
):
    """Apply tile pattern to segmented floor region.
    
    Uses homography-based perspective-correct tile rendering with
    support for multiple patterns and independent grout thickness.
    
    Args:
        image: Room image file
        mask: JSON string of binary floor mask
        tile_width: Real-world tile width in cm
        tile_height: Real-world tile height in cm
        tile_size: Legacy parameter - sets both width and height
        tile_color: Hex color for primary tiles
        tile_color2: Hex color for secondary tiles (checkerboard)
        grout_color: Hex color for grout lines
        grout_thickness: Grout thickness in pixels (applied to both directions)
        pattern: Tile pattern (grid, brick, diagonal, herringbone, checkerboard, diagonal_checkerboard)
    
    Returns:
        JPEG image with applied tiles
    """
    try:
        # Decode image
        image_data = await image.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return JSONResponse(
                {"error": "Could not decode image"},
                status_code=400
            )
        
        h, w = img.shape[:2]
        # 2. Read Mask binary and reshape
        mask_bytes = await mask.read()
        # Convert flat binary back to 2D array using image dimensions
        floor_mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((h, w))
        
        # ensure it's a binary 0/1 mask
        try:
            floor_mask = (floor_mask > 0).astype(np.uint8)
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "Invalid mask"},
                status_code=400
            )

        # Resize mask if needed
        if floor_mask.shape != img.shape[:2]:
            floor_mask = cv2.resize(
                floor_mask,
                (img.shape[1], img.shape[0]),
                interpolation=cv2.INTER_NEAREST
            )

        # Handle legacy tile_size parameter
        if tile_size is not None:
            tile_width = tile_height = tile_size

        # Validate and clamp parameters
        tile_width = float(np.clip(tile_width, TILE_WIDTH_MIN, TILE_WIDTH_MAX))
        tile_height = float(np.clip(tile_height, TILE_HEIGHT_MIN, TILE_HEIGHT_MAX))
        grout_thickness = int(np.clip(
            grout_thickness, GROUT_THICKNESS_MIN, GROUT_THICKNESS_MAX
        ))

        # Validate pattern
        if pattern not in PATTERN_FUNCTIONS:
            pattern = "grid"

        # Decode texture (optional)
        texture_arr = None
        if tile_texture is not None:
            tex_bytes   = await tile_texture.read()
            texture_arr = cv2.imdecode(np.frombuffer(tex_bytes, np.uint8), cv2.IMREAD_COLOR)

        # Decode secondary (dark) texture (optional, checker patterns)
        texture_arr2 = None
        if tile_texture2 is not None:
            tex_bytes2    = await tile_texture2.read()
            texture_arr2  = cv2.imdecode(np.frombuffer(tex_bytes2, np.uint8), cv2.IMREAD_COLOR)

        # Apply tiles
        result = apply_perspective_tiles(
            img, floor_mask,
            tile_color, tile_color2, grout_color,
            tile_width, tile_height,
            grout_thickness, grout_thickness,
            rotation,
            pattern,
            texture_arr,
            texture_arr2,
            translate_x=translate_x,
            translate_y=translate_y,
        )

        # Encode result
        ok, buf = cv2.imencode(
            '.jpg',
            result,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        if not ok:
            return JSONResponse(
                {"error": "Encode failed"},
                status_code=500
            )
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    """Health check endpoint.
    
    Returns:
        Status information
    """
    return {
        "status": "healthy",
        "device": "cpu",
        "cuda_available": torch.cuda.is_available()
    }


@app.get("/", response_class=FileResponse)
async def root():
    """Serve the frontend UI."""
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "message": "Floor Tile Visualizer API",
        "status": "running",
        "docs": "/docs"
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # from shared.utils.ssl_cert import ensure_ssl_cert

    # ssl_certfile, ssl_keyfile = ensure_ssl_cert()
    _frozen = getattr(sys, "frozen", False)  # True when running as PyInstaller exe

    uvicorn.run(
        app if _frozen else "server:app",  # string form required for reload; app object for frozen
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=not _frozen,     # reload=True dev only; breaks frozen exe (spawn loop)
        # ssl_certfile=ssl_certfile,
        # ssl_keyfile=ssl_keyfile,
        limit_max_requests=MAX_SIZE,
        limit_max_requests_jitter=MAX_SIZE,
        # This handles the large 'mask' string event size
        h11_max_incomplete_event_size=100 * 1024 * 1024
    )

# run from command line:
# python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload --h11-max-incomplete-event-size 10485760
