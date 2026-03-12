def get_private_key_pem() -> str | None:
    """Return the private key PEM string, or None if not generated yet."""
    if PRIVATE_KEY_PATH.exists():
        return PRIVATE_KEY_PATH.read_text()
    return None
"""Ed25519 key pair generation service."""

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
)

# Keys are stored in admin/keys/
KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "public_key.pem"


def generate_keypair(force: bool = False) -> dict:
    """Generate a new Ed25519 key pair and save to disk.

    Returns dict with paths and the public key PEM string.
    Raises FileExistsError if keys already exist (unless force=True).
    """
    if PRIVATE_KEY_PATH.exists() and not force:
        raise FileExistsError(
            f"Private key already exists at {PRIVATE_KEY_PATH}. "
            "Delete it manually or pass force=True to regenerate."
        )

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    pem_private = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pem_public = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )

    PRIVATE_KEY_PATH.write_bytes(pem_private)
    try:
        PRIVATE_KEY_PATH.chmod(0o600)
    except OSError:
        pass  # chmod not supported on Windows

    PUBLIC_KEY_PATH.write_bytes(pem_public)
    try:
        PUBLIC_KEY_PATH.chmod(0o644)
    except OSError:
        pass

    return {
        "private_key_path": str(PRIVATE_KEY_PATH),
        "public_key_path": str(PUBLIC_KEY_PATH),
        "public_key_pem": pem_public.decode(),
        "private_key_pem": pem_private.decode(),
    }


def get_public_key_pem() -> str | None:
    """Return the public key PEM string, or None if not generated yet."""
    if PUBLIC_KEY_PATH.exists():
        return PUBLIC_KEY_PATH.read_text()
    return None


def has_private_key() -> bool:
    """Check if the private key exists on disk."""
    return PRIVATE_KEY_PATH.exists()
