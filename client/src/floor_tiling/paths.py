"""Filesystem paths used across the app.

Centralises the project root and the ML model-weights cache directory so no
module has to compute paths relative to its own ``__file__``.
"""
import os
from pathlib import Path

# src/floor_tiling/paths.py → parents: [floor_tiling, src, <project root>]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Repository root (one level above this project) — holds the sibling ``shared``
# package that the licensing layer imports.
REPO_ROOT = PROJECT_ROOT.parent

# Where model weights are downloaded/cached. Override with the MODELS_DIR env
# var (e.g. a mounted volume); each model also honours its own *_DIR override.
MODELS_DIR = Path(os.environ.get("MODELS_DIR", PROJECT_ROOT / "models"))

# Bundled frontend assets (served by the FastAPI app).
STATIC_DIR = Path(__file__).resolve().parent / "static"


def model_dir(name: str, env_var: str) -> Path:
    """Resolve a single model's weight directory.

    Precedence: the model-specific env var (e.g. ``MASK2FORMER_DIR``) →
    ``MODELS_DIR/<name>``.
    """
    return Path(os.environ.get(env_var, str(MODELS_DIR / name)))
