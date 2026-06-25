import base64
import json
from datetime import date
from pathlib import Path
import platform
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

from floor_tiling.config import PUBLIC_KEY_PEM
# ``shared`` lives at the repo root; floor_tiling.__init__ puts it on sys.path.
from shared.config.settings import LICENSE_DIR, LICENSE_FILE
from shared.utils.storage_devices import list_devices
from shared.utils.fingerprint import generate_fingerprint

class LicenseError(RuntimeError):
    """Raised when license verification fails for any reason."""

def public_key_from_pem(pem: bytes) -> Ed25519PublicKey:
    if b"REPLACE_WITH" in pem:
        raise LicenseError(
            "No public key configured. "
            "Use the admin dashboard (Key Generation) and embed the "
            "public key into config/license.py before building the image."
        )
    return load_pem_public_key(pem)  # type: ignore[return-value]

def verify_signature(envelope: dict, public_key: Ed25519PublicKey) -> dict:
    try:
        payload_bytes = base64.urlsafe_b64decode(envelope["payload"])
        sig_bytes     = base64.urlsafe_b64decode(envelope["signature"])
    except (KeyError, Exception) as exc:
        raise LicenseError(f"Malformed license file: {exc}") from exc
    try:
        public_key.verify(sig_bytes, payload_bytes)
    except InvalidSignature:
        raise LicenseError("License signature is invalid — file may be tampered.")
    try:
        return json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise LicenseError(f"License payload is corrupt: {exc}") from exc

def check_expiry(payload: dict) -> None:
    expires_raw = payload.get("expires_at")
    if not expires_raw:
        return  # perpetual license
    try:
        expires = date.fromisoformat(str(expires_raw))
    except ValueError:
        raise LicenseError(f"License has invalid expires_at: {expires_raw!r}")
    if date.today() > expires:
        raise LicenseError(f"License expired on {expires_raw}.")

def check_fingerprint(payload: dict, parts: list) -> None:
    licensed_fp = payload.get("fingerprint", "")
    if not licensed_fp:
        raise LicenseError("License file is missing hardware fingerprint.")
    isValid = False
    try:
        actual_fp = generate_fingerprint(parts)
        if actual_fp == licensed_fp:
            isValid = True
    except RuntimeError as exc:
        raise LicenseError(f"Cannot collect machine fingerprint: {exc}") from exc
    if not isValid:
        raise LicenseError(
            "This license is locked to a different machine. "
            "Contact support to transfer your license."
        )

def verify_license() -> bool:
    """Verify the USB license.  Raises LicenseError on any failure.

    Call once at application startup (inside FastAPI lifespan).
    """
    """
    Search for the license file on all available devices and verify it.
    """

    # Skip license check if running inside Docker on non-Windows platforms, 
    # since we won't have access to USB devices there.
    # python3 -c "import platform; print(platform.system())"
    if _is_docker() and platform.system() != "Windows":
        return True # skip license check on non-Windows platforms for now

    devices = list_devices()
    found = False
    for device in devices:
        partitions = device.get("partitions", [])
        for part in partitions:
            mount = part.get("mount")
            if not mount:
                continue
            license_path = Path(mount) / LICENSE_DIR / LICENSE_FILE
            if license_path.exists():
                found = True
                try:
                    envelope = json.loads(license_path.read_text())
                    pubkey = public_key_from_pem(PUBLIC_KEY_PEM)
                    payload = verify_signature(envelope, pubkey)
                    check_expiry(payload)
                    parts = [device.get("serial", "")]
                    check_fingerprint(payload, parts)
                    return True
                except Exception as e:
                    raise LicenseError(f"License file found at {license_path}, but verification failed: {e}")
    if not found:
        raise LicenseError(f"No license file '{LICENSE_FILE}' found on any connected device.")


def _is_docker() -> bool:
    # Check 1: /.dockerenv file (present in almost all Docker containers)
    if os.path.exists("/.dockerenv"):
        return True
    # Check 2: 'docker' string in cgroup (works on older Docker/Linux kernels)
    try:
        with open("/proc/1/cgroup", "r") as f:
            if "docker" in f.read():
                return True
    except Exception:
        pass
    # Check 3: DOCKER environment variable (if you set it yourself in docker-compose/Dockerfile)
    if os.environ.get("DOCKER") or os.environ.get("DOCKER_CONTAINER"):
        return True
    return False