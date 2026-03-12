"""Floor Tiling — Admin Panel

FastAPI web application for managing licenses:
  - Generate Ed25519 key pairs
  - Collect hardware fingerprints
  - Issue signed license files

Run:
    cd admin && python server.py
    # opens at https://localhost:9000
"""

import os
import sys
from pathlib import Path
from schemas.hardware import FingerprintRequest
from schemas.license import IssueRequest
from fastapi import Body
import shutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from services import (
    generate_keypair,
    get_public_key_pem,
    get_fingerprint,
    get_fingerprint_components,
    issue_license,
)
from services.keygen import has_private_key
from services.fingerprint import list_devices

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Floor Tiling Admin",
    description="License management dashboard",
    version="1.0.0",
)

# Ensure repo root is on sys.path
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Mount license directory for downloads
LICENSES_DIR = BASE_DIR / "license"
app.mount("/license", StaticFiles(directory=str(LICENSES_DIR)), name="license")

# Mount keys directory for downloads
KEYS_DIR = BASE_DIR / "keys"
app.mount("/keys", StaticFiles(directory=str(KEYS_DIR)), name="keys")

# ─────────────────────────────────────────────────────────────────────────────
# Hardware Info Endpoint (for UI)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/hardware/info")
async def hardware_info():
    """Return available hardware info for UI (no fingerprint)."""
    try:
        from services.fingerprint import list_devices
        from shared.fingerprint import _cpu_id, _board_uuid, _mac_address
        devices = list_devices()
        return {
            "devices": devices,
            "cpu_id": _cpu_id() or None,
            "board_uuid": _board_uuid() or None,
            "mac_address": _mac_address() or None,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Serve the admin dashboard."""
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/api/status")
async def status():
    """Return current status: whether keys exist, etc."""
    from services.keygen import get_private_key_pem
    pub = get_public_key_pem()
    priv = get_private_key_pem()
    return {
        "has_private_key": has_private_key(),
        "public_key_pem": pub,
        "private_key_pem": priv,
    }

@app.get("/api/storage-devices")
def storage_devices():
    """Return list of available USB devices and hard disks."""
    devices = list_devices()
    return devices

@app.post("/api/keygen")
async def keygen():
    """Generate a new Ed25519 key pair."""
    try:
        result = generate_keypair()
        return result
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/keygen/force")
async def keygen_force():
    """Regenerate key pair (overwrites existing)."""
    result = generate_keypair(force=True)
    return result



@app.post("/api/hardware/fingerprint")
async def hardware_fingerprint(req: FingerprintRequest):
    """Return only the fingerprint string for selected hardware, using provided serials."""
    try:
        parts = []
        if req.storage_serial:
            parts.append(req.storage_serial)
        if req.cpu_serial:
            parts.append(req.cpu_serial)
        if req.board_serial:
            parts.append(req.board_serial)
        if req.mac_serial:
            parts.append(req.mac_serial)
        if parts:
            import hashlib
            combined = "|".join(parts)
            fingerprint = hashlib.sha256(combined.encode()).hexdigest()
        else:
            fingerprint = None
        return fingerprint
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/issue")
async def issue(req: IssueRequest):
    """Issue a signed license file."""
    if not req.customer:
        raise HTTPException(status_code=400, detail="Customer name is required.")
    if not req.fingerprint:
        raise HTTPException(status_code=400, detail="Fingerprint is required.")

    # Use default license folder for output
    LICENSES_DIR = Path(__file__).resolve().parent / "license"
    LICENSES_DIR.mkdir(parents=True, exist_ok=True)
    # filename = f"{req.customer.replace(' ', '_')}_floor_tiling.lic"
    filename = "floor_tiling.lic"
    out_path = LICENSES_DIR / filename

    try:
        result = issue_license(
            customer=req.customer,
            fingerprint=req.fingerprint,
            expires=req.expires or None,
            out=str(out_path),
        )
        # Read license file content
        lic_content = Path(result["path"]).read_text()
        # Provide download URL for license file
        rel_path = Path(result["path"]).relative_to(Path(__file__).resolve().parent)
        download_url = f"/license/{rel_path.name}"
        return {"license_content": lic_content, "download_url": download_url, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/build-client")
async def build_client(partition: str = Body(..., embed=True)):
    """Build client app and copy license file to selected partition."""
    LICENSES_DIR = Path(__file__).resolve().parent / "license"
    license_file = LICENSES_DIR / "floor_tiling.lic"
    if not license_file.exists():
        raise HTTPException(status_code=404, detail="License file not found. Issue license first.")
    # Partition is expected to be a path (e.g., 'E:\' or '/mnt/usb')
    target_path = Path(partition) / "license/floor_tiling.lic"
    # Ensure the target directory exists
    target_dir = target_path.parent
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(license_file), str(target_path))
        return {"detail": f"License copied to {target_path}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to copy license: {exc}")



@app.get("/health")
async def health():
    return {"status": "healthy"}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # from shared.ssl_cert import ensure_ssl_cert

    # ssl_certfile, ssl_keyfile = ensure_ssl_cert()

    is_frozen = getattr(sys, "frozen", False)

    uvicorn.run(
        app if is_frozen else "server:app",
        host="0.0.0.0",
        port=9000,
        log_level="info",
        reload=not is_frozen,
        # ssl_certfile=ssl_certfile,
        # ssl_keyfile=ssl_keyfile,
    )

# or run from command line:
# python -m uvicorn server:app --host 0.0.0.0 --port 9000 --reload