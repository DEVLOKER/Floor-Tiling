"""Cython build script — compiles proprietary Python modules to C extensions.

Compile targets (your custom business logic only):
  config/          → settings, license, ssl_cert, __init__
  core/            → helpers, __init__
  ml_models/       → __init__
  patterns/        → __init__
  processors/      → __init__
  ../shared/       → fingerprint (shared between client and admin)

NOT compiled (intentionally excluded):
  server.py      → FastAPI entry-point; uvicorn imports it by name
  sam2/          → third-party library, not your IP

Usage inside Docker:
  python setup_cython.py build_ext --inplace
"""

import glob
import os
from setuptools import setup
from Cython.Build import cythonize

# ── Collect source files ──────────────────────────────────────────────────────
PACKAGES = ["config", "core", "ml_models", "patterns", "processors"]

# Shared package lives one level up
SHARED_DIR = os.path.join(os.path.dirname(__file__), "..", "shared")

sources = []
for pkg in PACKAGES:
    sources += glob.glob(os.path.join(pkg, "**", "*.py"), recursive=True)

# Include shared/ fingerprint module
sources += glob.glob(os.path.join(SHARED_DIR, "**", "*.py"), recursive=True)

# Exclude __pycache__ artefacts and empty stubs that only contain `pass`
sources = [
    s for s in sources
    if "__pycache__" not in s
]

print(f"[setup_cython] Compiling {len(sources)} file(s):")
for s in sources:
    print(f"  {s}")

# ── Build ─────────────────────────────────────────────────────────────────────
# NOTE: nthreads > 0 uses multiprocessing; on Windows this requires the
#       if __name__ == '__main__' guard to prevent infinite spawn loops.
if __name__ == "__main__":
    setup(
        name="floor_tiling_core",
        ext_modules=cythonize(
            sources,
            compiler_directives={
                "language_level": "3",      # Python 3 semantics
                "always_allow_keywords": True,  # keeps **kwargs working
            },
            nthreads=4,                     # parallel C compilation
            quiet=False,
        ),
    )
