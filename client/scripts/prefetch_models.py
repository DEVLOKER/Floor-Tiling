"""Pre-fetch (download + bake) every model the app would load on startup.

Used at Docker *build* time to bake an offline, profile-specific image, and can
also be run once at runtime to warm a mounted model volume.

Which models are fetched is driven entirely by the same settings the server
honours at startup (DETECTION_PROFILE / *_VARIANT / SEG_USE_* / OPEN_VOCAB_* /
PAINT_REFINE_MATTING) — all of which are environment-overridable. So:

    DETECTION_PROFILE=fast python scripts/prefetch_models.py

bakes exactly the "fast" set into MODELS_DIR. Weights land in the same cache the
app reads from, so a later run with HF_HUB_OFFLINE=1 needs no network.

Run with PYTHONPATH=src (the project's src-layout), e.g.:
    PYTHONPATH=src python scripts/prefetch_models.py
"""
from __future__ import annotations

import logging
import sys

from floor_tiling.config import settings
from floor_tiling.ml import (
    get_mask2former_predictor,
    get_oneformer_predictor,
    get_depth_predictor,
    get_mlsd_predictor,
    get_grounding_dino_predictor,
    get_yolo_world_predictor,
    get_sam_predictor,
    get_matting_predictor,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logger = logging.getLogger("prefetch")


def _fetch(label: str, getter) -> bool:
    """Instantiate one manager (triggering its download/bake). Returns ok."""
    logger.info("▶ fetching %s …", label)
    try:
        getter()
        logger.info("✓ %s ready", label)
        return True
    except Exception as exc:  # noqa: BLE001 — report and continue
        logger.error("✗ %s failed: %s", label, exc, exc_info=True)
        return False


def main() -> int:
    logger.info(
        "Prefetch — profile=%s  m2f=%s one=%s depth=%s yolo=%s gdino=%s sam=%s vitmatte=%s",
        settings.DETECTION_PROFILE,
        settings.MASK2FORMER_VARIANT, settings.ONEFORMER_VARIANT,
        settings.DEPTH_VARIANT, settings.YOLO_WORLD_VARIANT,
        settings.GROUNDING_DINO_VARIANT, settings.SAM_VARIANT,
        settings.VITMATTE_VARIANT,
    )

    ok = True

    # Surface segmentation (mirrors the SEG_USE_* flags).
    if settings.SEG_USE_MASK2FORMER:
        ok &= _fetch("Mask2Former", get_mask2former_predictor)
    if settings.SEG_USE_ONEFORMER:
        ok &= _fetch("OneFormer", get_oneformer_predictor)

    # Depth + line detector — always loaded by the app (best-effort there too).
    ok &= _fetch("Depth-Anything-V2", get_depth_predictor)
    ok &= _fetch("M-LSD", get_mlsd_predictor)

    # Open-vocabulary object detector (+ SAM) — only the chosen backend.
    if settings.USE_OPEN_VOCAB_OBJECTS:
        if settings.OPEN_VOCAB_DETECTOR == "grounding_dino":
            ok &= _fetch("Grounding DINO", get_grounding_dino_predictor)
        else:
            ok &= _fetch("YOLO-World (+bake)", get_yolo_world_predictor)
        ok &= _fetch("SAM", get_sam_predictor)

    # Edge matting — only when enabled.
    if settings.PAINT_REFINE_MATTING:
        ok &= _fetch("ViTMatte", get_matting_predictor)

    if not ok:
        logger.error("One or more models failed to prefetch.")
        return 1
    logger.info("All requested models prefetched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
