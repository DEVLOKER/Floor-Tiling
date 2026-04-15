# ── Floor Tiling Visualizer — Production Dockerfile ───────────────────────
# Model: facebook/mask2former-swin-base-IN21k-ade-semantic
# SAM2 removed — segmentation is handled entirely by Mask2Former.

ARG MODEL_SOURCE=download

# ==========================================================================
# Stage 1: Model Provider
#   download mode → wget from CDNs
#   local mode    → copy from build context
# ==========================================================================
FROM alpine:latest AS downloader
ARG MODEL_SOURCE

RUN apk add --no-cache wget

WORKDIR /models

# Copy local weight folder (may be empty if files are ignored by .dockerignore)
COPY client/mask2former/models/ mask2former/

# Download weights only when MODEL_SOURCE=download
# Model: facebook/mask2former-swin-base-IN21k-ade-semantic
RUN if [ "$MODEL_SOURCE" = "download" ]; then \
        echo "▶ [downloader] Downloading Mask2Former swin-base weights ..."; \
        wget -q --show-progress -O mask2former/pytorch_model.bin \
            https://huggingface.co/facebook/mask2former-swin-base-IN21k-ade-semantic/resolve/main/pytorch_model.bin; \
    fi

# ==========================================================================
# Stage 2: Cython Builder
#   Compiles proprietary Python modules (config, core, mask2former, patterns,
#   processors) to native .so extensions, then strips the .py source files.
#   Only the compiled binaries (+ server.py entry-point) reach the final
#   runtime image, making source recovery very difficult.
#   Note: ARG MODEL_SOURCE is not needed here — this stage is model-agnostic.
# ==========================================================================
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared folder from build context root
COPY shared ./shared

# Install Cython and conversion requirements (CPU-only torch/transformers)
# We install these in builder to perform on-the-fly weights conversion.
RUN pip install --no-cache-dir cython \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers scipy

# Copy application source
COPY client/. .

# Inject Mask2Former weights from downloader stage
COPY --from=downloader /models/mask2former/ mask2former/models/

# Compile AND convert weights
RUN python setup_cython.py build_ext --inplace \
    && python mask2former/convert_to_safetensors.py \
    && rm -f mask2former/models/pytorch_model.bin

# Strip .py source files from compiled packages (keep server.py)
RUN find config core mask2former patterns processors \
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

# Copy shared folder from build context root
COPY shared ./shared

# --------------------------------------------------------------------------
# 3. Python dependencies
#    requirements.txt includes --extra-index-url for the PyTorch CPU index
#    and pins torch/torchvision+cpu, so a single pip install handles everything.
# --------------------------------------------------------------------------
COPY client/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------------
# 4. Application code (compiled artifacts from builder — no .py sources
#    for business-logic packages; only server.py is plain Python)
# --------------------------------------------------------------------------
COPY --chown=appuser:appuser --from=builder /app .

# --------------------------------------------------------------------------
# 5. Runtime environment
# --------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # Override in docker-compose / runtime for dev (reload=true, workers=1)
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_WORKERS=1 \
    APP_LOG_LEVEL=info

USER appuser

EXPOSE 8000

# --------------------------------------------------------------------------
# 7. Health check (Mask2Former swin-base loads at startup; allow 120 s warm-up)
# --------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
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
