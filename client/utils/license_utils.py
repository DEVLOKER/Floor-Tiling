import base64
import json
from datetime import date
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature
from shared.fingerprint import collect as collect_fingerprint

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

def find_license_file(usb_path_env, default_usb, license_file) -> Path:
    import os
    usb_root = Path(os.environ.get(usb_path_env, default_usb))
    lic_path = usb_root / license_file
    if not lic_path.exists():
        raise LicenseError(
            f"License file not found at {lic_path}. "
            "Make sure the USB drive is plugged in and mounted at "
            f"{usb_root} (override with {usb_path_env!r} env var). "
            "Docker: use  -v /path/to/usb:/license:ro"
        )
    return lic_path

def verify_signature(lic_path: Path, public_key: Ed25519PublicKey) -> dict:
    try:
        envelope = json.loads(lic_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise LicenseError(f"Cannot read license file: {exc}") from exc
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

def check_fingerprint(payload: dict) -> None:
    licensed_fp = payload.get("fingerprint", "")
    if not licensed_fp:
        raise LicenseError("License file is missing hardware fingerprint.")
    try:
        actual_fp = collect_fingerprint()
    except RuntimeError as exc:
        raise LicenseError(f"Cannot collect machine fingerprint: {exc}") from exc
    if actual_fp != licensed_fp:
        raise LicenseError(
            "This license is locked to a different machine. "
            "Contact support to transfer your license."
        )

def verify_license(lic_file: Path, pubkey: Ed25519PublicKey) -> None:
    """Verify the USB license.  Raises LicenseError on any failure.

    Call once at application startup (inside FastAPI lifespan).
    """

    lic_path = find_license_file(lic_file)
    pubkey = public_key_from_pem(PUBLIC_KEY_PEM)
    payload = verify_signature(lic_path, pubkey)
    check_expiry(payload)
    check_fingerprint(payload)

    print(
        "License verified — customer: %s  expires: %s",
        payload.get("customer", "—"),
        payload.get("expires_at") or "never",
    )
