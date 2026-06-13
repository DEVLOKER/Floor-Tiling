"""Wall painting route — /api/apply-paint."""

import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from config.settings import (
    DEFAULT_PAINT_COLOR,
    DEFAULT_PAINT_FINISH,
    JPEG_QUALITY,
    PAINT_FINISHES,
)
from processors import apply_wall_paint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["paint"])


@router.post("/apply-paint")
async def apply_paint(
    image: UploadFile = File(...),
    mask: UploadFile = File(...),
    paint_color: str = Form(DEFAULT_PAINT_COLOR),
    finish: str = Form(DEFAULT_PAINT_FINISH),
    opacity: float = Form(1.0),
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

        # ── Decode wall mask (flat uint8, one byte per pixel) ──────────────
        mask_bytes = await mask.read()
        try:
            wall_mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((h, w))
        except ValueError:
            return JSONResponse({"error": "Invalid mask"}, status_code=400)

        wall_mask = (wall_mask > 0).astype(np.uint8)
        if not wall_mask.any():
            return JSONResponse({"error": "Empty mask"}, status_code=400)

        # ── Normalise parameters ───────────────────────────────────────────
        if finish not in PAINT_FINISHES:
            finish = DEFAULT_PAINT_FINISH
        opacity = float(np.clip(opacity, 0.0, 1.0))

        # ── Render paint ───────────────────────────────────────────────────
        result = apply_wall_paint(
            img,
            wall_mask,
            paint_color,
            finish=finish,
            opacity=opacity,
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
