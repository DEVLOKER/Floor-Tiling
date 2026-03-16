
# Ensure asyncio subprocess support on Windows (must be first)
import sys
if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
import shutil
import json
from pathlib import Path
from schemas.hardware import FingerprintRequest
from schemas.license import IssueRequest
from schemas.key import KeyRequest
from schemas.build import BuildClientRequest
from fastapi import Body
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import subprocess
from fastapi.staticfiles import StaticFiles
from typing import Optional
from utils import (
    generate_keypair,
    get_public_key_pem,
    get_private_key_pem,
    has_private_key,
    issue_license,
    list_devices
)
from shared.utils.fingerprint import _cpu_id, _board_uuid, _mac_address, generate_fingerprint
from shared.config.settings import LICENSE_DIR, LICENSE_FILE, KEYS_DIR, PUBLIC_KEY_FILE, PRIVATE_KEY_FILE

# Ensure asyncio subprocess support on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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

LOCAL_BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(LOCAL_BASE_DIR / "static")), name="static")

# Mount license directory for downloads
LOCAL_LICENSE_DIR = LOCAL_BASE_DIR / LICENSE_DIR
app.mount("/license", StaticFiles(directory=str(LOCAL_LICENSE_DIR)), name="license")

# Mount keys directory for downloads
LOCAL_KEYS_DIR = LOCAL_BASE_DIR / KEYS_DIR
app.mount("/keys", StaticFiles(directory=str(LOCAL_KEYS_DIR)), name="keys")

# ─────────────────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Serve the admin dashboard."""
    return FileResponse(str(LOCAL_BASE_DIR / "static" / "index.html"))

@app.get("/health")
async def health():
    return {"status": "healthy"}



# ─────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint for build output
# ─────────────────────────────────────────────────────────────────────────────


@app.websocket("/ws/build-output")
async def websocket_build_output(websocket: WebSocket):
    await websocket.accept()
    process = None
    try:
        # Wait for build parameters from client
        data = await websocket.receive_json()
        model = "tiny"  # or data.get("model", "tiny")
        bat_path = Path(__file__).parent.parent / "client" / "scripts" / "build_exe.bat"
        bat_path_str = str(bat_path.resolve())
        cmd = f'cmd /c "{bat_path_str}" {model}'
        await websocket.send_text(f"[DEBUG] Batch path: {bat_path_str}")
        await websocket.send_text(f"[DEBUG] Command: {cmd}")

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(bat_path.parent),
        )

        async def stream_output(stream, prefix=""):
            while True:
                line = await stream.readline()
                if not line:
                    break
                await websocket.send_text(prefix + line.decode(errors="replace"))

        # Stream both stdout and stderr concurrently
        await asyncio.gather(
            stream_output(process.stdout),
            stream_output(process.stderr, prefix="[STDERR] "),
        )

        await process.wait()
        await websocket.send_text("[BUILD END]")
    except WebSocketDisconnect:
        if process and process.returncode is None:
            process.terminate()
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        await websocket.send_text(f"[ERROR] {exc}\n{tb}")
    if not websocket.client_state.name == "DISCONNECTED":
        await websocket.close()

#############################################################################
# 1. Key Generation
#############################################################################

@app.get("/api/keys-status")
async def status():
    """Return current status: whether keys exist, etc."""
    return {
        "has_private_key": has_private_key(),
        "public_key_pem": get_public_key_pem(),
        "private_key_pem": get_private_key_pem(),
    }

@app.post("/api/keygen")
async def keygen(req: KeyRequest):
    """Generate or force a new Ed25519 key pair."""
    try:
        result = generate_keypair(force=req.force or False)
        # save result to disk is handled by generate_keypair, just return the info here
        KEYS_PATH = Path(__file__).resolve().parent / KEYS_DIR
        KEYS_PATH.mkdir(parents=True, exist_ok=True)
        pubkey_path = KEYS_PATH / PUBLIC_KEY_FILE
        private_key_path = KEYS_PATH / PRIVATE_KEY_FILE
        pubkey_path.write_text(result.public_key_pem)
        private_key_path.write_text(result.private_key_pem)
        return result
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


#############################################################################
# 2. Hardware Fingerprint
#############################################################################

@app.get("/api/storage-devices")
def storage_devices():
    """Return list of available USB devices and hard disks."""
    return {
        "devices": list_devices()
    }

@app.get("/api/hardware-info")
async def hardware_info():
    """Return available hardware info for UI (no fingerprint)."""
    try:
        return {
            "devices": list_devices() or [],
            "cpu_id": _cpu_id() or None,
            "board_uuid": _board_uuid() or None,
            "mac_address": _mac_address() or None,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))    


@app.post("/api/hardware-fingerprint")
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
            fingerprint = generate_fingerprint(parts)
        else:
            fingerprint = None
        return fingerprint
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

#############################################################################
# 3. Issue License
#############################################################################

@app.post("/api/license-issue")
async def issue(req: IssueRequest):
    """Issue a signed license file."""
    if not req.customer:
        raise HTTPException(status_code=400, detail="Customer name is required.")
    if not req.fingerprint:
        raise HTTPException(status_code=400, detail="Fingerprint is required.")
    if not hasattr(req, "private_key") or not req.private_key:
        raise HTTPException(status_code=400, detail="Private key is required.")

    LICENSES_PATH = Path(__file__).resolve().parent / LICENSE_DIR
    LICENSES_PATH.mkdir(parents=True, exist_ok=True)
    out_path = LICENSES_PATH / LICENSE_FILE

    try:
        result = issue_license(
            customer=req.customer,
            fingerprint=req.fingerprint,
            expires=req.expires or None,
            out=str(out_path),
            private_key=req.private_key,
        )
        lic_content = Path(result["path"]).read_text()
        rel_path = Path(result["path"]).relative_to(Path(__file__).resolve().parent)
        download_url = f"/license/{rel_path.name}"
        return {"license_content": lic_content, "download_url": download_url, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

#############################################################################
# 4. Build Client App
#############################################################################


@app.post("/api/build-client")
async def build_client(req: BuildClientRequest):
    """Build client app and copy license file to selected partition. Triggers build process, output streamed via WebSocket."""
    root_dir = Path(req.partition)
    try:
        license_path = root_dir / LICENSE_DIR / LICENSE_FILE
        license_path.parent.mkdir(parents=True, exist_ok=True)
        if not req.license_data:
            raise HTTPException(status_code=400, detail="License data is required.")
        license_path.write_text(req.license_data)

        # Update client/config/secrets.py with new PUBLIC_KEY_PEM and LICENSE_DATA
        secrets_path = Path(__file__).resolve().parent.parent / "client" / "config" / "secrets.py"
        pubkey_pem = req.public_key.strip()
        secrets_py = f"import os\nPUBLIC_KEY_PEM = b\"\"\"\\\n{pubkey_pem}\n\"\"\""
        secrets_path.write_text(secrets_py)

        # Instead of running the build here, return a message to connect to WebSocket for build output
        return {"detail": f"License copied to {license_path}. Connect to /ws/build-output for build log.", "build_ws": "/ws/build-output"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to copy license/public key: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # from shared.utils.ssl_cert import ensure_ssl_cert

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