"""Machine fingerprint collector — compiled to Cython extension.

Builds a stable, opaque fingerprint string from hardware identifiers:
  • CPU info (via /proc/cpuinfo on Linux or wmic on Windows)
  • Motherboard / system UUID (via dmidecode on Linux or wmic on Windows)
  • First active physical MAC address (via uuid / netifaces)
  • USB dongle serial number (via wmic on Windows, lsusb on Linux)

The fingerprint is the lowercase hex SHA-256 of the sorted concatenation of
whatever hardware IDs are available.  Partial collection is allowed — if one
source fails silently, the rest still contribute.

Used by license.py to bind a signed .lic file to a specific machine.
"""

import hashlib
import os
import platform
import subprocess
import uuid


def _run(cmd: list[str]) -> str:
    """Run a command, return stripped stdout, or '' on any error."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.stdout.decode(errors="ignore").strip()
    except Exception:
        return ""


def _cpu_id() -> str:
    system = platform.system()
    if system == "Linux":
        raw = _run(["cat", "/proc/cpuinfo"])
        for line in raw.splitlines():
            if line.lower().startswith("serial") or line.lower().startswith("hardware"):
                return line.split(":", 1)[-1].strip()
        # Fallback: model name
        for line in raw.splitlines():
            if "model name" in line.lower():
                return line.split(":", 1)[-1].strip()
    elif system == "Windows":
        # wmic is deprecated/removed in Windows 11 — use PowerShell instead
        raw = _run([
            "powershell", "-NoProfile", "-Command",
            "Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty ProcessorId"
        ])
        if raw:
            return raw.splitlines()[0].strip()
    elif system == "Darwin":
        raw = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        return raw
    return ""


def _board_uuid() -> str:
    system = platform.system()
    if system == "Linux":
        # Requires root; may be empty inside containers
        out = _run(["cat", "/sys/class/dmi/id/product_uuid"])
        if out:
            return out
        out = _run(["dmidecode", "-s", "system-uuid"])
        return out
    elif system == "Windows":
        # wmic is deprecated/removed in Windows 11 — use PowerShell instead
        raw = _run([
            "powershell", "-NoProfile", "-Command",
            "Get-WmiObject -Class Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID"
        ])
        if raw:
            return raw.splitlines()[0].strip()
    elif system == "Darwin":
        raw = _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        for line in raw.splitlines():
            if "IOPlatformUUID" in line:
                parts = line.split('"')
                if len(parts) >= 4:
                    return parts[-2]
    return ""


def _mac_address() -> str:
    """Return the MAC of the first non-loopback interface."""
    raw = hex(uuid.getnode())[2:].upper()
    # uuid.getnode() may return a random value if hardware MAC unavailable
    return raw


# def _usb_serial() -> str:
#     """Return the serial number of the plugged-in USB dongle.

#     Looks for the license USB by finding the volume/path set in
#     LICENSE_DIR and reading the volume serial via OS tools.

#     Windows : uses `vol <drive>:` to get the volume serial number.
#     Linux   : reads the USB device serial from /sys via the mount point.
#     macOS   : uses diskutil info on the mount point.

#     Returns '' if the USB is not present or serial cannot be determined.
#     """
#     usb_path = LICENSE_DIR
#     if not usb_path:
#         return ""

#     system = platform.system()

#     if system == "Windows":
#         # Extract drive letter from path like "E:\license" or "E:\"
#         drive = usb_path[:2] if len(usb_path) >= 2 and usb_path[1] == ":" else ""
#         if not drive:
#             return ""
#         raw = _run(["cmd", "/c", f"vol {drive}"])
#         # Output: "Volume in drive E is MY_USB\r\n Volume Serial Number is ABCD-EF01"
#         for line in raw.splitlines():
#             if "serial number" in line.lower():
#                 return line.split()[-1].strip()

#     elif system == "Linux":
#         # Find the block device for the mount point, then read its serial
#         raw = _run(["findmnt", "-n", "-o", "SOURCE", usb_path])
#         dev = raw.strip()  # e.g. /dev/sdb1
#         if not dev:
#             return ""
#         # Walk /sys/block to find the device serial
#         dev_name = os.path.basename(dev).rstrip("0123456789")  # sdb1 → sdb
#         serial_path = f"/sys/block/{dev_name}/../../serial"
#         try:
#             with open(serial_path) as f:
#                 return f.read().strip()
#         except OSError:
#             pass
#         # Fallback: udevadm
#         raw2 = _run(["udevadm", "info", "--query=property", f"--name={dev}"])
#         for line in raw2.splitlines():
#             if line.startswith("ID_SERIAL="):
#                 return line.split("=", 1)[1].strip()

#     elif system == "Darwin":
#         raw = _run(["diskutil", "info", usb_path])
#         for line in raw.splitlines():
#             if "Volume UUID" in line or "Disk / Partition UUID" in line:
#                 return line.split(":", 1)[-1].strip()

#     return ""


# def collect() -> str:
#     """Return a stable hex fingerprint for this machine.

#     The result is a lowercase 64-char SHA-256 hex string.
#     Calling this function multiple times on the same machine returns the
#     same value (unless hardware changes).
#     """
#     # Always require disk or USB serial
#     serial = _usb_serial()
#     if not serial:
#         # Try to get disk serial via environment or fallback
#         disk_serial = os.environ.get("LICENSE_DISK_SERIAL", "")
#         if disk_serial:
#             serial = disk_serial
#     if not serial:
#         raise RuntimeError("No disk or USB serial found. Hardware fingerprint requires a valid storage serial.")

#     # Optionally include CPU, board, MAC
#     optional = [
#         _cpu_id(),
#         _board_uuid(),
#         _mac_address(),
#     ]
#     meaningful = [serial] + [p for p in optional if p and p not in ("", "0", "None")]
#     combined = "|".join(meaningful)
#     return hashlib.sha256(combined.encode()).hexdigest()


def generate_fingerprint(parts: list) -> str:
    """Return a stable hex fingerprint for this machine."""

    meaningful = [p for p in parts if p and p not in ("", "0", "None")]
    if not meaningful:
        raise RuntimeError("No valid hardware identifiers found for fingerprint.")
    combined = "|".join(meaningful)
    return hashlib.sha256(combined.encode()).hexdigest()
