from config.settings import (MAX_UPLOAD_SIZE_BYTES)
from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = MAX_UPLOAD_SIZE_BYTES

"""Floor Tile Visualizer — entry point.

Starts Uvicorn with the application defined in ``app.py``.

Run in development:
    python server.py

Run with Uvicorn CLI (recommended for production):
    uvicorn app:app --host 0.0.0.0 --port 8000 --h11-max-incomplete-event-size 104857600
"""

# Re-export ``app`` so PyInstaller and legacy ``uvicorn server:app`` still work.
from app import app  # noqa: F401  (used by uvicorn "server:app" string)

if __name__ == "__main__":
    import sys
    import uvicorn
    # from shared.utils.ssl_cert import ensure_ssl_cert

    # ssl_certfile, ssl_keyfile = ensure_ssl_cert()
    _frozen = getattr(sys, "frozen", False)  # True when running as PyInstaller exe

    uvicorn.run(
        # Object form for frozen exe (reload=False); string form enables hot-reload in dev.
        app if _frozen else "app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=not _frozen, # reload=True,  # dev only; breaks frozen exe (spawn loop)
        # ssl_certfile=ssl_certfile,
        # ssl_keyfile=ssl_keyfile,
        limit_max_requests=MAX_SIZE,
        limit_max_requests_jitter=MAX_SIZE,        
        h11_max_incomplete_event_size=MAX_UPLOAD_SIZE_BYTES,  # large mask payloads
    )
