"""Hardware fingerprint service — wraps shared.fingerprint."""

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `shared` is importable
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.fingerprint import (  # noqa: E402
    collect,
    _cpu_id,
    _board_uuid,
    _mac_address,
    _usb_serial,
)


def get_fingerprint_components(usb_path: str = "") -> dict:
    """Return individual hardware components as a dict.

    If usb_path is provided, sets LICENSE_USB_PATH so _usb_serial() can
    find the USB drive.
    """
    if usb_path:
        os.environ["LICENSE_USB_PATH"] = usb_path

    return {
        "cpu_id": _cpu_id() or None,
        "board_uuid": _board_uuid() or None,
        "mac_address": _mac_address() or None,
        "usb_serial": _usb_serial() or None,
    }


def get_fingerprint(usb_path: str = "") -> str:
    """Return the combined SHA-256 hex fingerprint for this machine."""
    if usb_path:
        os.environ["LICENSE_USB_PATH"] = usb_path
    return collect()


def list_devices() -> list:
    """Return one USB and one hard drive device (first of each type)."""
    import platform
    devices = []
    if platform.system() == "Windows":
        try:
            import subprocess
            ps_script = "Get-PhysicalDisk | Select-Object FriendlyName, SerialNumber, MediaType, Size | ConvertTo-Json"
            result = subprocess.run([
                "powershell", "-Command", ps_script
            ], capture_output=True, text=True)
            if result.returncode == 0:
                import json
                try:
                    ps_disks = json.loads(result.stdout)
                except Exception as e:
                    ps_disks = []
                if isinstance(ps_disks, dict):
                    ps_disks = [ps_disks]
                elif not isinstance(ps_disks, list):
                    ps_disks = []
                usb_device = None
                disk_device = None
                for pd in ps_disks:
                    fname = pd.get("FriendlyName", "")
                    serial = pd.get("SerialNumber", "")
                    media = pd.get("MediaType", "")
                    size = pd.get("Size", None)
                    size_str = None
                    if size is not None:
                        try:
                            size_gb = float(size) / (1024 ** 3)
                            size_str = f"{size_gb:.2f} GB"
                        except Exception:
                            size_str = str(size)
                    if not usb_device and (media == "Unspecified" or "USB" in fname.upper()):
                        usb_device = {
                            "type": "usb",
                            "id": fname,
                            "name": fname,
                            "serial": serial,
                            "manufacturer": "",
                            "size": size_str,
                        }
                    if not disk_device and (media in ["SSD", "HDD"] or "USB" not in fname.upper()):
                        disk_device = {
                            "type": "disk",
                            "id": fname,
                            "model": fname,
                            "serial": serial,
                            "manufacturer": "",
                            "size": size_str,
                        }
                    if usb_device and disk_device:
                        break
                if disk_device:
                    # Add partitions for disk_device
                    import psutil
                    partitions = []
                    for part in psutil.disk_partitions(all=False):
                        partitions.append({
                            "id": part.device,
                            "mount": part.mountpoint,
                            "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                            "fstype": part.fstype,
                            "opts": part.opts,
                        })
                    disk_device["partitions"] = partitions
                    devices.append(disk_device)
                if usb_device:
                    devices.append(usb_device)
                return devices
        except Exception:
            pass
        # USB: first found (non-Windows fallback)
        try:
            import usb.core
            import usb.util
            usb_devs = usb.core.find(find_all=True)
            for dev in usb_devs:
                size_str = None
                devices.append({
                    "type": "usb",
                    "id": hex(dev.address),
                    "vendor": hex(dev.idVendor),
                    "product": hex(dev.idProduct),
                    "serial": usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else "",
                    "manufacturer": usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "",
                    "name": usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "",
                    "size": size_str,
                })
                break
        except Exception:
            pass
        return devices
