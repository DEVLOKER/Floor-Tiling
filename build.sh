#!/usr/bin/env bash
# ── Floor Tiling — Docker build script ──────────────────────────────────────
set -euo pipefail

IMAGE_NAME="floor-tiling"
IMAGE_TAG="${1:-latest}"          # pass a tag as first arg, default: latest

echo "▶ Building ${IMAGE_NAME}:${IMAGE_TAG} ..."

docker build \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file Dockerfile \
  .

echo "✔ Build complete: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "Run with:"
echo "  docker run -p 8000:8000 ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  — or —"
echo "  docker compose up"
