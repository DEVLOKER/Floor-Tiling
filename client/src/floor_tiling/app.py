"""Floor Tile Visualizer — FastAPI application factory.

Wires up middleware, lifespan (license + model loading), static files,
and all API routers.  Import ``app`` from here for Uvicorn or testing.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import json

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import torch

from floor_tiling.api.dependencies import require_license
from floor_tiling.api.routes.detection import router as detection_router
from floor_tiling.api.routes.paint import router as paint_router
from floor_tiling.api.routes.tiles import router as tiles_router
from floor_tiling.config.settings import (
    CORS_ORIGINS,
    MAX_UPLOAD_SIZE_BYTES,
    WALL_PAINT_ENABLED,
    SEG_USE_MASK2FORMER,
    SEG_USE_ONEFORMER,
    USE_OPEN_VOCAB_OBJECTS,
    OPEN_VOCAB_DETECTOR,
    OPEN_VOCAB_OBJECT_PROMPT,
    OPEN_VOCAB_BOX_THRESHOLD,
    OPEN_VOCAB_TEXT_THRESHOLD,
    YOLO_WORLD_CONF,
    DEFAULT_TILE_WIDTH, DEFAULT_TILE_HEIGHT,
    DEFAULT_GROUT_THICKNESS, DEFAULT_PATTERN,
    DEFAULT_TRANSLATE_X, DEFAULT_TRANSLATE_Y,
    DEFAULT_PERSPECTIVE_COMPRESSION,
    DEFAULT_PAINT_COLOR, DEFAULT_PAINT_FINISH, PAINT_FINISHES,
    TILE_WIDTH_MIN, TILE_WIDTH_MAX,
    TILE_HEIGHT_MIN, TILE_HEIGHT_MAX,
    GROUT_THICKNESS_MIN, GROUT_THICKNESS_MAX,
    PAINT_REFINE_MATTING,
)
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
from floor_tiling.licensing import verify_license, LicenseError

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logger = logging.getLogger(__name__)

# Resolved path of this file's directory (used to locate static assets)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify license and load ML models.  Shutdown: nothing extra."""

    # ── Write server-side config for the frontend ─────────────────────────
    config_js_path = os.path.join(_BASE_DIR, "static", "config.js")
    try:
        with open(config_js_path, "w", encoding="utf-8") as _f:
            _f.write(f"window.__APP_CONFIG__ = {json.dumps(_build_frontend_config())};")
        logger.info("Frontend config written to %s", config_js_path)
    except PermissionError:
        logger.warning("Cannot write %s (permission denied) — frontend will use fallback defaults.", config_js_path)

    # ── License check ─────────────────────────────────────────────────────
    # NOTE: temporarily disabled (re-enable for licensed/production builds).
    # try:
    #     verify_license()
    # except LicenseError as exc:
    #     logger.critical("License check failed: %s", exc)
    #     sys.exit(1)

    # ── Load segmentation model(s) — see SEG_USE_* flags in settings ──────
    app.state.mask2former_predictor = None
    if SEG_USE_MASK2FORMER:
        try:
            app.state.mask2former_predictor = await asyncio.to_thread(
                get_mask2former_predictor
            )
            logger.info("Mask2Former model ready.")
        except Exception as exc:
            logger.error("Failed to load Mask2Former: %s", exc, exc_info=True)
    else:
        logger.info("Mask2Former disabled (SEG_USE_MASK2FORMER=False).")

    app.state.oneformer_predictor = None
    if SEG_USE_ONEFORMER:
        try:
            app.state.oneformer_predictor = await asyncio.to_thread(get_oneformer_predictor)
            logger.info("OneFormer model ready.")
        except Exception as exc:
            logger.error("Failed to load OneFormer: %s", exc, exc_info=True)
    else:
        logger.info("OneFormer disabled (SEG_USE_ONEFORMER=False).")

    # ── Load depth model (for per-wall plane separation) ──────────────────
    # Best-effort: if it fails, detection falls back to connected components.
    app.state.depth_predictor = None
    if WALL_PAINT_ENABLED:
        try:
            app.state.depth_predictor = await asyncio.to_thread(get_depth_predictor)
            logger.info("Depth model ready.")
        except Exception as exc:
            logger.error("Failed to load depth model: %s", exc, exc_info=True)
    else:
        logger.info("Depth model skipped (WALL_PAINT_ENABLED=False).")

    # ── Load M-LSD (line detector for wall edge snapping) ────────────────
    # Best-effort: if it fails, the depth tiler falls back to the floor-quad.
    app.state.mlsd_predictor = None
    if WALL_PAINT_ENABLED:
        try:
            app.state.mlsd_predictor = await asyncio.to_thread(get_mlsd_predictor)
            logger.info("M-LSD model ready.")
        except Exception as exc:
            logger.error("Failed to load M-LSD: %s", exc, exc_info=True)
    else:
        logger.info("M-LSD skipped (WALL_PAINT_ENABLED=False).")

    # ── Load open-vocab object detector + SAM (wall objects to exclude) ────
    app.state.object_detector = None
    app.state.sam_predictor = None
    if WALL_PAINT_ENABLED and USE_OPEN_VOCAB_OBJECTS:
        try:
            if OPEN_VOCAB_DETECTOR == "grounding_dino":
                app.state.object_detector = await asyncio.to_thread(get_grounding_dino_predictor)
            else:
                app.state.object_detector = await asyncio.to_thread(get_yolo_world_predictor)
            app.state.sam_predictor = await asyncio.to_thread(get_sam_predictor)
            logger.info("Open-vocab detector (%s) + SAM ready.", OPEN_VOCAB_DETECTOR)
        except Exception as exc:
            logger.error("Failed to load open-vocab detector/SAM: %s", exc, exc_info=True)
            app.state.object_detector = None
            app.state.sam_predictor = None
    else:
        logger.info("Open-vocab object exclusion skipped (WALL_PAINT_ENABLED=False or USE_OPEN_VOCAB_OBJECTS=False).")

    # ── Load ViTMatte (refines paint edges around fine foliage) ───────────
    app.state.matting_predictor = None
    if WALL_PAINT_ENABLED and PAINT_REFINE_MATTING:
        try:
            app.state.matting_predictor = await asyncio.to_thread(get_matting_predictor)
            logger.info("ViTMatte model ready.")
        except Exception as exc:
            logger.error("Failed to load ViTMatte: %s", exc, exc_info=True)
    else:
        logger.info("Paint matting skipped (WALL_PAINT_ENABLED=False or PAINT_REFINE_MATTING=False).")

    # ── Warm up models (one dummy inference) ──────────────────────────────
    # The FIRST real inference of each model is 2-4× slower due to lazy graph
    # init. Running a tiny dummy now moves that cost to startup, so the user's
    # first detection isn't penalised. Best-effort: never block startup.
    try:
        import numpy as _np
        # Warm at a realistic resolution (~the app's 1000px-wide working size) —
        # CPU kernels auto-tune per input shape, so warming a tiny image wouldn't
        # speed up the first real (large) detection.
        dummy = _np.full((750, 1000, 3), 127, dtype=_np.uint8)

        def _warmup():
            for p in (
                app.state.mask2former_predictor,
                app.state.oneformer_predictor,
                app.state.depth_predictor,
                app.state.mlsd_predictor,
            ):
                if p is not None:
                    try:
                        p.predict(dummy)
                    except Exception:
                        pass
            det = app.state.object_detector
            if det is not None:
                try:
                    if OPEN_VOCAB_DETECTOR == "grounding_dino":
                        det.detect(dummy, OPEN_VOCAB_OBJECT_PROMPT,
                                   OPEN_VOCAB_BOX_THRESHOLD, OPEN_VOCAB_TEXT_THRESHOLD)
                    else:
                        det.detect(dummy, YOLO_WORLD_CONF)
                except Exception:
                    pass
            if app.state.sam_predictor is not None:
                try:
                    app.state.sam_predictor.segment_boxes(
                        dummy, _np.array([[10, 10, 120, 120]], dtype=_np.float32))
                except Exception:
                    pass
            if app.state.matting_predictor is not None:
                try:
                    app.state.matting_predictor.matte(
                        dummy, _np.ones((256, 256), dtype=_np.uint8))
                except Exception:
                    pass

        await asyncio.to_thread(_warmup)
        logger.info("Model warmup complete — first detection will be fast.")
    except Exception as exc:
        logger.warning("Model warmup skipped: %s", exc)

    yield  # ── server is running ─────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def _build_frontend_config() -> dict:
    """Collect all settings that the frontend needs."""
    return {
        "wallPaintEnabled": WALL_PAINT_ENABLED,
        "defaultTileWidth": DEFAULT_TILE_WIDTH,
        "defaultTileHeight": DEFAULT_TILE_HEIGHT,
        "defaultGrout": DEFAULT_GROUT_THICKNESS,
        "defaultPattern": DEFAULT_PATTERN,
        "defaultTranslateX": DEFAULT_TRANSLATE_X,
        "defaultTranslateY": DEFAULT_TRANSLATE_Y,
        "defaultPerspectiveCompression": DEFAULT_PERSPECTIVE_COMPRESSION,
        "tileWidthMin": TILE_WIDTH_MIN,
        "tileWidthMax": TILE_WIDTH_MAX,
        "tileHeightMin": TILE_HEIGHT_MIN,
        "tileHeightMax": TILE_HEIGHT_MAX,
        "groutThicknessMin": GROUT_THICKNESS_MIN,
        "groutThicknessMax": GROUT_THICKNESS_MAX,
        "defaultPaintColor": DEFAULT_PAINT_COLOR,
        "defaultPaintFinish": DEFAULT_PAINT_FINISH,
        "paintFinishes": list(PAINT_FINISHES),
    }


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""

    _app = FastAPI(
        title="Floor Tile Visualizer",
        description="Floor segmentation and perspective-correct tile visualization",
        version="1.0.0",
        lifespan=lifespan,
        # NOTE: license gate temporarily disabled (re-enable for production).
        # dependencies=[Depends(require_license)],
    )

    # ── Request size limit ────────────────────────────────────────────────
    _app.state.limit_max_request_body = MAX_UPLOAD_SIZE_BYTES

    # ── CORS ──────────────────────────────────────────────────────────────
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static files ──────────────────────────────────────────────────────
    _app.mount(
        "/static",
        StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
        name="static",
    )

    # ── API routers ───────────────────────────────────────────────────────
    _app.include_router(detection_router)
    _app.include_router(tiles_router)
    if WALL_PAINT_ENABLED:
        _app.include_router(paint_router)
    else:
        logger.info("Paint router disabled (WALL_PAINT_ENABLED=False).")

    # ── Utility routes ────────────────────────────────────────────────────

    @_app.get("/health", tags=["meta"])
    async def health():
        """Health-check endpoint."""
        return {
            "status": "healthy",
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "cuda_available": torch.cuda.is_available(),
        }

    @_app.get("/api", tags=["meta"])
    async def api_info():
        """API information endpoint."""
        return {
            "message": "Floor Tile Visualizer API",
            "status": "running",
            "docs": "/docs",
        }

    @_app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        """Serve the SVG favicon to silence 404s from browsers."""
        return FileResponse(
            os.path.join(_BASE_DIR, "static", "favicon.svg"),
            media_type="image/svg+xml",
        )

    @_app.get("/", response_class=FileResponse, include_in_schema=False)
    async def root():
        """Serve the frontend SPA."""
        return FileResponse(os.path.join(_BASE_DIR, "static", "index.html"))

    return _app


# Module-level app instance (used by Uvicorn and PyInstaller entry-point)
app = create_app()
