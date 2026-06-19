"""Cython build — compile proprietary modules to native extensions.

Compiles only the business-logic subpackages of ``floor_tiling`` (and the
shared fingerprint helpers), leaving the FastAPI entry points (``app.py``,
``__main__.py``) and the thin ``api`` routing layer as plain Python.

Because the package uses a ``src/`` layout, the build runs with the working
directory set to ``src/`` so ``--inplace`` drops each ``.pyd`` next to its source
(``src/floor_tiling/<pkg>/...``) with the correct dotted module name. The
``shared`` package lives at the repo root and is compiled in a second pass.

Usage (inside Docker / build_exe):
    python setup_cython.py build_ext --inplace
"""
import glob
import os
from pathlib import Path

from setuptools import setup
from Cython.Build import cythonize

HERE = Path(__file__).resolve().parent          # client/
SRC = HERE / "src"                              # client/src/
REPO_ROOT = HERE.parent                         # repo root (holds shared/)

# Proprietary floor_tiling subpackages to compile (relative to src/).
FLOOR_TILING_PKGS = [
    "floor_tiling/config",
    "floor_tiling/core",
    "floor_tiling/ml",
    "floor_tiling/patterns",
    "floor_tiling/processors",
    "floor_tiling/licensing",
]

# Shared modules (relative to the repo root) used by the licensing layer.
SHARED_MODULES = [
    "shared/utils/fingerprint.py",
    "shared/utils/keygen.py",
    "shared/utils/ssl_cert.py",
    "shared/utils/storage_devices.py",
    "shared/config/settings.py",
    "shared/config/__init__.py",
    "shared/utils/__init__.py",
]

DIRECTIVES = {"language_level": "3", "always_allow_keywords": True}


def _compile(cwd: Path, sources: list[str]) -> None:
    """Run an in-place Cython build of ``sources`` (paths relative to ``cwd``)."""
    sources = [s for s in sources if "__pycache__" not in s and os.path.exists(cwd / s)]
    if not sources:
        return
    print(f"[setup_cython] ({cwd}) compiling {len(sources)} file(s):")
    for s in sources:
        print(f"  {s}")
    prev = Path.cwd()
    os.chdir(cwd)
    try:
        setup(
            name="floor_tiling_native",
            script_args=["build_ext", "--inplace"],
            ext_modules=cythonize(sources, compiler_directives=DIRECTIVES, nthreads=4, quiet=False),
        )
    finally:
        os.chdir(prev)


if __name__ == "__main__":
    # Pass 1 — floor_tiling subpackages (module names like floor_tiling.core.planes).
    ft_sources = []
    for pkg in FLOOR_TILING_PKGS:
        ft_sources += [
            os.path.relpath(p, SRC)
            for p in glob.glob(str(SRC / pkg / "**" / "*.py"), recursive=True)
        ]
    _compile(SRC, ft_sources)

    # Pass 2 — shared package (module names like shared.utils.fingerprint).
    _compile(REPO_ROOT, SHARED_MODULES)
