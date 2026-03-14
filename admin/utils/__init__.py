"""Admin utils — business logic for licensing operations."""

# from .keygen import generate_keypair, get_public_key_pem, get_private_key_pem, has_private_key
# from .issuer import issue_license

import sys
from pathlib import Path

from .issuer import *

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.utils.storage_devices import *
from shared.utils.keygen import *
from shared.utils.fingerprint import *
from shared.utils.ssl_cert import *
from shared.config.settings import *

# from shared.utils.storage_devices import list_devices

# __all__ = [
#     "generate_keypair",
#     "get_public_key_pem",
#     "get_private_key_pem",
#     "has_private_key",
#     "issue_license",
#     "list_devices"
# ]
