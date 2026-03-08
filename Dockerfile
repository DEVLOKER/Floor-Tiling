# ── Floor Tile Visualizer — Production Dockerfile ──────────────────────────

# ==========================================================================
# Stage 1: Model Downloader
#   Uses a minimal Alpine image to fetch SAM2 checkpoints from Meta's CDN.
#   This entire layer is cached by Docker — models are never re-downloaded
#   unless the URLs (or this RUN command) change, regardless of how often
#   the application code is rebuilt.
# ==========================================================================
FROM alpine:latest AS downloader

RUN apk add --no-cache wget

WORKDIR /models

# RUN wget -q -O sam2.1_hiera_tiny.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt 
# RUN wget -q -O sam2.1_hiera_small.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt \
# RUN wget -q -O sam2.1_hiera_base_plus.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt \
# RUN wget -q -O sam2.1_hiera_large.pt https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt

# ==========================================================================
# Stage 2: Cython Builder
#   Compiles proprietary Python modules (config, core, ml_models, patterns,
#   processors) to native .so extensions, then strips the .py source files.
#   Only the compiled binaries (+ server.py entry-point) reach the final
#   runtime image, making source recovery very difficult.
# ==========================================================================
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Cython (only needed for compilation, not in runtime image)
RUN pip install --no-cache-dir cython

# Copy application source
COPY . .

# Compile custom modules to C extensions
RUN python setup_cython.py build_ext --inplace

# Strip .py source files from compiled packages (keep server.py + sam2/)
RUN find config core ml_models patterns processors \
        -name "*.py" -delete \
    && find . -name "*.c" -delete \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove the build script itself — no reason to ship it
RUN rm -f setup_cython.py

# ==========================================================================
# Stage 3: Final Runtime
#   Slim Python image with all dependencies and compiled application code.
#   Models are injected from Stage 1 — the runtime image itself never needs
#   network access to Meta's CDN.
# ==========================================================================
FROM python:3.11-slim

# --------------------------------------------------------------------------
# 1. System dependencies
#    libgl1 + libglib2.0-0 → OpenCV headless requirement
#    libsm6 libxext6 libxrender1 → some OpenCV codecs
# --------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# 2. Non-root user (security best practice)
# --------------------------------------------------------------------------
RUN useradd -m -u 1000 appuser

WORKDIR /app

# --------------------------------------------------------------------------
# 3. Python dependencies — ordered for maximum layer-cache reuse
#
#    Install CPU-only torch FIRST (largest layer, changes rarely).
#    Using the official PyTorch CPU index avoids pulling the multi-GB
#    CUDA variant that pip would pick from PyPI by default.
# --------------------------------------------------------------------------
RUN pip install --no-cache-dir \
        torch==2.3.0 \
        torchvision==0.18.0 \
        --index-url https://download.pytorch.org/whl/cpu

# Copy requirements separately so the layer is only rebuilt when it changes.
COPY requirements.txt .

# torch/torchvision already satisfy the >=2.3.0 constraint — pip will skip them.
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------------
# 4. Application code (compiled artifacts from builder — no .py sources
#    for business-logic packages; only server.py + sam2/ are plain Python)
# --------------------------------------------------------------------------
COPY --chown=appuser:appuser --from=builder /app .

# --------------------------------------------------------------------------
# 5. SAM2 model checkpoints (copied from Stage 1)
#    Placed AFTER "COPY . ." so the downloaded weights always take precedence
#    over any .pt files that may exist locally (e.g. in sam2/models/).
# --------------------------------------------------------------------------
COPY --chown=appuser:appuser --from=downloader /models/ ./sam2/models/

# --------------------------------------------------------------------------
# 6. Runtime environment
# --------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Add /app to PYTHONPATH so `sam2`, `config`, etc. are importable
    PYTHONPATH=/app \
    # Override in docker-compose / runtime for dev (reload=true, workers=1)
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_WORKERS=1 \
    APP_LOG_LEVEL=info

USER appuser

EXPOSE 8000

# --------------------------------------------------------------------------
# 7. Health check (SAM2 loads at startup; give it 90 s to warm up)
# --------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

# --------------------------------------------------------------------------
# 8. Entrypoint — uvicorn in production mode (no reload, no debug)
# --------------------------------------------------------------------------
CMD ["uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--h11-max-incomplete-event-size", "104857600"]
