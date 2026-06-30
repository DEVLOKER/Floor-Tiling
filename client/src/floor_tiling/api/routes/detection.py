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

from floor_tiling.core.planes import split_wall_planes
from floor_tiling.core.masks import (
    refine_mask,
    fill_surface_gaps,
    snap_mask_to_lines,
    grow_walls_to_objects,
)
from floor_tiling.config.settings import (
    WALL_PAINT_ENABLED,
    PAINT_IGNORE_WALL_OBJECTS,
    WALL_OBJECT_DILATE_FRAC,
    SNAP_EDGES_TO_LINES,
    WALL_FILL_GAPS_PX,
    USE_OPEN_VOCAB_OBJECTS,
    OPEN_VOCAB_DETECTOR,
    OPEN_VOCAB_OBJECT_PROMPT,
    OPEN_VOCAB_BOX_THRESHOLD,
    OPEN_VOCAB_TEXT_THRESHOLD,
    OPEN_VOCAB_MAX_BOX_FRAC,
    YOLO_WORLD_CONF,
)

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
            # Use whichever segmentation model(s) are enabled (SEG_USE_* flags).
            # With both, their masks are unioned (ensemble); with one, it's used
            # alone.
            seg_predictors = [
                p for p in (
                    getattr(request.app.state, "mask2former_predictor", None),
                    getattr(request.app.state, "oneformer_predictor", None),
                )
                if p is not None
            ]
            if not seg_predictors:
                raise RuntimeError("No segmentation model available.")

            floor_mask = wall_mask = ceiling_mask = object_mask = opening_mask = None
            for p in seg_predictors:
                f2, w2, c2, o2, op2 = await asyncio.to_thread(p.predict, image_np)
                if floor_mask is None:
                    floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask = f2, w2, c2, o2, op2
                else:
                    floor_mask = ((floor_mask > 0) | (f2 > 0)).astype(np.uint8)
                    wall_mask = ((wall_mask > 0) | (w2 > 0)).astype(np.uint8)
                    ceiling_mask = ((ceiling_mask > 0) | (c2 > 0)).astype(np.uint8)
                    object_mask = ((object_mask > 0) | (o2 > 0)).astype(np.uint8)
                    opening_mask = ((opening_mask > 0) | (op2 > 0)).astype(np.uint8)

            # Keep the three surfaces mutually exclusive (a union can overlap at
            # junctions): floor > ceiling > wall.
            floor_mask = (floor_mask > 0).astype(np.uint8)
            ceiling_mask = (ceiling_mask & ~(floor_mask > 0)).astype(np.uint8)
            wall_mask = (wall_mask & ~(floor_mask > 0) & ~(ceiling_mask > 0)).astype(np.uint8)

            if not WALL_PAINT_ENABLED:
                # Wall/ceiling painting is disabled — discard those masks so the
                # rest of the pipeline only processes the floor.
                wall_mask = np.zeros((h, w), np.uint8)
                ceiling_mask = np.zeros((h, w), np.uint8)
                object_mask = np.zeros((h, w), np.uint8)
                opening_mask = np.zeros((h, w), np.uint8)
                logger.info("Wall/ceiling disabled (WALL_PAINT_ENABLED=False) — floor only.")
            else:
                # ── Open-vocab objects the semantic model lacks ───────────────
                # Air conditioner, sockets, pipes, thermostats… have no ADE20K class,
                # so Grounding DINO finds them by text prompt and SAM cuts them
                # precisely. Their masks are unioned into the exclusion set.
                detector = getattr(request.app.state, "object_detector", None)
                sam = getattr(request.app.state, "sam_predictor", None)
                if USE_OPEN_VOCAB_OBJECTS and detector is not None and sam is not None:
                    try:
                        def _open_vocab():
                            # Grounding DINO takes a text prompt + 2 thresholds;
                            # YOLO-World has the prompt baked in and one conf gate.
                            if OPEN_VOCAB_DETECTOR == "grounding_dino":
                                boxes = detector.detect(
                                    image_np, OPEN_VOCAB_OBJECT_PROMPT,
                                    OPEN_VOCAB_BOX_THRESHOLD, OPEN_VOCAB_TEXT_THRESHOLD,
                                )
                            else:
                                boxes = detector.detect(image_np, YOLO_WORLD_CONF)
                            if len(boxes):
                                area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
                                boxes = boxes[area < OPEN_VOCAB_MAX_BOX_FRAC * h * w]
                            return sam.segment_boxes(image_np, boxes)
                        ov_mask = await asyncio.to_thread(_open_vocab)
                        object_mask = (
                            ov_mask if object_mask is None
                            else ((object_mask > 0) | (ov_mask > 0)).astype(np.uint8)
                        )
                        logger.info("Open-vocab objects: %d px", int(ov_mask.sum()))
                    except Exception as exc:
                        logger.warning("Open-vocab object detection skipped: %s", exc)

            if WALL_PAINT_ENABLED:
                # ── Surfaces' objects to EXCLUDE from painting ────────────────
                if object_mask is None:
                    object_mask = np.zeros((h, w), np.uint8)
                if opening_mask is None:
                    opening_mask = np.zeros((h, w), np.uint8)
                object_mask = (object_mask.astype(np.uint8) & ~(floor_mask > 0)).astype(np.uint8)
                opening_mask = (opening_mask.astype(np.uint8) & ~(floor_mask > 0)).astype(np.uint8)
                obj_tight = ((object_mask > 0) | (opening_mask > 0)).astype(np.uint8)
                obj_excl = None
                if PAINT_IGNORE_WALL_OBJECTS and obj_tight.any():
                    r = max(1, int(WALL_OBJECT_DILATE_FRAC * max(h, w)))
                    obj_excl = cv2.dilate(
                        obj_tight,
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)),
                    )
                    obj_excl = (obj_excl & ~(floor_mask > 0)).astype(np.uint8)

                # ── Edge-aware mask refinement ────────────────────────────────
                def _refine_all(img, f, wl, c):
                    return (
                        refine_mask(f, img, single_region=True),
                        refine_mask(wl, img),
                        refine_mask(c, img, single_region=True),
                    )
                floor_mask, wall_mask, ceiling_mask = await asyncio.to_thread(
                    _refine_all, image_np, floor_mask, wall_mask, ceiling_mask
                )

                # ── Snap wall/ceiling boundaries onto architectural lines ─────
                mlsd_predictor = getattr(request.app.state, "mlsd_predictor", None)
                if SNAP_EDGES_TO_LINES and mlsd_predictor is not None:
                    try:
                        segments = await asyncio.to_thread(mlsd_predictor.predict, image_np)

                        def _snap(wl, c):
                            return (
                                snap_mask_to_lines(wl, segments),
                                snap_mask_to_lines(c, segments),
                            )
                        wall_mask, ceiling_mask = await asyncio.to_thread(
                            _snap, wall_mask, ceiling_mask
                        )
                    except Exception as exc:
                        logger.warning("Edge line-snapping skipped: %s", exc)

                if obj_excl is not None:
                    wall_mask = (wall_mask & ~(obj_excl > 0)).astype(np.uint8)
                    ceiling_mask = (ceiling_mask & ~(obj_excl > 0)).astype(np.uint8)
            else:
                obj_tight = None
                obj_excl = None

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

            # ── Split walls into individual planes (wall painting only) ───
            labeled_walls = np.zeros((h, w), np.uint8)
            ceiling_mask_out = ceiling_mask.copy()
            if WALL_PAINT_ENABLED:
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

                floor_mask, labeled_walls, ceiling_mask_out = fill_surface_gaps(
                    floor_mask, labeled_walls, ceiling_mask
                )

                if obj_excl is not None:
                    labeled_walls[obj_excl > 0] = 0
                    ceiling_mask_out = (ceiling_mask_out & ~(obj_excl > 0)).astype(np.uint8)

                if WALL_FILL_GAPS_PX > 0 and obj_tight is not None:
                    labeled_walls = grow_walls_to_objects(
                        labeled_walls, floor_mask, ceiling_mask_out, obj_tight, WALL_FILL_GAPS_PX
                    )

                wall_count = 0
                for pid in np.unique(labeled_walls):
                    if pid == 0:
                        continue
                    piece = labeled_walls == pid
                    if int(piece.sum()) < 500:
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

                ceiling_center = _get_centroid(ceiling_mask_out)
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

            # ── Excluded items, labelled by the surface they sit on ───────
            object_labeled = np.zeros((h, w), np.uint8)
            opening_labeled = np.zeros((h, w), np.uint8)
            if WALL_PAINT_ENABLED:
                opix = object_mask > 0
                wpix = opening_mask > 0
                if opix.any() or wpix.any():
                    surfaces = [(255, (ceiling_mask_out > 0).astype(np.uint8))]
                    for wid in [int(i) for i in np.unique(labeled_walls) if i != 0]:
                        surfaces.append((wid, (labeled_walls == wid).astype(np.uint8)))
                    best = np.full((h, w), np.inf, np.float32)
                    nearest = np.zeros((h, w), np.int32)
                    for sid, sm in surfaces:
                        if not sm.any():
                            continue
                        dist = cv2.distanceTransform(1 - sm, cv2.DIST_L2, 3)
                        upd = dist < best
                        best[upd] = dist[upd]
                        nearest[upd] = sid
                    object_labeled[opix] = nearest[opix].astype(np.uint8)
                    opening_labeled[wpix] = nearest[wpix].astype(np.uint8)
            ceiling_mask = ceiling_mask_out

            # ── Step 5: Compress & encode binary payload ──────────────────
            yield _sse({"step": 5, "total": 5, "message": "Compression et envoi des résultats…"})
            labels_json = json.dumps(labels).encode("utf-8")
            floor_bytes = floor_mask.astype(np.uint8).tobytes()
            wall_bytes = labeled_walls.astype(np.uint8).tobytes()
            ceiling_bytes = ceiling_mask.astype(np.uint8).tobytes()
            object_bytes = object_labeled.astype(np.uint8).tobytes()
            opening_bytes = opening_labeled.astype(np.uint8).tobytes()
            header = struct.pack("<III", len(labels_json), h, w)
            raw = (
                header + labels_json + floor_bytes + wall_bytes + ceiling_bytes
                + object_bytes + opening_bytes
            )
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
