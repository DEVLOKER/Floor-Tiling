"""Self-signed SSL certificate helper.

Generates a self-signed cert + key on first run and reuses them
on subsequent starts.  Files are stored next to the executable
(prod) or in the client/ directory (dev).

The certificate is valid for 10 years with SAN=localhost + 127.0.0.1
so browsers/tools can connect over HTTPS without extra configuration
beyond accepting the self-signed warning once.
"""

import datetime
import ipaddress
import os
import sys

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared.config import SSL_DIR, SSL_CERT_FILE, SSL_KEY_FILE

# Where to store the cert files
def _cert_dir() -> str:
    """Return the directory to store cert/key files (inside an ssl/ subfolder)."""
    if getattr(sys, "frozen", False):
        # PyInstaller exe — store next to the exe
        base = os.path.dirname(sys.executable)
    else:
        # Dev — store relative to this file (shared/)
        base = os.path.dirname(os.path.abspath(__file__))
    ssl_dir = os.path.join(base, SSL_DIR)
    os.makedirs(ssl_dir, exist_ok=True)
    return ssl_dir


def ensure_ssl_cert() -> tuple[str, str]:
    """Return (certfile, keyfile) paths, generating them if missing."""
    cert_dir = _cert_dir()
    cert_path = os.path.join(cert_dir, SSL_CERT_FILE)
    key_path = os.path.join(cert_dir, SSL_KEY_FILE)

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    print(f"Generating self-signed SSL certificate in {cert_dir} ...")

    # Generate RSA private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Build certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Floor Tiling localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Floor Tiling"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 20))  # 20 years
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write key
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Write cert
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"SSL cert: {cert_path}")
    print(f"SSL key:  {key_path}")
    return cert_path, key_path
