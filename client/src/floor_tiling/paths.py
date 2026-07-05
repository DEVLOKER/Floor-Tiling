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


def model_dir(
    name: str,
    env_var: str,
    variant: str | None = None,
    expected_model_id: str | None = None,
) -> Path:
    """Resolve a single model's weight directory.

    Precedence: the model-specific env var (e.g. ``MASK2FORMER_DIR``) →
    ``MODELS_DIR/<name>``.

    When ``variant`` is given, each size variant is cached in its OWN
    subdirectory — ``MODELS_DIR/<name>/<variant>/``.  This means switching the
    DETECTION_PROFILE (or a single ``*_VARIANT``) never overwrites or re-downloads
    a variant you already have: the app just loads the matching subdir, and other
    variants stay on disk.  Because the path is fully local (git-ignored), all
    variants are reused across branches too.

    One-time migration: if the flat ``<name>/`` directory already holds this
    exact variant (its ``.model_id`` marker matches ``expected_model_id``), its
    files are MOVED into the ``<variant>/`` subdir so upgrading to this layout
    doesn't force a re-download of weights you already have.
    """
    base = Path(os.environ.get(env_var, str(MODELS_DIR / name)))
    if not variant:
        return base

    vdir = base / variant

    # Migrate a pre-existing flat model into its variant subdir (no re-download).
    if expected_model_id is not None and not vdir.exists():
        marker = base / ".model_id"
        try:
            if marker.exists() and marker.read_text().strip() == expected_model_id:
                vdir.mkdir(parents=True, exist_ok=True)
                for f in base.iterdir():
                    if f.is_file():
                        f.rename(vdir / f.name)
        except OSError:
            pass  # migration is best-effort; fall back to a fresh download

    return vdir
