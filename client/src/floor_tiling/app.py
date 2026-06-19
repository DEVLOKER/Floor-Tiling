"""Floor Tile Visualizer — FastAPI application factory.

Wires up middleware, lifespan (license + model loading), static files,
and all API routers.  Import ``app`` from here for Uvicorn or testing.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import torch

from floor_tiling.api.dependencies import require_license
from floor_tiling.api.routes.detection import router as detection_router
from floor_tiling.api.routes.paint import router as paint_router
from floor_tiling.api.routes.tiles import router as tiles_router
from floor_tiling.config.settings import (
    CORS_ORIGINS,
    MAX_UPLOAD_SIZE_BYTES,
    SEG_USE_MASK2FORMER,
    SEG_USE_ONEFORMER,
)
from floor_tiling.ml import (
    get_mask2former_predictor,
    get_oneformer_predictor,
    get_depth_predictor,
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

    # ── License check ─────────────────────────────────────────────────────
    try:
        verify_license()
    except LicenseError as exc:
        logger.critical("License check failed: %s", exc)
        sys.exit(1)

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
    try:
        app.state.depth_predictor = await asyncio.to_thread(get_depth_predictor)
        logger.info("Depth model ready.")
    except Exception as exc:
        logger.error("Failed to load depth model: %s", exc, exc_info=True)
        app.state.depth_predictor = None

    yield  # ── server is running ─────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""

    _app = FastAPI(
        title="Floor Tile Visualizer",
        description="Floor segmentation and perspective-correct tile visualization",
        version="1.0.0",
        lifespan=lifespan,
        dependencies=[Depends(require_license)],
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
    _app.include_router(paint_router)

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
