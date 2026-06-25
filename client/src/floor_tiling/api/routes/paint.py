"""Wall painting route — /api/apply-paint."""

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from floor_tiling.config.settings import (
    DEFAULT_PAINT_COLOR,
    DEFAULT_PAINT_FINISH,
    JPEG_QUALITY,
    PAINT_FINISHES,
    PAINT_REFINE_MATTING,
    MATTING_MAX_SIDE,
    MATTING_FG_ERODE,
    MATTING_BG_DILATE,
    MATTING_COLOR_DEMOTE_T,
)
from floor_tiling.processors import apply_wall_paint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["paint"])

# Cache the (colour-independent) alpha matte so recolouring the same wall doesn't
# re-run ViTMatte. Keyed by a hash of the mask + lighting source.
_MATTE_CACHE: "OrderedDict[str, np.ndarray]" = OrderedDict()
_MATTE_CACHE_MAX = 8


@router.post("/apply-paint")
async def apply_paint(
    request: Request,
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    paint_color: str = Form(DEFAULT_PAINT_COLOR),
    finish: str = Form(DEFAULT_PAINT_FINISH),
    opacity: float = Form(0.8),
    texture_scale: float = Form(1.3),
    light_strength: float = Form(1.0),
    saturation: float = Form(0.86),
    paint_objects: bool = Form(False),
    source: Optional[UploadFile] = File(None),
    paint_texture: Optional[UploadFile] = File(None),
):
    """Repaint the masked wall region with a solid colour.

    The original wall's lighting, shadows and surface texture are preserved so
    the new colour reads as real paint rather than a flat fill.

    Returns:
        JPEG image with the wall repainted onto the supplied mask.
    """
    try:
        # ── Decode room image ──────────────────────────────────────────────
        image_data = await image.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return JSONResponse({"error": "Could not decode image"}, status_code=400)

        h, w = img.shape[:2]

        # ── Decode paint mask (flat uint8; LABELED — each plane a distinct id) ──
        mask_bytes = await mask.read()
        try:
            paint_mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((h, w)).copy()
        except ValueError:
            return JSONResponse({"error": "Invalid mask"}, status_code=400)

        if not paint_mask.any():
            return JSONResponse({"error": "Empty mask"}, status_code=400)

        # ── Decode optional lighting source (pristine original) ────────────
        # Keeps shading idempotent across repeated applies — paint is always
        # derived from the real wall, never from the previous painted result.
        lighting_source = None
        if source is not None:
            src_bytes = await source.read()
            lighting_source = cv2.imdecode(np.frombuffer(src_bytes, np.uint8), cv2.IMREAD_COLOR)

        # ── Decode optional paint texture (material / wallpaper finish) ────
        texture_arr = None
        if paint_texture is not None:
            tex_bytes = await paint_texture.read()
            texture_arr = cv2.imdecode(np.frombuffer(tex_bytes, np.uint8), cv2.IMREAD_COLOR)

        # ── Depth for per-plane perspective texture mapping ────────────────
        # Only needed for texture finishes; sampled on the pristine original so
        # the geometry matches the real room.
        depth_map = None
        if texture_arr is not None:
            depth_predictor = getattr(request.app.state, "depth_predictor", None)
            if depth_predictor is not None:
                try:
                    src_for_depth = lighting_source if lighting_source is not None else img
                    rgb = cv2.cvtColor(src_for_depth, cv2.COLOR_BGR2RGB)
                    depth_map = await asyncio.to_thread(depth_predictor.predict, rgb)
                except Exception as exc:
                    logger.warning("Depth for paint texture failed: %s", exc)
                    depth_map = None

        # ── Normalise parameters ───────────────────────────────────────────
        if finish not in PAINT_FINISHES:
            finish = DEFAULT_PAINT_FINISH
        opacity = float(np.clip(opacity, 0.0, 1.0))
        texture_scale = float(np.clip(texture_scale, 0.3, 4.0))
        light_strength = float(np.clip(light_strength, 0.0, 2.0))
        saturation = float(np.clip(saturation, 0.0, 1.0))

        # ── Render paint ───────────────────────────────────────────────────
        result = apply_wall_paint(
            img,
            paint_mask,
            paint_color,
            finish=finish,
            opacity=opacity,
            lighting_source=lighting_source,
            texture=texture_arr,
            depth=depth_map,
            texture_scale=texture_scale,
            light_strength=light_strength,
            saturation=saturation,
        )

        # ── Matting refinement around fine foreground (foliage) ────────────
        # Composite the paint with a soft alpha so wispy leaves the mask can't
        # resolve stay clean instead of showing as ghost edges. The matte is
        # colour-independent, so it's cached and reused across recolours.
        matting = getattr(request.app.state, "matting_predictor", None)
        if PAINT_REFINE_MATTING and matting is not None and not paint_objects:
            try:
                matte_src = lighting_source if lighting_source is not None else img
                matte_rgb = cv2.cvtColor(matte_src, cv2.COLOR_BGR2RGB)
                key = (
                    hashlib.md5(mask_bytes).hexdigest()
                    + hashlib.md5(matte_rgb.tobytes()).hexdigest()
                )
                alpha = _MATTE_CACHE.get(key)
                if alpha is None:
                    alpha = await asyncio.to_thread(
                        matting.matte, matte_rgb, paint_mask,
                        MATTING_MAX_SIDE, MATTING_FG_ERODE, MATTING_BG_DILATE,
                        MATTING_COLOR_DEMOTE_T,
                    )
                    _MATTE_CACHE[key] = alpha
                    if len(_MATTE_CACHE) > _MATTE_CACHE_MAX:
                        _MATTE_CACHE.popitem(last=False)
                a = alpha[:, :, None]
                result = (a * result.astype(np.float32)
                          + (1.0 - a) * img.astype(np.float32)).astype(np.uint8)
            except Exception as exc:
                logger.warning("Paint matting skipped: %s", exc)

        # ── Encode and return ──────────────────────────────────────────────
        ok, buf = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return JSONResponse({"error": "Encode failed"}, status_code=500)

        return Response(content=buf.tobytes(), media_type="image/jpeg")

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(exc)}, status_code=500)
