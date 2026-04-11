# -*- mode: python ; coding: utf-8 -*-
# ── Floor Tiling Admin — PyInstaller spec ────────────────────────────────────
#
# This file MUST stay in admin/ — PyInstaller sets SPECPATH to its location
# and all paths below are resolved relative to it.
#
# Normal build (from anywhere):
#   .\admin\scripts\build_exe.ps1     # Windows PowerShell
#
# Manual build (from admin/):
#   pyinstaller admin_panel.spec
# ─────────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)         # = admin/
REPO_ROOT = ROOT.parent       # = Floor Tiling/

# ── Collect full setuptools / pkg_resources ───────────────────────────────────
_st_datas, _st_binaries, _st_hidden = collect_all("setuptools")
_ad_datas, _ad_binaries, _ad_hidden = collect_all("appdirs")

datas = [
    # Shared package (fingerprint.py, ssl_cert.py)
    (str(REPO_ROOT / "shared"), "shared"),
    # Services package
    (str(ROOT / "utils"), "utils"),
]

hidden = [
    # Cryptography (for key generation + license signing)
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "cryptography.hazmat.primitives.asymmetric.rsa",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.backends.openssl",
    "cryptography.x509",
    # pkg_resources / setuptools runtime deps
    "pkg_resources",
    "pkg_resources.extern",
    "appdirs",
]

# ─────────────────────────────────────────────────────────────────────────────

# ── Analysis for Tkinter Admin App ───────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[str(ROOT), str(REPO_ROOT)],
    binaries=_st_binaries + _ad_binaries,
    datas=datas + _st_datas + _ad_datas,
    hiddenimports=hidden + _st_hidden + _ad_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "hooks" / "rthook_appdirs.py")],
    excludes=[
        # Remove web/GUI exclusions, keep only unnecessary packages
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "torch",
        "torchvision",
        "cv2",
        "PIL",
        "numpy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir mode
    name="admin-panel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # windowed mode for Tkinter app
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
    name="admin-panel",      # dist/admin-panel/
)
