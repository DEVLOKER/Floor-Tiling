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

from core.planes import split_wall_planes
from core.masks import refine_mask, fill_surface_gaps

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

            # ── Step 3: AI segmentation (floor + walls + ceiling) ─────────
            yield _sse({"step": 3, "total": 5, "message": "Segmentation IA du sol, des murs et du plafond en cours…"})
            floor_mask, wall_mask, ceiling_mask = await asyncio.to_thread(predictor.predict, image_np)

            # ── Edge-aware mask refinement ────────────────────────────────
            # Snap jagged model boundaries to the photo's real edges and clean
            # specks/holes so painted/tiled regions have smooth, natural edges.
            def _refine_all(img, f, wl, c):
                return (
                    refine_mask(f, img, single_region=True),
                    refine_mask(wl, img),
                    refine_mask(c, img, single_region=True),
                )
            floor_mask, wall_mask, ceiling_mask = await asyncio.to_thread(
                _refine_all, image_np, floor_mask, wall_mask, ceiling_mask
            )
            logger.info(
                "Segmentation done — floor px: %d, wall px: %d, ceiling px: %d",
                int(floor_mask.sum()), int(wall_mask.sum()), int(ceiling_mask.sum()),
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

            # ── Split walls into individual planes ────────────────────────
            # A depth model gives per-pixel normals so the single semantic
            # "wall" blob is separated into its real planes (left/back/right).
            # If depth isn't available, fall back to connected components
            # (which can only separate visually disconnected walls).
            depth_predictor = getattr(request.app.state, "depth_predictor", None)
            labeled_walls = None
            if depth_predictor is not None:
                try:
                    depth = await asyncio.to_thread(depth_predictor.predict, image_np)
                    labeled_walls, _ = split_wall_planes(wall_mask, depth)
                except Exception as exc:
                    logger.warning("Wall-plane split failed, using fallback: %s", exc)
                    labeled_walls = None
            if labeled_walls is None:
                _, cc = cv2.connectedComponents(wall_mask.astype(np.uint8), connectivity=8)
                labeled_walls = cc.astype(np.uint8)

            # ── Close hairline gaps between adjacent surfaces ─────────────
            # Removes the unpainted slivers along wall↔ceiling / wall↔floor
            # edges (assigns them to the nearest surface) without bridging
            # openings as wide as a door/window.
            floor_mask, labeled_walls, ceiling_mask = fill_surface_gaps(
                floor_mask, labeled_walls, ceiling_mask
            )

            wall_count = 0
            for pid in np.unique(labeled_walls):
                if pid == 0:
                    continue
                piece = labeled_walls == pid
                area = int(piece.sum())
                if area < 500:
                    continue
                ys, xs = np.where(piece)
                wall_count += 1
                labels.append({
                    "text": "Mur",
                    "x": float(xs.mean()),
                    "y": float(ys.mean()),
                    "type": "wall",
                    "id": str(int(pid)),
                })

            ceiling_center = _get_centroid(ceiling_mask)
            if ceiling_center:
                labels.append({
                    "text": "Plafond",
                    "x": ceiling_center["x"],
                    "y": ceiling_center["y"],
                    "type": "ceiling",
                    "id": "ceiling",
                })
            logger.info(
                "Regions: 1 floor, %d wall(s), %d ceiling",
                wall_count, 1 if ceiling_center else 0,
            )

            # ── Step 5: Compress & encode binary payload ──────────────────
            yield _sse({"step": 5, "total": 5, "message": "Compression et envoi des résultats…"})
            labels_json = json.dumps(labels).encode("utf-8")
            floor_bytes = floor_mask.astype(np.uint8).tobytes()
            wall_bytes = labeled_walls.astype(np.uint8).tobytes()
            ceiling_bytes = ceiling_mask.astype(np.uint8).tobytes()
            header = struct.pack("<III", len(labels_json), h, w)
            raw = header + labels_json + floor_bytes + wall_bytes + ceiling_bytes
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
