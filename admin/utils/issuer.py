"""License issuance service — sign and write .lic files."""

import base64
import json
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key


def issue_license(
    customer: str,
    fingerprint: str,
    expires: str | None = None,
    out: str | Path = "",
    private_key: str | None = None,
    ) -> dict:
    """Sign and write a license file.

    Args:
        customer:    Customer name.
        fingerprint: Machine fingerprint hex (64 chars).
        expires:     Expiry date as YYYY-MM-DD string, or None for perpetual.
        out:         Output file path. Parent dirs created automatically.

    Returns:
        dict with license payload and output path.

    Raises:
        FileNotFoundError: Private key not generated yet.
        ValueError:        Invalid expires format.
    """
    # Validate expiry
    if expires:
        try:
            date.fromisoformat(expires)
        except ValueError:
            raise ValueError(f"Invalid expires format: {expires!r}. Use YYYY-MM-DD.")

    # Load private key only from param
    if private_key is None:
        raise FileNotFoundError("Private key must be provided as a parameter.")
    key_obj = load_pem_private_key(private_key.encode(), password=None)

    payload = {
        "version": 1,
        "customer": customer,
        "fingerprint": fingerprint,
        "expires_at": expires,
        "issued_at": date.today().isoformat(),
    }

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = key_obj.sign(payload_bytes)

    envelope = {
        "payload": base64.urlsafe_b64encode(payload_bytes).decode(),
        "signature": base64.urlsafe_b64encode(signature).decode(),
    }

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(envelope, indent=2))

    return {
        "path": str(out_path),
        "customer": customer,
        "fingerprint": fingerprint,
        "expires": expires or "never (perpetual)",
        "issued_at": payload["issued_at"],
    }
