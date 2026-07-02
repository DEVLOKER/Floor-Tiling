# syntax=docker/dockerfile:1
# ── Floor Tiling Visualizer — production Dockerfile ───────────────────────────
#
# Two build modes (choose with --build-arg WITH_MODELS):
#
#   WITH_MODELS=true  (default)
#       Bake the chosen DETECTION_PROFILE's models INTO the image. The build runs
#       scripts/prefetch_models.py, which instantiates exactly the managers the
#       app loads (per settings) and downloads/bakes their weights into
#       /app/models. Runtime then sets HF_HUB_OFFLINE=1 → fully offline.
#
#   WITH_MODELS=false
#       Ship NO weights (lean image). Mount a writable volume at MODELS_DIR
#       (/app/models) and the app downloads the models once at runtime, persisting
#       them in the volume. Configure everything via env (no rebuild).
#
# Arg-driven profile matrix:
#   docker build --build-arg DETECTION_PROFILE=fast     -t floortiling:fast .
#   docker build --build-arg DETECTION_PROFILE=balanced -t floortiling:balanced .
#   docker build --build-arg DETECTION_PROFILE=quality  -t floortiling:quality .
#   docker build --build-arg WITH_MODELS=false --build-arg HF_HUB_OFFLINE=0 \
#                -t floortiling:slim .
#
# Per-model size overrides (optional, win over the profile):
#   --build-arg SAM_VARIANT=base  --build-arg DEPTH_VARIANT=large  …
#
# NOTE: source is shipped as plain Python (no Cython compilation step).

ARG DETECTION_PROFILE=fast
ARG WITH_MODELS=true
ARG HF_HUB_OFFLINE=1

# ==========================================================================
# Stage 1: base — system libs + Python deps + application source
#   Shared by the prefetch and final stages so the heavy pip layer is built once.
# ==========================================================================
FROM python:3.11-slim AS base

# libgl1 + libglib2.0-0 → OpenCV (headless) runtime; curl → healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (created here so both stages can chown to it).
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Python deps first (requirements.txt pins torch/torchvision CPU wheels).
COPY client/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sibling `shared` package (imported by the licensing layer) + app source.
COPY shared ./shared
COPY client/. .

# src-layout: /app/src holds the floor_tiling package; /app holds `shared`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src:/app \
    MODELS_DIR=/app/models

# ==========================================================================
# Stage 2: prefetch — bake the profile's models when WITH_MODELS=true
#   prefetch_models.py reads the same env the server honours (DETECTION_PROFILE /
#   *_VARIANT / SEG_USE_* / OPEN_VOCAB_* / PAINT_REFINE_MATTING), so the baked set
#   matches exactly what runtime will load.
# ==========================================================================
FROM base AS prefetch
ARG WITH_MODELS
ARG DETECTION_PROFILE
# Optional per-model overrides — only exported below when non-empty so they don't
# clobber the profile with an empty string.
ARG MASK2FORMER_VARIANT=""
ARG ONEFORMER_VARIANT=""
ARG DEPTH_VARIANT=""
ARG YOLO_WORLD_VARIANT=""
ARG GROUNDING_DINO_VARIANT=""
ARG SAM_VARIANT=""
ARG VITMATTE_VARIANT=""

ENV DETECTION_PROFILE=${DETECTION_PROFILE}

RUN set -e; \
    if [ "$WITH_MODELS" = "true" ]; then \
        for v in MASK2FORMER_VARIANT ONEFORMER_VARIANT DEPTH_VARIANT \
                 YOLO_WORLD_VARIANT GROUNDING_DINO_VARIANT SAM_VARIANT \
                 VITMATTE_VARIANT; do \
            eval "val=\$$v"; \
            if [ -n "$val" ]; then export "$v=$val"; fi; \
        done; \
        echo "▶ baking models for profile=$DETECTION_PROFILE"; \
        python scripts/prefetch_models.py; \
    else \
        echo "▶ WITH_MODELS=false → no weights baked (provided at runtime)"; \
        mkdir -p models; \
    fi

# ==========================================================================
# Stage 3: final runtime
# ==========================================================================
FROM base AS final
ARG DETECTION_PROFILE
ARG HF_HUB_OFFLINE
# Same per-model ARGs as the prefetch stage, persisted as ENV below so RUNTIME
# resolves the exact variants that were baked (otherwise a baked override would
# mismatch the profile default and try — and, when offline, fail — to redownload).
ARG MASK2FORMER_VARIANT=""
ARG ONEFORMER_VARIANT=""
ARG DEPTH_VARIANT=""
ARG YOLO_WORLD_VARIANT=""
ARG GROUNDING_DINO_VARIANT=""
ARG SAM_VARIANT=""
ARG VITMATTE_VARIANT=""

# Runtime defaults — override ANY at `docker run -e` / compose `environment:`.
# Empty values are safe: settings._env() treats "" as "unset" and falls back to
# the profile. For the -nomodels image this is the dynamic-model dial: set
# DETECTION_PROFILE or any *_VARIANT at run time and the app downloads that set
# into the mounted volume on first use (needs HF_HUB_OFFLINE=0).
ENV DETECTION_PROFILE=${DETECTION_PROFILE} \
    HF_HUB_OFFLINE=${HF_HUB_OFFLINE} \
    MODELS_DIR=/app/models \
    MASK2FORMER_VARIANT=${MASK2FORMER_VARIANT} \
    ONEFORMER_VARIANT=${ONEFORMER_VARIANT} \
    DEPTH_VARIANT=${DEPTH_VARIANT} \
    YOLO_WORLD_VARIANT=${YOLO_WORLD_VARIANT} \
    GROUNDING_DINO_VARIANT=${GROUNDING_DINO_VARIANT} \
    SAM_VARIANT=${SAM_VARIANT} \
    VITMATTE_VARIANT=${VITMATTE_VARIANT}

# Bring in baked models (an empty dir when WITH_MODELS=false). chown so a named
# volume mounted here inherits appuser ownership and the app can write downloads.
COPY --from=prefetch --chown=appuser:appuser /app/models /app/models

# Allow appuser to write the generated config.js into the static directory at startup.
RUN chown appuser:appuser /app/src/floor_tiling/static

USER appuser

# Default port — overridden at runtime by HF Spaces (PORT=7860) or docker -e PORT=…
ENV PORT=8000
EXPOSE ${PORT}

# Models load (and warm up) at startup on CPU — allow a generous start period.
HEALTHCHECK --interval=30s --timeout=10s --start-period=420s --retries=3 \
    CMD curl -fs http://localhost:${PORT}/health || exit 1

# Production entrypoint — uvicorn, no reload.
# Shell form so ${PORT} is expanded from the environment at container start.
CMD uvicorn floor_tiling.app:app \
        --host 0.0.0.0 \
        --port ${PORT} \
        --workers 1 \
        --log-level info \
        --h11-max-incomplete-event-size 104857600
