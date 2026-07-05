"""Detection routes — /api/detect-floor  and  /api/detect-walls.

Two-phase lazy detection:

  Phase 1  POST /api/detect-floor   (fast, ~3-5 s)
    Runs segmentation model(s) and returns only the floor mask.
    Wall / ceiling processing is skipped entirely — floor-tiling users
    never pay for the cost of the wall pipeline.
    The raw segmentation result is cached (keyed by image MD5) so that
    if the user later requests wall detection on the same image, the
    models don't run a second time.

  Phase 2  POST /api/detect-walls   (on-demand, ~8-12 s)
    Called only when the user opens the paint tab for the first time.
    Retrieves the cached segmentation (or re-runs if the cache expired),
    then runs the full wall pipeline:
      • confidence-weighted ensemble
      • open-vocab object detection (YOLO-World / Grounding DINO + SAM)
      • adaptive per-object dilation
      • edge-aware mask refinement + Laplacian boundary sharpening
      • M-LSD edge snapping
      • depth RANSAC plane splitting with wall-normal validation
      • M-LSD line-guided geometric fallback (works on texture-less walls)
      • surface gap filling
      • wall growing around objects

Both routes stream Server-Sent Events and share the same binary payload
format so the frontend parser is unchanged.

The legacy /api/auto-detect route is kept for backward-compatibility; it
runs both phases back-to-back and returns the combined result.
"""

import asyncio
import hashlib
import io
import json
import logging
import struct
import gzip
import base64
import time
from collections import OrderedDict

import cv2
import numpy as np
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from floor_tiling.core.planes import (
    split_wall_planes,
    split_wall_planes_with_lines,
    horizontal_surfaces_from_depth,
)
from floor_tiling.core.masks import (
    refine_mask,
    fill_surface_gaps,
    snap_mask_to_lines,
    grow_walls_to_objects,
    sharpen_wall_boundary,
    color_coherence_expand,
    infer_wall_behind_furniture,
    wall_is_chromatic,
    close_wall_halos,
    strip_wall_color_from_objects,
    derive_wall_by_complement,
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


# ─────────────────────────────────────────────────────────────────────────────
# Segmentation result cache
# ─────────────────────────────────────────────────────────────────────────────
# Stores the raw 5-tuple (floor, wall, ceiling, object, opening masks) keyed
# by image MD5.  Avoids re-running the segmentation models when detect-walls
# is called shortly after detect-floor on the same image.

_SEG_CACHE: OrderedDict = OrderedDict()
_SEG_CACHE_MAX = 3       # keep at most 3 different images in RAM
_SEG_CACHE_TTL = 600.0   # evict entries older than 10 minutes


def _cache_key(image_data: bytes) -> str:
    return hashlib.md5(image_data).hexdigest()


def _get_seg_cache(key: str):
    entry = _SEG_CACHE.get(key)
    if entry is None:
        return None
    if time.monotonic() - entry["ts"] > _SEG_CACHE_TTL:
        del _SEG_CACHE[key]
        return None
    _SEG_CACHE.move_to_end(key)
    return entry["masks"]


def _set_seg_cache(key: str, masks: tuple) -> None:
    _SEG_CACHE[key] = {"masks": masks, "ts": time.monotonic()}
    _SEG_CACHE.move_to_end(key)
    while len(_SEG_CACHE) > _SEG_CACHE_MAX:
        _SEG_CACHE.popitem(last=False)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _get_centroid(mask: np.ndarray) -> dict | None:
    coords = np.argwhere(mask > 0)
    if len(coords) == 0:
        return None
    y, x = np.mean(coords, axis=0)
    return {"x": float(x), "y": float(y)}


def _wall_ensemble(m1: np.ndarray, m2: np.ndarray) -> np.ndarray:
    """Recall-maximizing wall ensemble (union).

    Wall UNDER-detection is the dominant failure mode (tiled walls, textured
    surfaces, furniture occlusion), so we take the union of both models to
    recover as much wall as possible.  Boundary noise is cleaned up downstream
    by object exclusion + edge refinement, not by shrinking the mask here.
    """
    return ((m1 > 0) | (m2 > 0)).astype(np.uint8)


def _adaptive_dilate_objects(obj_tight: np.ndarray, h: int, w: int) -> np.ndarray:
    """Per-object dilation sized proportionally to each object's footprint.

    The global WALL_OBJECT_DILATE_FRAC causes over-dilation around small
    sockets and under-dilation around large TVs.  Sizing the kernel to
    sqrt(area) × 0.15 gives natural margins at every scale.
    """
    n_labels, labeled, stats, _ = cv2.connectedComponentsWithStats(
        obj_tight.astype(np.uint8), connectivity=8
    )
    result = np.zeros_like(obj_tight)
    max_r = max(h, w) // 20   # hard cap: 5% of image dimension

    for i in range(1, n_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        r = int(np.sqrt(area) * 0.15)
        r = max(4, min(r, max_r))
        obj_i = (labeled == i).astype(np.uint8)
        k = 2 * r + 1
        dilated_i = cv2.dilate(
            obj_i,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)),
        )
        result = np.maximum(result, dilated_i)

    return result.astype(np.uint8)


