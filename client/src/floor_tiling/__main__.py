"""Floor Tiling Visualizer — console entry point.

Starts Uvicorn with the application factory in :mod:`floor_tiling.app`.

Run in development:
    python -m floor_tiling

Run with the Uvicorn CLI (production):
    uvicorn floor_tiling.app:app --host 0.0.0.0 --port 8000 \
        --h11-max-incomplete-event-size 104857600
"""
import sys

from starlette.formparsers import MultiPartParser

from floor_tiling.config.settings import MAX_UPLOAD_SIZE_BYTES

# Allow large multipart bodies (mask payloads) before the app is imported.
MultiPartParser.max_part_size = MAX_UPLOAD_SIZE_BYTES


def main() -> None:
    import uvicorn

    _frozen = getattr(sys, "frozen", False)  # True under a PyInstaller build
    uvicorn.run(
        # Object form for the frozen exe (no reload); import string in dev so
        # hot-reload works.
        "floor_tiling.app:app" if not _frozen else _load_app(),
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=not _frozen,  # dev only; breaks the frozen exe (spawn loop)
        limit_max_requests=MAX_UPLOAD_SIZE_BYTES,
        limit_max_requests_jitter=MAX_UPLOAD_SIZE_BYTES,
        h11_max_incomplete_event_size=MAX_UPLOAD_SIZE_BYTES,  # large mask payloads
    )


def _load_app():
    from floor_tiling.app import app

    return app


if __name__ == "__main__":
    main()
