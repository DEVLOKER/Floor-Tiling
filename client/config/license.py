"""License verification — compiled to Cython extension.

Protection model
────────────────
1. Customer plugs in USB drive.
2. USB is bind-mounted into the container at LICENSE_USB_PATH
   (default: /license).
3. App reads  <usb>/floor_tiling.lic   — a JSON file signed with your
   Ed25519 private key (never distributed; stays on your machine).
4. Signature is verified against your Ed25519 PUBLIC key, which is
   BAKED INTO THIS MODULE at build time (not a runtime file).
5. The fingerprint field inside the .lic is compared against this
   machine's hardware fingerprint.  Mismatch → abort.

.lic file format (JSON)
───────────────────────
{
  "customer":    "Acme Corp",
  "fingerprint": "<sha256 hex from config.fingerprint.collect()>",
  "expires_at":  "2027-06-01",   ← ISO date, or null for perpetual
  "issued_at":   "2026-03-09",
  "version":     1
}
The file on disk is:
{
  "payload": "<base64url of the JSON above>",
  "signature": "<base64url of Ed25519 signature over the payload bytes>"
}

Issue new licenses with the admin dashboard:  https://localhost:9000
"""

import base64
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

from shared.fingerprint import collect as collect_fingerprint

logger = logging.getLogger(__name__)

# ── Ed25519 public key (baked in at build time) ──────────────────────────────
# To rotate: use the admin dashboard (Key Generation), paste new PEM here.
# The private key NEVER goes into this file, this repo, or the build.
_PUBLIC_KEY_PEM = b"""\
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAOKHXJyBFNnuMSX41K/1/27j61soby9g+A2MpzrRYf/U=
-----END PUBLIC KEY-----
"""

# ── Config ────────────────────────────────────────────────────────────────────
_USB_PATH_ENV   = "LICENSE_USB_PATH"
_DEFAULT_USB    = "/license"
_LICENSE_FILE   = "floor_tiling.lic"


# ── Public exception ──────────────────────────────────────────────────────────
class LicenseError(RuntimeError):
    """Raised when license verification fails for any reason."""


# ── Internal helpers ──────────────────────────────────────────────────────────
def _public_key() -> Ed25519PublicKey:
    if b"REPLACE_WITH" in _PUBLIC_KEY_PEM:
        raise LicenseError(
            "No public key configured. "
            "Use the admin dashboard (Key Generation) and embed the "
            "public key into config/license.py before building the image."
        )
    return load_pem_public_key(_PUBLIC_KEY_PEM)  # type: ignore[return-value]


def _find_license_file() -> Path:
    usb_root = Path(os.environ.get(_USB_PATH_ENV, _DEFAULT_USB))
    lic_path = usb_root / _LICENSE_FILE
    if not lic_path.exists():
        raise LicenseError(
            f"License file not found at {lic_path}. "
            "Make sure the USB drive is plugged in and mounted at "
            f"{usb_root} (override with {_USB_PATH_ENV!r} env var). "
            "Docker: use  -v /path/to/usb:/license:ro"
        )
    return lic_path


def _verify_signature(lic_path: Path) -> dict:
    """Parse, verify signature, return decoded payload dict."""
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
        _public_key().verify(sig_bytes, payload_bytes)
    except InvalidSignature:
        raise LicenseError("License signature is invalid — file may be tampered.")

    try:
        return json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise LicenseError(f"License payload is corrupt: {exc}") from exc


def _check_expiry(payload: dict) -> None:
    expires_raw = payload.get("expires_at")
    if not expires_raw:
        return  # perpetual license
    try:
        expires = date.fromisoformat(str(expires_raw))
    except ValueError:
        raise LicenseError(f"License has invalid expires_at: {expires_raw!r}")
    if date.today() > expires:
        raise LicenseError(f"License expired on {expires_raw}.")


def _check_fingerprint(payload: dict) -> None:
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


# ── Public API ────────────────────────────────────────────────────────────────
def verify_license() -> None:
    """Verify the USB license.  Raises LicenseError on any failure.

    Call once at application startup (inside FastAPI lifespan).
    """
    lic_path = _find_license_file()
    payload  = _verify_signature(lic_path)
    _check_expiry(payload)
    _check_fingerprint(payload)

    logger.info(
        "License verified — customer: %s  expires: %s",
        payload.get("customer", "—"),
        payload.get("expires_at") or "never",
    )