def _reconcile_labels_to_mask(labeled_walls: np.ndarray, paintable: np.ndarray) -> np.ndarray:
    """Guarantee every paintable wall pixel carries a plane label.

    ``split_wall_planes`` can leave wall pixels unlabeled (plane validation,
    ray-cast misses, sliver removal).  Those label-0 pixels would be UNPAINTED —
    showing as the original wall bleeding through the new colour (the classic
    "tile centres stay green" artefact).  Here we assign any unlabeled paintable
    pixel to its nearest existing plane, so the painted region always equals the
    full detected wall coverage regardless of how the split behaved.
    """
    labeled = labeled_walls.copy()
    unlabeled = (paintable > 0) & (labeled == 0)
    if not unlabeled.any():
        return labeled

    plane_ids = [int(i) for i in np.unique(labeled) if i != 0]
    if not plane_ids:
        # No planes survived splitting → the whole wall is one plane.
        labeled[paintable > 0] = 1
        return labeled

    h, w = labeled.shape
    best   = np.full((h, w), np.inf, np.float32)
    choice = np.zeros((h, w), np.uint8)
    for pid in plane_ids:
        dist = cv2.distanceTransform((labeled != pid).astype(np.uint8), cv2.DIST_L2, 3)
        upd = unlabeled & (dist < best)
        best[upd]   = dist[upd]
        choice[upd] = pid
    labeled[unlabeled] = choice[unlabeled]
    return labeled


async def _run_segmentation(request: Request, image_np: np.ndarray) -> tuple:
    """Run enabled segmentation models and return raw 5-tuple of masks."""
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
            floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask = (
                f2, w2, c2, o2, op2
            )
        else:
            # Floor / ceiling / objects: simple union (single-region, union is safe)
            floor_mask   = ((floor_mask   > 0) | (f2  > 0)).astype(np.uint8)
            ceiling_mask = ((ceiling_mask > 0) | (c2  > 0)).astype(np.uint8)
            object_mask  = ((object_mask  > 0) | (o2  > 0)).astype(np.uint8)
            opening_mask = ((opening_mask > 0) | (op2 > 0)).astype(np.uint8)
            # Walls: confidence-weighted ensemble (reduces boundary noise)
            wall_mask = _wall_ensemble(wall_mask, w2)

    return floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask


