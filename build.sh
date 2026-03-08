#!/usr/bin/env bash
# ── Floor Tiling — Docker build script ──────────────────────────────────────
# Usage:
#   ./build.sh [TAG] [MODEL_SOURCE]
#
#   TAG          Image tag (default: latest)
#   MODEL_SOURCE download → fetch SAM2 model from Meta CDN (default)
#                local    → copy from ./sam2/models/ in build context
#                           ⚠  remove 'sam2/models/*.pt' from .dockerignore first
#
# Examples:
#   ./build.sh                     → floor-tiling:latest  (download mode)
#   ./build.sh 1.0.0               → floor-tiling:1.0.0   (download mode)
#   ./build.sh latest local        → floor-tiling:latest  (local mode)
set -euo pipefail

IMAGE_NAME="floor-tiling"
IMAGE_TAG="${1:-latest}"
MODEL_SOURCE="${2:-download}"

if [ "$MODEL_SOURCE" != "download" ] && [ "$MODEL_SOURCE" != "local" ]; then
    echo "✖ Invalid MODEL_SOURCE '${MODEL_SOURCE}'. Use 'download' or 'local'."
    exit 1
fi

if [ "$MODEL_SOURCE" = "local" ]; then
    echo "⚠  Local model mode — make sure 'sam2/models/*.pt' is NOT excluded in .dockerignore"
fi

echo "▶ Building ${IMAGE_NAME}:${IMAGE_TAG} (MODEL_SOURCE=${MODEL_SOURCE}) ..."

docker build \
  --build-arg MODEL_SOURCE="${MODEL_SOURCE}" \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file Dockerfile \
  .

echo "✔ Build complete: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "Run with:"
echo "  docker run -p 8000:8000 ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  — or —"
echo "  docker compose up"
