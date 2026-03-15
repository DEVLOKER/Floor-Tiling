# -*- mode: python ; coding: utf-8 -*-
# ── Floor Tiling — PyInstaller spec ──────────────────────────────────────────
#
# This file MUST stay in client/ — PyInstaller sets SPECPATH to its location
# and all paths below are resolved relative to it.
#
# Normal build (from anywhere):
#   .\client\scripts\build_exe.ps1     # Windows PowerShell
#
# Manual build (from client/):
#   pyinstaller floor_tiling.spec
# ─────────────────────────────────────────────────────────────────────────────

import glob
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH)  # = client/
REPO_ROOT = ROOT.parent  # = Floor Tiling/

# ── Collect full setuptools / pkg_resources (needed by pyi_rth_pkgres hook) ──
_st_datas, _st_binaries, _st_hidden = collect_all("setuptools")
_ad_datas, _ad_binaries, _ad_hidden = collect_all("appdirs")

# ── Cython-compiled .pyd binaries ─────────────────────────────────────────────
# Collect all .pyd files in the sensitive packages.  Each entry is a tuple:
#   (source_path, dest_directory_inside_the_bundle)
pyd_binaries = []
for pkg in ["config", "core", "ml_models", "patterns", "processors"]:
    for pyd in glob.glob(str(ROOT / pkg / "*.pyd")):
        pyd_binaries.append((pyd, pkg))
# Shared package (lives at repo root)
for pyd in glob.glob(str(REPO_ROOT / "shared" / "*.pyd")):
    pyd_binaries.append((pyd, "shared"))

# ── Data files ────────────────────────────────────────────────────────────────
# Only include .py sources from shared/ if no .pyd exists for that module
def shared_datas():
    shared_dir = REPO_ROOT / "shared"
    datas = []
    # Add all non-.py files (e.g., data, certs, etc.)
    for root, dirs, files in os.walk(shared_dir):
        for f in files:
            if not f.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, f), shared_dir)
                datas.append((str(shared_dir / rel), str(Path("shared") / Path(rel).parent)))
    # Only add .py if no .pyd exists for that module
    for root, dirs, files in os.walk(shared_dir):
        for f in files:
            if f.endswith(".py"):
                pyd_name = f[:-3] + ".pyd"
                if not os.path.exists(os.path.join(root, pyd_name)):
                    rel = os.path.relpath(os.path.join(root, f), shared_dir)
                    datas.append((str(shared_dir / rel), str(Path("shared") / Path(rel).parent)))
    return datas

# Exclude dev files/folders from datas
def filter_dev_files(datas):
    exclude_patterns = [
        "Dockerfile", ".git", "scripts", "build_exe.ps1", "build_docker.ps1", "install_deps.ps1", "run_docker.ps1"
    ]
    filtered = []
    for src, dest in datas:
        if not any(pat in src or pat in dest for pat in exclude_patterns):
            filtered.append((src, dest))
    return filtered

datas = [
    (str(ROOT / "static"),       "static"),
    (str(ROOT / "sam2" / "configs"), os.path.join("sam2", "configs")),
] + shared_datas()
datas = filter_dev_files(datas)
#    # SAM2 model checkpoints (large — uncomment if you want to bundle them)
#    # (str(ROOT / "sam2" / "models"), os.path.join("sam2", "models")),

# ── Hidden imports ────────────────────────────────────────────────────────────
# PyInstaller's static analysis misses these because they are loaded
# dynamically (uvicorn plugin system, torch C extensions, etc.)
hidden = [
    # uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # FastAPI / Starlette internals
    "starlette.routing",
    "starlette.middleware",
    "starlette.staticfiles",
    "anyio",
    "anyio.abc",
    "anyio._backends._asyncio",
    # Cryptography (for license.pyd)
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.backends.openssl",
    # Image / ML
    "PIL._imaging",
    "cv2",
    "torch",
    "torchvision",
    # pkg_resources / setuptools runtime deps (appdirs is required internally)
    "pkg_resources",
    "pkg_resources.extern",
    "appdirs",
    "jaraco.text",
    "jaraco.context",
    "jaraco.functools",
    "more_itertools",
]

# ─────────────────────────────────────────────────────────────────────────────
a = Analysis(
    ["server.py"],
    pathex=[str(ROOT), str(REPO_ROOT)],
    binaries=pyd_binaries + _st_binaries + _ad_binaries,
    datas=datas + _st_datas + _ad_datas,
    hiddenimports=hidden + _st_hidden + _ad_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "hooks" / "rthook_appdirs.py")],
    excludes=[
        # Remove these to keep the bundle smaller
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    noarchive=False,
    optimize=0,  # optimize=2 strips docstrings and breaks numpy/torch at runtime
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir mode — binaries go into the folder
    name="floor-tiling",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                # compress with UPX if available
    console=True,            # keep console so license errors are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="floor-tiling",     # dist/floor-tiling/
)