def _encode_payload(labels: list, h: int, w: int,
                    floor_mask, labeled_walls, ceiling_mask,
                    object_labeled, opening_labeled) -> str:
    """Gzip-compress and base64-encode the standard binary payload."""
    labels_json = json.dumps(labels).encode("utf-8")
    header = struct.pack("<III", len(labels_json), h, w)
    raw = (
        header
        + labels_json
        + floor_mask.astype(np.uint8).tobytes()
        + labeled_walls.astype(np.uint8).tobytes()
        + ceiling_mask.astype(np.uint8).tobytes()
        + object_labeled.astype(np.uint8).tobytes()
        + opening_labeled.astype(np.uint8).tobytes()
    )
    compressed = gzip.compress(raw, compresslevel=1)
    b64 = base64.b64encode(compressed).decode("ascii")
    logger.info("Payload: %d B raw → %d B compressed", len(raw), len(compressed))
    return b64


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Floor detection only (fast)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/detect-floor")
async def detect_floor(
    request: Request,
    image: UploadFile = File(...),
):
    """Segment only the floor surface and stream progress via SSE.

    Skips the entire wall/ceiling pipeline — optimised for users who only
    need floor tiling.  The raw segmentation result is cached so a subsequent
    /detect-walls call on the same image skips the models entirely.

    Returns the standard binary payload (wall / ceiling / object arrays are
    all-zero so the frontend parser is unchanged).
    """
    image_data = await image.read()
    cache_key = _cache_key(image_data)

    async def event_stream():
        try:
            yield _sse({"step": 1, "total": 3, "message": "Décodage de l'image…"})
            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np = np.array(pil_image)
            h, w = image_np.shape[:2]
            logger.info("detect-floor: %dx%d px", w, h)

            if h < 64 or w < 64:
                raise ValueError(f"Image trop petite ({w}×{h}). Minimum : 64×64 px.")
            await asyncio.sleep(0)

            # ── Step 2: Segmentation (cached if available) ────────────────
            yield _sse({"step": 2, "total": 3, "message": "Segmentation IA du sol en cours…"})
            cached = _get_seg_cache(cache_key)
            if cached is not None:
                logger.info("detect-floor: segmentation cache hit")
                floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask = cached
            else:
                (floor_mask, wall_mask, ceiling_mask,
                 object_mask, opening_mask) = await _run_segmentation(request, image_np)
                _set_seg_cache(cache_key, (
                    floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask
                ))
                logger.info("detect-floor: segmentation done, result cached")

            # Enforce mutual exclusivity: floor > ceiling > wall
            floor_mask = (floor_mask > 0).astype(np.uint8)

            # ── Step 3: Refine floor boundary + build payload ─────────────
            yield _sse({"step": 3, "total": 3, "message": "Affinage du contour du sol…"})
            floor_mask = await asyncio.to_thread(
                refine_mask, floor_mask, image_np, True
            )
            logger.info("detect-floor: floor px=%d", int(floor_mask.sum()))

            labels: list[dict] = []
            fc = _get_centroid(floor_mask)
            if fc:
                labels.append({
                    "text": "Sol", "x": fc["x"], "y": fc["y"],
                    "type": "floor", "id": "floor",
                })

            zeros = np.zeros((h, w), np.uint8)
            b64 = _encode_payload(labels, h, w,
                                   floor_mask, zeros, zeros, zeros, zeros)
            yield _sse({"step": "done", "binary": b64, "mode": "floor"})

        except Exception as exc:
            logger.error("detect-floor error: %s", exc, exc_info=True)
            yield _sse({"step": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Wall detection (on-demand)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/detect-walls")
async def detect_walls(
    request: Request,
    image: UploadFile = File(...),
):
    """Run the full wall + ceiling detection pipeline and stream via SSE.

    Triggered only when the user opens the paint tab.  Retrieves the cached
    segmentation from detect-floor (or re-runs if the cache expired / the
    user skipped phase 1), then runs:

      • Confidence-weighted ensemble (already applied in segmentation)
      • Open-vocab object detection (YOLO-World / Grounding DINO + SAM)
      • Adaptive per-object exclusion dilation
      • Edge-aware mask refinement + Laplacian boundary sharpening
      • M-LSD architectural edge snapping
      • Depth RANSAC plane splitting with wall-normal + aspect-ratio validation
      • M-LSD geometric fallback when depth is unreliable (texture-less walls)
      • Surface gap fill
      • Wall growing around excluded objects

    Returns the standard binary payload (floor array is all-zero — the
    frontend already has the floor mask from detect-floor).
    """
    image_data = await image.read()
    cache_key = _cache_key(image_data)

    async def event_stream():
        try:
            yield _sse({"step": 1, "total": 5, "message": "Décodage de l'image…"})
            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np = np.array(pil_image)
            # BGR view for OpenCV color functions (HSV etc. expect BGR).
            image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            h, w = image_np.shape[:2]
            logger.info("detect-walls: %dx%d px", w, h)

            if h < 64 or w < 64:
                raise ValueError(f"Image trop petite ({w}×{h}). Minimum : 64×64 px.")
            await asyncio.sleep(0)

            # ── Step 2: Segmentation (cache hit expected) ──────────────────
            yield _sse({"step": 2, "total": 5, "message": "Segmentation IA des murs et du plafond…"})
            cached = _get_seg_cache(cache_key)
            if cached is not None:
                logger.info("detect-walls: segmentation cache hit")
                floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask = cached
            else:
                logger.info("detect-walls: cache miss — re-running segmentation")
                (floor_mask, wall_mask, ceiling_mask,
                 object_mask, opening_mask) = await _run_segmentation(request, image_np)
                _set_seg_cache(cache_key, (
                    floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask
                ))

            # Enforce mutual exclusivity: floor > ceiling > wall
            floor_mask   = (floor_mask   > 0).astype(np.uint8)
            ceiling_mask = (ceiling_mask & ~(floor_mask > 0)).astype(np.uint8)
            wall_mask    = (wall_mask    & ~(floor_mask > 0) & ~(ceiling_mask > 0)).astype(np.uint8)

            # ── Step 3: Objects + openings (things NOT to paint) ──────────
            yield _sse({"step": 3, "total": 5,
                        "message": "Détection des objets et ouvertures…"})

            # Open-vocabulary objects (AC, sockets, vents, pipes… not in ADE20K).
            # High recall matters here: in the complement model a MISSED object
            # would fall through to "wall" and be painted over.
            detector = getattr(request.app.state, "object_detector", None)
            sam      = getattr(request.app.state, "sam_predictor", None)
            if USE_OPEN_VOCAB_OBJECTS and detector is not None and sam is not None:
                try:
                    def _open_vocab():
                        if OPEN_VOCAB_DETECTOR == "grounding_dino":
                            boxes = detector.detect(
                                image_np, OPEN_VOCAB_OBJECT_PROMPT,
                                OPEN_VOCAB_BOX_THRESHOLD, OPEN_VOCAB_TEXT_THRESHOLD,
                            )
                        else:
                            boxes = detector.detect(image_np, YOLO_WORLD_CONF)
                        if len(boxes):
                            area = ((boxes[:, 2] - boxes[:, 0])
                                    * (boxes[:, 3] - boxes[:, 1]))
                            boxes = boxes[area < OPEN_VOCAB_MAX_BOX_FRAC * h * w]
                        return sam.segment_boxes(image_np, boxes)
                    ov_mask = await asyncio.to_thread(_open_vocab)
                    object_mask = (
                        ov_mask if object_mask is None
                        else ((object_mask > 0) | (ov_mask > 0)).astype(np.uint8)
                    )
                    logger.info("detect-walls: open-vocab objects %d px",
                                int(ov_mask.sum()))
                except Exception as exc:
                    logger.warning("Open-vocab detection skipped: %s", exc)

            if object_mask is None:
                object_mask  = np.zeros((h, w), np.uint8)
            if opening_mask is None:
                opening_mask = np.zeros((h, w), np.uint8)
            object_mask  = (object_mask.astype(np.uint8)  & ~(floor_mask > 0)).astype(np.uint8)
            opening_mask = (opening_mask.astype(np.uint8) & ~(floor_mask > 0)).astype(np.uint8)
            obj_tight = ((object_mask > 0) | (opening_mask > 0)).astype(np.uint8)
            # Small fixed safety dilation to catch object frames (e.g. window
            # casing) WITHOUT the large adaptive halo the old path produced.
            obj_carve = cv2.dilate(
                obj_tight, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            ) if obj_tight.any() else obj_tight
            obj_carve = (obj_carve & ~(floor_mask > 0)).astype(np.uint8)

            # ── Step 4: Wall from semantic class + comprehensive exclusion ─
            yield _sse({"step": 4, "total": 5,
                        "message": "Déduction des murs…"})

            # Depth (computed once, reused for floor/ceiling strengthening AND
            # plane splitting).
            depth_predictor = getattr(request.app.state, "depth_predictor", None)
            depth = None
            if depth_predictor is not None:
                try:
                    depth = await asyncio.to_thread(depth_predictor.predict, image_np)
                except Exception as exc:
                    logger.warning("Depth prediction failed: %s", exc)

            # Strengthen floor / ceiling recall with depth-horizontal surfaces.
            floor_strong   = (floor_mask   > 0).astype(np.uint8)
            ceiling_strong = (ceiling_mask > 0).astype(np.uint8)
            if depth is not None:
                try:
                    df, dc = horizontal_surfaces_from_depth(depth)
                    floor_strong   = ((floor_strong   > 0) | (df > 0)).astype(np.uint8)
                    ceiling_strong = ((ceiling_strong > 0) | (dc > 0)).astype(np.uint8)
                    ceiling_strong = (ceiling_strong & ~(floor_strong > 0)).astype(np.uint8)
                except Exception as exc:
                    logger.warning("Depth floor/ceiling strengthen skipped: %s", exc)

            # ── Comprehensive CLUTTER exclusion ───────────────────────────
            # The pure complement painted furniture (sofas, tables, dressers)
            # because they aren't floor/ceiling/wall-objects.  The segmenter DOES
            # classify them (as bed/sofa/table/…), so anything it does NOT call
            # wall/floor/ceiling is clutter and must never be painted.  Union
            # with the detected wall-objects/openings (a pipe may be "wall"
            # semantically yet still an object) for the full exclusion.
            clutter = (
                ~((wall_mask > 0) | (floor_strong > 0) | (ceiling_strong > 0))
            ).astype(np.uint8)
            exclude = ((clutter > 0) | (obj_carve > 0)).astype(np.uint8)
            # Small safety dilation so we stop just short of furniture/frames.
            exclude = cv2.dilate(
                exclude, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            )
            exclude = (exclude & ~(floor_strong > 0)).astype(np.uint8)
            obj_carve = exclude  # bound every downstream op by full clutter

            # Wall base = the SEMANTIC wall class (excludes furniture by design),
            # refined + edge-sharpened, then bounded away from clutter/floor/ceiling.
            wall_mask = (wall_mask > 0).astype(np.uint8)
            wall_mask = await asyncio.to_thread(
                lambda m: sharpen_wall_boundary(refine_mask(m, image_bgr), image_bgr),
                wall_mask,
            )
            wall_mask = (wall_mask & ~(exclude > 0) & ~(floor_strong > 0)
                         & ~(ceiling_strong > 0)).astype(np.uint8)

            # M-LSD edge snapping (straighten wall/ceiling architectural lines)
            mlsd_predictor = getattr(request.app.state, "mlsd_predictor", None)
            mlsd_segments  = None
            if SNAP_EDGES_TO_LINES and mlsd_predictor is not None:
                try:
                    mlsd_segments = await asyncio.to_thread(mlsd_predictor.predict, image_np)
                    wall_mask = await asyncio.to_thread(
                        snap_mask_to_lines, wall_mask, mlsd_segments
                    )
                    wall_mask = (wall_mask & ~(exclude > 0) & ~(floor_strong > 0)).astype(np.uint8)
                except Exception as exc:
                    logger.warning("Edge snapping skipped: %s", exc)

            ceiling_mask = ceiling_strong
            logger.info(
                "detect-walls: semantic wall px=%d  ceiling px=%d",
                int(wall_mask.sum()), int(ceiling_mask.sum()),
            )

            # ── Step 5: Plane splitting + label extraction ────────────────
            yield _sse({"step": 5, "total": 5,
                        "message": "Séparation des plans muraux…"})

            labeled_walls = None
            if depth is not None:
                try:
                    labeled_walls, n_planes = split_wall_planes(wall_mask, depth)
                    logger.info("detect-walls: depth RANSAC → %d planes", n_planes)
                except Exception as exc:
                    logger.warning("Depth RANSAC failed: %s — M-LSD fallback", exc)
                    labeled_walls = None
            if labeled_walls is None or int((labeled_walls > 0).sum()) < 500:
                if mlsd_segments is not None:
                    labeled_walls, n_planes = split_wall_planes_with_lines(
                        wall_mask, mlsd_segments
                    )
                    logger.info("detect-walls: M-LSD fallback → %d planes", n_planes)
                else:
                    _, labeled_walls = cv2.connectedComponents(
                        wall_mask.astype(np.uint8), connectivity=8
                    )
                    labeled_walls = labeled_walls.astype(np.uint8)

            # Gap fill (real floor as boundary, not returned — frontend has it).
            floor_ref = floor_strong.copy()
            floor_ref, labeled_walls, ceiling_mask = fill_surface_gaps(
                floor_ref, labeled_walls, ceiling_mask
            )
            labeled_walls[obj_carve > 0] = 0
            ceiling_mask = (ceiling_mask & ~(obj_carve > 0)).astype(np.uint8)

            # Guarantee every complement-wall pixel is labelled (no unpainted gaps)
            paintable = ((wall_mask > 0) & ~(obj_carve > 0)).astype(np.uint8)
            labeled_walls = _reconcile_labels_to_mask(labeled_walls, paintable)

            # Close junction halos (reach right up to floor/ceiling/corner lines)
            labeled_walls = close_wall_halos(
                labeled_walls, floor_ref, ceiling_mask, obj_carve
            )

            # Extract labels (centroids)
            labels: list[dict] = []
            wall_count = 0
            for pid in np.unique(labeled_walls):
                if pid == 0:
                    continue
                piece = labeled_walls == pid
                if int(piece.sum()) < 500:
                    continue
                ys_p, xs_p = np.where(piece)
                wall_count += 1
                labels.append({
                    "text": "Mur",
                    "x": float(xs_p.mean()),
                    "y": float(ys_p.mean()),
                    "type": "wall",
                    "id": str(int(pid)),
                })

            ceil_c = _get_centroid(ceiling_mask)
            if ceil_c:
                labels.append({
                    "text": "Plafond",
                    "x": ceil_c["x"], "y": ceil_c["y"],
                    "type": "ceiling", "id": "ceiling",
                })

            logger.info("detect-walls: %d wall(s), %d ceiling",
                        wall_count, 1 if ceil_c else 0)

            # Object/opening labelling (nearest surface)
            object_labeled  = np.zeros((h, w), np.uint8)
            opening_labeled = np.zeros((h, w), np.uint8)
            opix = object_mask  > 0
            wpix = opening_mask > 0
            if opix.any() or wpix.any():
                surfaces = [(255, (ceiling_mask > 0).astype(np.uint8))]
                for wid in [int(i) for i in np.unique(labeled_walls) if i != 0]:
                    surfaces.append((wid, (labeled_walls == wid).astype(np.uint8)))
                best    = np.full((h, w), np.inf, np.float32)
                nearest = np.zeros((h, w), np.int32)
                for sid, sm in surfaces:
                    if not sm.any():
                        continue
                    dist = cv2.distanceTransform(1 - sm, cv2.DIST_L2, 3)
                    upd = dist < best
                    best[upd]    = dist[upd]
                    nearest[upd] = sid
                object_labeled[opix]  = nearest[opix].astype(np.uint8)
                opening_labeled[wpix] = nearest[wpix].astype(np.uint8)

            # Encode — floor array is zeros (frontend has real floor from phase 1)
            zeros = np.zeros((h, w), np.uint8)
            b64 = _encode_payload(labels, h, w,
                                   zeros, labeled_walls, ceiling_mask,
                                   object_labeled, opening_labeled)
            yield _sse({"step": "done", "binary": b64, "mode": "walls"})

        except Exception as exc:
            logger.error("detect-walls error: %s", exc, exc_info=True)
            yield _sse({"step": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy — /api/auto-detect (backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/auto-detect")
async def auto_detect_features(
    request: Request,
    image: UploadFile = File(...),
):
    """Combined floor + wall detection (legacy endpoint, kept for compatibility).

    Runs both phases sequentially and returns a single payload with all masks.
    Prefer /detect-floor + /detect-walls for new integrations.
    """
    image_data = await image.read()
    cache_key  = _cache_key(image_data)

    async def event_stream():
        try:
            yield _sse({"step": 1, "total": 5, "message": "Décodage de l'image…"})
            pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_np  = np.array(pil_image)
            image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            h, w      = image_np.shape[:2]

            if h < 64 or w < 64:
                raise ValueError(f"Image trop petite ({w}×{h}). Minimum : 64×64 px.")
            await asyncio.sleep(0)

            yield _sse({"step": 2, "total": 5,
                        "message": "Segmentation IA du sol, des murs et du plafond…"})
            cached = _get_seg_cache(cache_key)
            if cached:
                floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask = cached
            else:
                (floor_mask, wall_mask, ceiling_mask,
                 object_mask, opening_mask) = await _run_segmentation(request, image_np)
                _set_seg_cache(cache_key, (
                    floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask
                ))

            floor_mask   = (floor_mask   > 0).astype(np.uint8)
            ceiling_mask = (ceiling_mask & ~(floor_mask > 0)).astype(np.uint8)
            wall_mask    = (wall_mask    & ~(floor_mask > 0) & ~(ceiling_mask > 0)).astype(np.uint8)

            if not WALL_PAINT_ENABLED:
                wall_mask    = np.zeros((h, w), np.uint8)
                ceiling_mask = np.zeros((h, w), np.uint8)
                object_mask  = np.zeros((h, w), np.uint8)
                opening_mask = np.zeros((h, w), np.uint8)

            yield _sse({"step": 3, "total": 5, "message": "Affinage des masques…"})
            floor_mask = await asyncio.to_thread(
                refine_mask, floor_mask, image_np, True
            )

            labeled_walls   = np.zeros((h, w), np.uint8)
            ceiling_mask_out = ceiling_mask.copy()
            obj_tight = obj_excl = None

            if WALL_PAINT_ENABLED:
                # Object exclusion
                if object_mask is None:
                    object_mask  = np.zeros((h, w), np.uint8)
                if opening_mask is None:
                    opening_mask = np.zeros((h, w), np.uint8)
                object_mask  = (object_mask  & ~(floor_mask > 0)).astype(np.uint8)
                opening_mask = (opening_mask & ~(floor_mask > 0)).astype(np.uint8)
                obj_tight = ((object_mask > 0) | (opening_mask > 0)).astype(np.uint8)
                if PAINT_IGNORE_WALL_OBJECTS and obj_tight.any():
                    obj_excl = _adaptive_dilate_objects(obj_tight, h, w)
                    obj_excl = (obj_excl & ~(floor_mask > 0)).astype(np.uint8)

                # Refine walls + Laplacian sharpening
                def _refine_all(img, f, wl, c):
                    wl_r = refine_mask(wl, img)
                    wl_r = sharpen_wall_boundary(wl_r, img)
                    c_r  = refine_mask(c, img, single_region=True)
                    return refine_mask(f, img, single_region=True), wl_r, c_r

                floor_mask, wall_mask, ceiling_mask = await asyncio.to_thread(
                    _refine_all, image_np, floor_mask, wall_mask, ceiling_mask
                )

                mlsd_predictor = getattr(request.app.state, "mlsd_predictor", None)
                mlsd_segments  = None
                if SNAP_EDGES_TO_LINES and mlsd_predictor is not None:
                    try:
                        mlsd_segments = await asyncio.to_thread(
                            mlsd_predictor.predict, image_np
                        )
                        wall_mask, ceiling_mask = await asyncio.to_thread(
                            lambda wl, c: (
                                snap_mask_to_lines(wl, mlsd_segments),
                                snap_mask_to_lines(c, mlsd_segments),
                            ),
                            wall_mask, ceiling_mask,
                        )
                    except Exception as exc:
                        logger.warning("Edge snapping skipped: %s", exc)

                if obj_excl is not None:
                    wall_mask    = (wall_mask    & ~(obj_excl > 0)).astype(np.uint8)
                    ceiling_mask = (ceiling_mask & ~(obj_excl > 0)).astype(np.uint8)

                # Color-coherence expansion + wall-behind-furniture inference
                chromatic = wall_is_chromatic(wall_mask, image_bgr)
                obj_carve = obj_tight if chromatic else (
                    obj_excl if obj_excl is not None else obj_tight
                )
                forbidden = (
                    (floor_mask > 0).astype(np.uint8)
                    | (ceiling_mask > 0).astype(np.uint8)
                    | (obj_tight > 0 if obj_tight is not None else np.zeros((h, w), np.uint8))
                ).astype(np.uint8)
                wall_mask = await asyncio.to_thread(
                    color_coherence_expand, wall_mask, image_bgr, forbidden
                )
                wall_mask = await asyncio.to_thread(
                    infer_wall_behind_furniture, wall_mask, floor_mask, ceiling_mask, h
                )
                if obj_carve is not None:
                    wall_mask = (wall_mask & ~(obj_carve > 0)).astype(np.uint8)

            yield _sse({"step": 4, "total": 5,
                        "message": "Séparation des plans muraux…"})

            if WALL_PAINT_ENABLED:
                depth_predictor = getattr(request.app.state, "depth_predictor", None)
                labeled_walls   = None
                if depth_predictor is not None:
                    try:
                        depth = await asyncio.to_thread(depth_predictor.predict, image_np)
                        labeled_walls, _ = split_wall_planes(wall_mask, depth)
                    except Exception as exc:
                        logger.warning("Depth RANSAC failed: %s", exc)
                        labeled_walls = None

                if labeled_walls is None or int((labeled_walls > 0).sum()) < 500:
                    if mlsd_segments is not None:
                        labeled_walls, _ = split_wall_planes_with_lines(
                            wall_mask, mlsd_segments
                        )
                    else:
                        _, labeled_walls = cv2.connectedComponents(
                            wall_mask.astype(np.uint8), connectivity=8
                        )
                        labeled_walls = labeled_walls.astype(np.uint8)

                floor_mask, labeled_walls, ceiling_mask_out = fill_surface_gaps(
                    floor_mask, labeled_walls, ceiling_mask
                )
                labeled_walls[obj_carve > 0] = 0
                ceiling_mask_out = (ceiling_mask_out & ~(obj_carve > 0)).astype(np.uint8)
                if WALL_FILL_GAPS_PX > 0 and obj_tight is not None:
                    labeled_walls = grow_walls_to_objects(
                        labeled_walls, floor_mask, ceiling_mask_out, obj_tight, WALL_FILL_GAPS_PX
                    )

                # Guarantee full wall coverage (no unpainted tile centres).
                paintable = ((wall_mask > 0) & ~(obj_carve > 0)).astype(np.uint8)
                labeled_walls = _reconcile_labels_to_mask(labeled_walls, paintable)

                # Close junction halos so painting leaves no coloured strip.
                labeled_walls = close_wall_halos(
                    labeled_walls, floor_mask, ceiling_mask_out, obj_carve
                )

            yield _sse({"step": 5, "total": 5,
                        "message": "Compression et envoi des résultats…"})

            labels: list[dict] = []
            fc = _get_centroid(floor_mask)
            if fc:
                labels.append({"text": "Sol", "x": fc["x"], "y": fc["y"],
                                "type": "floor", "id": "floor"})

            if WALL_PAINT_ENABLED:
                wall_count = 0
                for pid in np.unique(labeled_walls):
                    if pid == 0:
                        continue
                    piece = labeled_walls == pid
                    if int(piece.sum()) < 500:
                        continue
                    ys_p, xs_p = np.where(piece)
                    wall_count += 1
                    labels.append({"text": "Mur",
                                   "x": float(xs_p.mean()), "y": float(ys_p.mean()),
                                   "type": "wall", "id": str(int(pid))})
                ceil_c = _get_centroid(ceiling_mask_out)
                if ceil_c:
                    labels.append({"text": "Plafond",
                                   "x": ceil_c["x"], "y": ceil_c["y"],
                                   "type": "ceiling", "id": "ceiling"})

            object_labeled  = np.zeros((h, w), np.uint8)
            opening_labeled = np.zeros((h, w), np.uint8)
            if WALL_PAINT_ENABLED and object_mask is not None:
                opix = object_mask  > 0
                wpix = opening_mask > 0
                if opix.any() or wpix.any():
                    surfaces = [(255, (ceiling_mask_out > 0).astype(np.uint8))]
                    for wid in [int(i) for i in np.unique(labeled_walls) if i != 0]:
                        surfaces.append((wid, (labeled_walls == wid).astype(np.uint8)))
                    best    = np.full((h, w), np.inf, np.float32)
                    nearest = np.zeros((h, w), np.int32)
                    for sid, sm in surfaces:
                        if not sm.any():
                            continue
                        dist = cv2.distanceTransform(1 - sm, cv2.DIST_L2, 3)
                        upd = dist < best
                        best[upd]    = dist[upd]
                        nearest[upd] = sid
                    object_labeled[opix]  = nearest[opix].astype(np.uint8)
                    opening_labeled[wpix] = nearest[wpix].astype(np.uint8)

            b64 = _encode_payload(labels, h, w,
                                   floor_mask, labeled_walls, ceiling_mask_out,
                                   object_labeled, opening_labeled)
            yield _sse({"step": "done", "binary": b64, "mode": "all"})

        except Exception as exc:
            logger.error("auto-detect error: %s", exc, exc_info=True)
            yield _sse({"step": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Debug — visual overlay of the detected surfaces (diagnostics)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/debug-walls")
async def debug_walls(
    request: Request,
    image: UploadFile = File(...),
):
    """Return a PNG overlay of the full wall pipeline for visual diagnosis.

    Upload an image (e.g. via Swagger at /docs) and inspect the returned PNG:
      • green   = floor
      • blue    = ceiling
      • red     = wall (after refinement + color-coherence expansion)
      • yellow  = excluded objects / openings

    Shows EXACTLY what the detector produces, so wall-coverage problems can be
    seen directly instead of inferred from the painted result.
    """
    from fastapi.responses import Response

    image_data = await image.read()
    pil_image  = Image.open(io.BytesIO(image_data)).convert("RGB")
    image_np   = np.array(pil_image)
    image_bgr  = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    h, w = image_np.shape[:2]

    (floor_mask, wall_seed, ceiling_mask,
     object_mask, opening_mask) = await _run_segmentation(request, image_np)
    floor_mask   = (floor_mask   > 0).astype(np.uint8)
    ceiling_mask = (ceiling_mask & ~(floor_mask > 0)).astype(np.uint8)
    wall_seed    = (wall_seed & ~(floor_mask > 0) & ~(ceiling_mask > 0)).astype(np.uint8)
    if object_mask  is None: object_mask  = np.zeros((h, w), np.uint8)
    if opening_mask is None: opening_mask = np.zeros((h, w), np.uint8)
    obj_tight = (((object_mask > 0) | (opening_mask > 0)) & ~(floor_mask > 0)).astype(np.uint8)

    # Depth + floor/ceiling strengthening
    depth_predictor = getattr(request.app.state, "depth_predictor", None)
    depth = None
    if depth_predictor is not None:
        try:
            depth = depth_predictor.predict(image_np)
        except Exception:
            depth = None
    floor_strong, ceiling_strong = floor_mask.copy(), ceiling_mask.copy()
    if depth is not None:
        try:
            df, dc = horizontal_surfaces_from_depth(depth)
            floor_strong   = ((floor_strong   > 0) | (df > 0)).astype(np.uint8)
            ceiling_strong = ((ceiling_strong > 0) | (dc > 0)).astype(np.uint8)
            ceiling_strong = (ceiling_strong & ~(floor_strong > 0)).astype(np.uint8)
        except Exception:
            pass

    # Comprehensive clutter (everything not wall/floor/ceiling) + detected objects
    clutter = (~((wall_seed > 0) | (floor_strong > 0) | (ceiling_strong > 0))).astype(np.uint8)
    obj_carve = ((clutter > 0) | (obj_tight > 0)).astype(np.uint8)
    obj_carve = cv2.dilate(obj_carve, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    obj_carve = (obj_carve & ~(floor_strong > 0)).astype(np.uint8)

    # Wall = semantic wall class, bounded away from clutter/floor/ceiling
    wall_ref = sharpen_wall_boundary(refine_mask(wall_seed, image_bgr), image_bgr)
    wall_ref = (wall_ref & ~(obj_carve > 0) & ~(floor_strong > 0)
                & ~(ceiling_strong > 0)).astype(np.uint8)
    ceiling_mask = ceiling_strong
    obj_tight = obj_carve  # overlay shows the full clutter exclusion

    # Plane split + reconcile + halo close — the EXACT mask that gets painted.
    labeled = None
    if depth is not None:
        try:
            labeled, _ = split_wall_planes(wall_ref, depth)
        except Exception:
            labeled = None
    if labeled is None or int((labeled > 0).sum()) < 500:
        _, labeled = cv2.connectedComponents(wall_ref.astype(np.uint8), connectivity=8)
        labeled = labeled.astype(np.uint8)
    labeled = _reconcile_labels_to_mask(labeled, wall_ref)
    labeled = close_wall_halos(labeled, floor_strong, ceiling_mask, obj_carve)

    overlay = image_bgr.copy().astype(np.float32)
    def _blend(mask, color, a=0.5):
        sel = mask > 0
        overlay[sel] = (1 - a) * overlay[sel] + a * np.array(color, np.float32)
    _blend(floor_mask,   (0, 200, 0))       # green
    _blend(ceiling_mask, (255, 100, 0))     # blue
    # Per-plane colors so plane splitting is visible too
    plane_colors = [(0,0,255), (255,0,255), (255,255,0), (0,128,255), (128,0,255)]
    for i, pid in enumerate([p for p in np.unique(labeled) if p != 0]):
        _blend((labeled == pid).astype(np.uint8), plane_colors[i % len(plane_colors)])
    _blend(obj_tight,    (0, 255, 255))     # yellow

    _, buf = cv2.imencode(".png", overlay.astype(np.uint8))
    return Response(content=buf.tobytes(), media_type="image/png")
