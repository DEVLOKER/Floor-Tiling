from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = 100 * 1024 * 1024  # 100 MB
"""Floor Tile Visualizer API

A FastAPI application for interactive floor tile visualization using SAM 2
for floor segmentation and perspective-correct homography-based tile rendering.
"""
import json
import io
import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import torch

from config.settings import (
    MAX_SIZE,
    CORS_ORIGINS,
    TILE_WIDTH_MIN,
    TILE_WIDTH_MAX,
    TILE_HEIGHT_MIN,
    TILE_HEIGHT_MAX,
    GROUT_THICKNESS_MIN,
    GROUT_THICKNESS_MAX,
    JPEG_QUALITY,
)
from ml_models import get_sam2_predictor
from processors import apply_perspective_tiles
from patterns import PATTERN_FUNCTIONS

# ─────────────────────────────────────────────────────────────────────────────
# Application Setup
# ─────────────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="Floor Tile Visualizer",
    description="SAM 2 powered floor segmentation and tile visualization",
    version="1.0.0"
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

# Initialize SAM2 model
predictor = get_sam2_predictor()


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/segment-floor")
async def segment_floor(
    image: UploadFile = File(...),
    click_x: float = Form(...),
    click_y: float = Form(...)
):
    """Segment floor region using SAM 2 based on click point.
    
    Args:
        image: Room image file
        click_x: X coordinate of click point
        click_y: Y coordinate of click point
    
    Returns:
        JSON with floor mask and confidence score
    """
    try:
        image_data = await image.read()
        pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        image_np = np.array(pil_image)
        
        predictor.set_image(image_np)
        input_point = np.array([[click_x, click_y]], dtype=np.float32)
        input_label = np.array([1], dtype=np.int32)
        
        with torch.inference_mode():
            masks, scores, logits = predictor.predict(
                point_coords=input_point,
                point_labels=input_label,
                multimask_output=True
            )
        
        best = int(np.argmax(scores))
        mask = masks[best]
        if hasattr(mask, 'cpu'):
            mask = mask.cpu().numpy()
        mask = np.where(np.isnan(mask), 0, mask)
        
        return JSONResponse({
            "mask": mask.astype(float).tolist(),
            "score": float(scores[best])
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/apply-tiles")
async def apply_tiles(
    image: UploadFile = File(...),
    # mask: str = Form(...), # Changed to UploadFile for binary data
    mask: UploadFile = File(...), # Changed from Form to File
    tile_width: float = Form(30),
    tile_height: float = Form(30),
    tile_size: float = Form(None),
    tile_color: str = Form("#E8D1B5"),
    tile_color2: str = Form("#333333"),
    grout_color: str = Form("#A9A9A9"),
    grout_h_thickness: int = Form(1),
    grout_v_thickness: int = Form(1),
    pattern: str = Form("grid"),
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
        grout_h_thickness: Horizontal grout thickness in pixels
        grout_v_thickness: Vertical grout thickness in pixels
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
        grout_h_thickness = int(np.clip(
            grout_h_thickness, GROUT_THICKNESS_MIN, GROUT_THICKNESS_MAX
        ))
        grout_v_thickness = int(np.clip(
            grout_v_thickness, GROUT_THICKNESS_MIN, GROUT_THICKNESS_MAX
        ))

        # Validate pattern
        if pattern not in PATTERN_FUNCTIONS:
            pattern = "grid"

        # Apply tiles
        result = apply_perspective_tiles(
            img, floor_mask,
            tile_color, tile_color2, grout_color,
            tile_width, tile_height,
            grout_h_thickness, grout_v_thickness,
            pattern
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


@app.get("/")
async def root():
    """Root endpoint.
    
    Returns:
        API information
    """
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
    # python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload --limit-max-requests 10485760
    # python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload --h11-max-incomplete-event-size 10485760
    # uvicorn.run(
    #     app,
    #     host="0.0.0.0",
    #     port=8000,
    #     log_level="info",
    #     limit_max_requests=MAX_SIZE,
    #     limit_max_requests_jitter=MAX_SIZE,
    #     # This handles the large 'mask' string event size
    #     h11_max_incomplete_event_size=MAX_SIZE, 
    # )
    uvicorn.run(
        "server:app",       # Must be a string path "filename:app" for reload to work
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,        # Enables auto-reload on code changes
        limit_max_requests=MAX_SIZE,
        limit_max_requests_jitter=MAX_SIZE,
        # This handles the large 'mask' string event size
        h11_max_incomplete_event_size=100 * 1024 * 1024 
    )