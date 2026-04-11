"""Hardware fingerprint service — wraps shared.fingerprint."""

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `shared` is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# from shared.fingerprint import collect, _cpu_id, _board_uuid, _mac_address, _usb_serial
from shared.utils.fingerprint import list_devices


def list_devices() -> list:
    return list_devices()
