"""Cython build script — compiles proprietary Python modules to C extensions.

Compile targets (your custom business logic only):
  config/          → settings, license, ssl_cert, __init__
  core/            → geometry, planes, masks, __init__
  depth/           → depth-model wrapper, __init__
  mask2former/     → __init__
  patterns/        → __init__
  processors/      → __init__
  ../shared/       → fingerprint (shared between client and admin)

NOT compiled (intentionally excluded):
  server.py      → FastAPI entry-point; uvicorn imports it by name
  app.py         → FastAPI app factory; imported by name (server:app)

Usage inside Docker:
  python setup_cython.py build_ext --inplace
"""

import glob
import os
from setuptools import setup
from Cython.Build import cythonize

# ── Collect source files ──────────────────────────────────────────────────────
# Only cythonize proprietary/sensitive modules, not third-party or open-source
PACKAGES = [
    "config",    # your app config, secrets, license logic
    "core",      # core business logic (geometry, planes, mask refinement)
    "depth",     # depth model wrapper (for wall-plane separation)
    "mask2former", # your ML model wrappers AND models
    "patterns",  # your proprietary pattern logic
    "processors", # your proprietary processors
    "utils"      # your proprietary utilities
]

# Shared package lives one level up
SHARED_DIR = os.path.join(os.path.dirname(__file__), "..", "shared")

sources = []
for pkg in PACKAGES:
    sources += glob.glob(os.path.join(pkg, "**", "*.py"), recursive=True)

# Only include your own shared modules (not third-party)
# Example: only fingerprint, keygen, ssl_cert, storage_devices
shared_modules = [
    os.path.join(SHARED_DIR, "utils", "fingerprint.py"),
    os.path.join(SHARED_DIR, "utils", "keygen.py"),
    os.path.join(SHARED_DIR, "utils", "ssl_cert.py"),
    os.path.join(SHARED_DIR, "utils", "storage_devices.py"),
    os.path.join(SHARED_DIR, "config", "settings.py"),
    os.path.join(SHARED_DIR, "config", "__init__.py"),
    os.path.join(SHARED_DIR, "utils", "__init__.py"),
]
sources += [s for s in shared_modules if os.path.exists(s)]

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
    # Dynamically collect all unique output directories from sources (client and shared)
    output_dirs = set()
    for s in sources:
        dir_path = os.path.dirname(s)
        if os.path.isabs(dir_path):
            output_dirs.add(dir_path)
            # Also create relative to current working directory if different
            rel_to_cwd = os.path.relpath(dir_path, os.getcwd())
            if not rel_to_cwd.startswith("..") and rel_to_cwd != ".":
                output_dirs.add(os.path.join(os.getcwd(), rel_to_cwd))
    for d in output_dirs:
        os.makedirs(d, exist_ok=True)
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
