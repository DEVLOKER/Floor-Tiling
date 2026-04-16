"""Tile application route — /api/apply-tiles."""

import json
import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from typing import Optional

from config.settings import (
    DEFAULT_GROUT_THICKNESS,
    DEFAULT_PATTERN,
    DEFAULT_ROTATION,
    DEFAULT_TILE_HEIGHT,
    DEFAULT_TILE_WIDTH,
    DEFAULT_TRANSLATE_X,
    DEFAULT_TRANSLATE_Y,
    GROUT_THICKNESS_MAX,
    GROUT_THICKNESS_MIN,
    JPEG_QUALITY,
    TILE_HEIGHT_MAX,
    TILE_HEIGHT_MIN,
    TILE_WIDTH_MAX,
    TILE_WIDTH_MIN,
)
from patterns import PATTERN_FUNCTIONS
from processors import apply_perspective_tiles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tiles"])


@router.post("/apply-tiles")
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
    """Apply a perspective-correct tile pattern onto the segmented floor region.

    Supports multiple patterns (grid, brick, diagonal, herringbone,
    checkerboard, diagonal_checkerboard) and optional texture images for
    both primary and secondary tile colors.

    Returns:
        JPEG image with tiles rendered onto the floor mask.
    """
    try:
        # ── Decode room image ──────────────────────────────────────────────
        image_data = await image.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return JSONResponse({"error": "Could not decode image"}, status_code=400)

        h, w = img.shape[:2]

        # ── Decode floor mask ──────────────────────────────────────────────
        mask_bytes = await mask.read()
        floor_mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((h, w))

        try:
            floor_mask = (floor_mask > 0).astype(np.uint8)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid mask"}, status_code=400)

        if floor_mask.shape != img.shape[:2]:
            floor_mask = cv2.resize(
                floor_mask, (w, h), interpolation=cv2.INTER_NEAREST
            )

        # ── Normalise parameters ───────────────────────────────────────────
        if tile_size is not None:
            tile_width = tile_height = tile_size

        tile_width = float(np.clip(tile_width, TILE_WIDTH_MIN, TILE_WIDTH_MAX))
        tile_height = float(np.clip(tile_height, TILE_HEIGHT_MIN, TILE_HEIGHT_MAX))
        grout_thickness = int(
            np.clip(grout_thickness, GROUT_THICKNESS_MIN, GROUT_THICKNESS_MAX)
        )

        if pattern not in PATTERN_FUNCTIONS:
            pattern = "grid"

        # ── Decode optional textures ───────────────────────────────────────
        texture_arr = None
        if tile_texture is not None:
            tex_bytes = await tile_texture.read()
            texture_arr = cv2.imdecode(np.frombuffer(tex_bytes, np.uint8), cv2.IMREAD_COLOR)

        texture_arr2 = None
        if tile_texture2 is not None:
            tex_bytes2 = await tile_texture2.read()
            texture_arr2 = cv2.imdecode(np.frombuffer(tex_bytes2, np.uint8), cv2.IMREAD_COLOR)

        # ── Render tiles ───────────────────────────────────────────────────
        result = apply_perspective_tiles(
            img,
            floor_mask,
            tile_color,
            tile_color2,
            grout_color,
            tile_width,
            tile_height,
            grout_thickness,
            grout_thickness,
            rotation,
            pattern,
            texture_arr,
            texture_arr2,
            translate_x=translate_x,
            translate_y=translate_y,
        )

        # ── Encode and return ──────────────────────────────────────────────
        ok, buf = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return JSONResponse({"error": "Encode failed"}, status_code=500)

        return Response(content=buf.tobytes(), media_type="image/jpeg")

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(exc)}, status_code=500)
