# ── Floor Tiling Visualizer — Production Dockerfile ───────────────────────
# Models (all loaded offline at runtime from the image):
#   • Segmentation : facebook/mask2former-swin-large-ade-semantic
#                  + shi-labs/oneformer_ade20k_swin_large   (ensembled)
#   • Depth        : depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf
#
# MODEL_SOURCE=download (default) → fetch weights from Hugging Face at build.
# MODEL_SOURCE=local             → use weights bundled in the build context
#                                   (kept via .dockerignore negations).
# MODEL_SOURCE=volume            → ship NO weights; mount a writable volume at
#                                   /models and let the app download once into
#                                   it (set MASK2FORMER_DIR/DEPTH_DIR — see
#                                   docker-compose.yml). Leanest image.

ARG MODEL_SOURCE=download

# ==========================================================================
# Stage 1: Model Provider
#   download mode → wget the .safetensors weights from Hugging Face
#   local mode    → use weights already copied from the build context
#   Small files (config.json, preprocessor_config.json, .model_id) always come
#   from the context, so only the large weights are ever downloaded.
# ==========================================================================
FROM alpine:latest AS downloader
ARG MODEL_SOURCE

RUN apk add --no-cache wget

WORKDIR /models

# Configs (+ local weights when bundled) from the build context.
COPY client/models/mask2former/ mask2former/
COPY client/models/oneformer/ oneformer/
COPY client/models/depth/ depth/

RUN case "$MODEL_SOURCE" in \
      download) \
        echo "▶ [downloader] Mask2Former swin-large weights ..."; \
        wget -q --show-progress -O mask2former/model.safetensors \
            https://huggingface.co/facebook/mask2former-swin-large-ade-semantic/resolve/main/model.safetensors; \
        echo "▶ [downloader] OneFormer ade20k swin-large weights ..."; \
        wget -q --show-progress -O oneformer/model.safetensors \
            https://huggingface.co/shi-labs/oneformer_ade20k_swin_large/resolve/main/model.safetensors; \
        echo "▶ [downloader] Depth-Anything-V2 metric-indoor-base weights ..."; \
        wget -q --show-progress -O depth/model.safetensors \
            https://huggingface.co/depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf/resolve/main/model.safetensors; \
        ;; \
      local) \
        echo "▶ [downloader] MODEL_SOURCE=local — using weights bundled in the build context"; \
        ;; \
      volume) \
        echo "▶ [downloader] MODEL_SOURCE=volume — no weights baked; provided at runtime"; \
        rm -f mask2former/model.safetensors oneformer/model.safetensors depth/model.safetensors; \
        ;; \
      *) echo "Unknown MODEL_SOURCE=$MODEL_SOURCE" >&2; exit 1; ;; \
    esac

# ==========================================================================
# Stage 2: Cython Builder
#   Compiles proprietary Python modules (config, core, depth, mask2former,
#   patterns, processors, utils) to native .so extensions, then strips the .py
#   source.  Only compiled binaries (+ the app/__main__ entry points) reach runtime,
#   making source recovery very difficult.
#
#   Cython only transpiles/compiles C — it does NOT import the modules' runtime
#   dependencies — so this stage needs nothing more than a C toolchain + Cython.
# ==========================================================================
FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Shared package lives at the repo root.
COPY shared ./shared

RUN pip install --no-cache-dir cython

# Application source.
COPY client/. .

# Inject model weights (+ configs) from the downloader stage into the cache dir
# that floor_tiling.paths.MODELS_DIR points at (<app>/models/<name>).
COPY --from=downloader /models/mask2former/ models/mask2former/
COPY --from=downloader /models/oneformer/ models/oneformer/
COPY --from=downloader /models/depth/ models/depth/

# Compile proprietary packages to .so.
RUN python setup_cython.py build_ext --inplace

# Strip .py / .c sources from the compiled subpackages (keep app.py / __main__.py
# and the api routing layer as plain Python; leave third-party untouched).
RUN cd src/floor_tiling \
    && find config core ml patterns processors licensing -name "*.py" -delete \
    && find config core ml patterns processors licensing -name "*.c" -delete \
    && cd /app \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove the build script — no reason to ship it.
RUN rm -f setup_cython.py

# ==========================================================================
# Stage 3: Final Runtime
#   Slim Python image with dependencies + compiled application code + bundled
#   models.  Needs no network access at runtime.
# ==========================================================================
FROM python:3.11-slim

# --------------------------------------------------------------------------
# 1. System dependencies
#    libgl1 + libglib2.0-0 → OpenCV runtime requirement
#    (headless OpenCV avoids the X11/GUI libs the GUI build needs)
# --------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# 2. Non-root user (security best practice)
# --------------------------------------------------------------------------
RUN useradd -m -u 1000 appuser

# Writable mount point for the optional model-cache volume (MODEL_SOURCE=volume).
# Creating it owned by appuser means a fresh named volume mounted here inherits
# that ownership, so the app (uid 1000) can write the downloaded weights.
RUN mkdir -p /models/mask2former /models/oneformer /models/depth && chown -R appuser:appuser /models

WORKDIR /app

# Shared package from the build context root.
COPY shared ./shared

# --------------------------------------------------------------------------
# 3. Python dependencies
#    requirements.txt carries the PyTorch CPU extra-index and pins torch/
#    torchvision+cpu, so a single pip install handles everything.
# --------------------------------------------------------------------------
COPY client/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------------------------
# 4. Application code (compiled artifacts from builder — no .py sources for
#    business-logic packages; only app.py / __main__.py / api stay plain Python)
# --------------------------------------------------------------------------
COPY --chown=appuser:appuser --from=builder /app .

# --------------------------------------------------------------------------
# 5. Runtime environment
# --------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

USER appuser

EXPOSE 8000

# --------------------------------------------------------------------------
# 6. Health check
#    Three models load at startup on CPU (~866 MB + ~879 MB segmentation
#    ensemble + ~390 MB depth), so allow a generous warm-up.
# --------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=360s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

# --------------------------------------------------------------------------
# 7. Entrypoint — uvicorn in production mode (no reload, no debug)
# --------------------------------------------------------------------------
CMD ["uvicorn", "floor_tiling.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--h11-max-incomplete-event-size", "104857600"]
