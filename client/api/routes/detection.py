"""Floor detection route — /api/auto-detect."""

import asyncio
import io
import json
import logging
import struct
import gzip
import base64

import cv2
import numpy as np
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["detection"])


def _sse(obj: dict) -> str:
    """Encode a dict as a Server-Sent Events data frame."""
    return f"data: {json.dumps(obj)}\n\n"


def _get_centroid(mask: np.ndarray) -> dict | None:
    coords = np.argwhere(mask > 0)
    if len(coords) == 0:
        return None
    y, x = np.mean(coords, axis=0)
    return {"x": float(x), "y": float(y)}


@router.post("/auto-detect")
async def auto_detect_features(
    request: Request,
    image: UploadFile = File(...),
):
    """Segment floor and walls using Mask2Former and stream progress via SSE.

    Yields Server-Sent Events with step progress, then a final ``done`` event
    containing a gzip-compressed, base64-encoded binary payload with:
    - JSON label list (floor + wall centroids)
    - Floor mask (uint8, flat)
    - Labeled wall mask (uint8, flat)
    """
    image_data = await image.read()
    predictor = request.app.state.mask2former_predictor

    async def event_stream():
        try:
            # ── Step 1: Decode uploaded image ─────────────────────────────
            yield _sse({"step": 1, "total": 5, "message": "Décodage de l'image…"})
            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np = np.array(pil_image)
            h, w = image_np.shape[:2]
            logger.info("Image decoded: %dx%d px", w, h)

            # ── Step 2: Validate & prepare ────────────────────────────────
            yield _sse({"step": 2, "total": 5, "message": f"Image reçue\u00a0: {w}×{h} px — préparation de la segmentation…"})
            if h < 64 or w < 64:
                raise ValueError(f"Image trop petite ({w}×{h}). Minimum requis\u00a0: 64×64 px.")
            await asyncio.sleep(0)   # yield control to the event loop

            # ── Step 3: AI segmentation (floor + walls) ───────────────────
            yield _sse({"step": 3, "total": 5, "message": "Segmentation IA du sol et des murs en cours…"})
            floor_mask, wall_mask = await asyncio.to_thread(predictor.predict, image_np)
            logger.info(
                "Segmentation done — floor px: %d, wall px: %d",
                int(floor_mask.sum()), int(wall_mask.sum()),
            )

            # ── Step 4: Extract regions & centroids ───────────────────────
            yield _sse({"step": 4, "total": 5, "message": "Extraction des régions détectées…"})

            labels: list[dict] = []
            floor_center = _get_centroid(floor_mask)
            if floor_center:
                labels.append({
                    "text": "Sol",
                    "x": floor_center["x"],
                    "y": floor_center["y"],
                    "type": "floor",
                    "id": "floor",
                })

            num_labels, labeled_walls, stats, centroids = cv2.connectedComponentsWithStats(
                wall_mask.astype(np.uint8), connectivity=8
            )
            wall_count = 0
            for i in range(1, num_labels):
                if stats[i, cv2.CC_STAT_AREA] < 500:
                    continue
                wall_count += 1
                labels.append({
                    "text": "Mur",
                    "x": float(centroids[i][0]),
                    "y": float(centroids[i][1]),
                    "type": "wall",
                    "id": str(i),
                })
            logger.info("Regions: 1 floor, %d wall(s)", wall_count)

            # ── Step 5: Compress & encode binary payload ──────────────────
            yield _sse({"step": 5, "total": 5, "message": "Compression et envoi des résultats…"})
            labels_json = json.dumps(labels).encode("utf-8")
            floor_bytes = floor_mask.astype(np.uint8).tobytes()
            wall_bytes = labeled_walls.astype(np.uint8).tobytes()
            header = struct.pack("<III", len(labels_json), h, w)
            raw = header + labels_json + floor_bytes + wall_bytes
            compressed = gzip.compress(raw, compresslevel=1)
            b64 = base64.b64encode(compressed).decode("ascii")
            logger.info("Payload: %d bytes (raw) → %d bytes (compressed)", len(raw), len(compressed))

            yield _sse({"step": "done", "binary": b64})

        except Exception as exc:
            logger.error("Auto-detect error: %s", exc, exc_info=True)
            yield _sse({"step": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
