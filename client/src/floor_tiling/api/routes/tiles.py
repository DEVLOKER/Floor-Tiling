"""Tile application route — /api/apply-tiles."""

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from typing import Optional

# Cache of expensive per-image inference (depth map + M-LSD segments) keyed by a
# hash of the source image. Lets interactive adjustments (move/rotate/size) skip
# the ~1–2 s model inference and just re-render. Small LRU — a few rooms.
_GEOM_CACHE: "OrderedDict[bytes, tuple]" = OrderedDict()
_GEOM_CACHE_MAX = 8

from floor_tiling.config.settings import (
    DEFAULT_GROUT_THICKNESS,
    DEFAULT_PATTERN,
    DEFAULT_PERSPECTIVE_COMPRESSION,
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
from floor_tiling.patterns import PATTERN_FUNCTIONS
from floor_tiling.processors import apply_perspective_tiles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tiles"])


@router.post("/apply-tiles")
async def apply_tiles(
    request: Request,
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
    perspective_compression: float = Form(DEFAULT_PERSPECTIVE_COMPRESSION),
    algorithm: str = Form("vanishing"),
    auto_align: bool = Form(False),
    align_x1: float = Form(None),
    align_y1: float = Form(None),
    align_x2: float = Form(None),
    align_y2: float = Form(None),
    align2_x1: float = Form(None),
    align2_y1: float = Form(None),
    align2_x2: float = Form(None),
    align2_y2: float = Form(None),
    tile_texture: Optional[UploadFile] = File(None),
    tile_texture2: Optional[UploadFile] = File(None),
    source: Optional[UploadFile] = File(None),
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

        if algorithm not in ("vanishing", "depth"):
            algorithm = "vanishing"

        # Manual alignment lines (image coords), if provided.
        align_points = None
        if None not in (align_x1, align_y1, align_x2, align_y2):
            align_points = ((align_x1, align_y1), (align_x2, align_y2))
        align_points2 = None
        if None not in (align2_x1, align2_y1, align2_x2, align2_y2):
            align_points2 = ((align2_x1, align2_y1), (align2_x2, align2_y2))

        # ── Decode optional textures ───────────────────────────────────────
        texture_arr = None
        if tile_texture is not None:
            tex_bytes = await tile_texture.read()
            texture_arr = cv2.imdecode(np.frombuffer(tex_bytes, np.uint8), cv2.IMREAD_COLOR)

        texture_arr2 = None
        if tile_texture2 is not None:
            tex_bytes2 = await tile_texture2.read()
            texture_arr2 = cv2.imdecode(np.frombuffer(tex_bytes2, np.uint8), cv2.IMREAD_COLOR)

        # ── Decode optional lighting source (pristine original) ────────────
        # Sampling shadows/geometry from the original keeps re-tiling idempotent.
        lighting_source = None
        if source is not None:
            src_bytes = await source.read()
            lighting_source = cv2.imdecode(np.frombuffer(src_bytes, np.uint8), cv2.IMREAD_COLOR)

        # ── Depth (only for the depth algorithm) ───────────────────────────
        # Sampled on the pristine original so tile geometry matches the real floor.
        depth_map = None
        mlsd_segments = None
        if algorithm == "depth":
            # Cache key: the source image is constant across adjustments of the
            # same room, so depth + M-LSD are computed once and reused.
            key = hashlib.md5(src_bytes if source is not None else image_data).digest()
            cached = _GEOM_CACHE.get(key)
            if cached is not None:
                depth_map, mlsd_segments = cached
                _GEOM_CACHE.move_to_end(key)
            else:
                src_for_depth = lighting_source if lighting_source is not None else img
                rgb = cv2.cvtColor(src_for_depth, cv2.COLOR_BGR2RGB)
                depth_predictor = getattr(request.app.state, "depth_predictor", None)
                if depth_predictor is not None:
                    try:
                        depth_map = await asyncio.to_thread(depth_predictor.predict, rgb)
                    except Exception as exc:
                        logger.warning("Depth for tiling failed, falling back to vanishing: %s", exc)
                else:
                    logger.warning("Depth model unavailable; falling back to vanishing.")
                # M-LSD line segments → grid orientation cue (best-effort; the
                # renderer falls back to the floor-quad anchor if missing).
                mlsd_predictor = getattr(request.app.state, "mlsd_predictor", None)
                if mlsd_predictor is not None:
                    try:
                        mlsd_segments = await asyncio.to_thread(mlsd_predictor.predict, rgb)
                    except Exception as exc:
                        logger.warning("M-LSD for tiling failed: %s", exc)
                if depth_map is not None:
                    _GEOM_CACHE[key] = (depth_map, mlsd_segments)
                    if len(_GEOM_CACHE) > _GEOM_CACHE_MAX:
                        _GEOM_CACHE.popitem(last=False)

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
            perspective_compression=perspective_compression,
            lighting_source=lighting_source,
            algorithm=algorithm,
            depth=depth_map,
            mlsd_segments=mlsd_segments,
            align_points=align_points,
            align_points2=align_points2,
            auto_align=auto_align,
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
