# def list_devices() -> list:
#     import platform
#     import os
#     devices = []
#     if platform.system() == "Windows":
#         try:
#             import subprocess
#             ps_script = "Get-PhysicalDisk | Select-Object FriendlyName, SerialNumber, MediaType, Size | ConvertTo-Json"
#             result = subprocess.run([
#                 "powershell", "-Command", ps_script
#             ], capture_output=True, text=True)
#             if result.returncode == 0:
#                 import json
#                 try:
#                     ps_disks = json.loads(result.stdout)
#                 except Exception as e:
#                     ps_disks = []
#                 if isinstance(ps_disks, dict):
#                     ps_disks = [ps_disks]
#                 elif not isinstance(ps_disks, list):
#                     ps_disks = []
#                 usb_device = None
#                 disk_device = None
#                 for pd in ps_disks:
#                     fname = pd.get("FriendlyName", "")
#                     serial = pd.get("SerialNumber", "")
#                     media = pd.get("MediaType", "")
#                     size = pd.get("Size", None)
#                     size_str = None
#                     if size is not None:
#                         try:
#                             size_gb = float(size) / (1024 ** 3)
#                             size_str = f"{size_gb:.2f} GB"
#                         except Exception:
#                             size_str = str(size)
#                     if not usb_device and (media == "Unspecified" or "USB" in fname.upper()):
#                         usb_device = {
#                             "type": "usb",
#                             "id": fname,
#                             "name": fname,
#                             "serial": serial,
#                             "manufacturer": "",
#                             "size": size_str,
#                         }
#                     if not disk_device and (media in ["SSD", "HDD"] or "USB" not in fname.upper()):
#                         disk_device = {
#                             "type": "disk",
#                             "id": fname,
#                             "model": fname,
#                             "serial": serial,
#                             "manufacturer": "",
#                             "size": size_str,
#                         }
#                     if usb_device and disk_device:
#                         break
#                 # Robust mapping: always return devices, fallback if WMI fails
#                 import psutil
#                 partitions = psutil.disk_partitions(all=False)
#                 disk_parts = []
#                 usb_parts = []
#                 try:
#                     import wmi
#                     c = wmi.WMI()
#                     drive_to_serial = {}
#                     for disk in c.Win32_DiskDrive():
#                         serial = getattr(disk, "SerialNumber", None)
#                         model = getattr(disk, "Model", None)
#                         for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
#                             for logical in partition.associators("Win32_LogicalDiskToPartition"):
#                                 drive_letter = logical.DeviceID
#                                 if serial:
#                                     drive_to_serial[drive_letter] = serial.strip()
#                                 elif model:
#                                     drive_to_serial[drive_letter] = model.strip()
#                     # Assign partitions
#                     mapped = False
#                     for part in partitions:
#                         drive_letter = part.device.split(":")[0] + ":\\"
#                         serial = drive_to_serial.get(drive_letter)
#                         if serial and disk_device and serial == disk_device["serial"]:
#                             disk_parts.append({
#                                 "id": part.device,
#                                 "mount": part.mountpoint,
#                                 "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                 "fstype": part.fstype,
#                                 "opts": part.opts,
#                             })
#                             mapped = True
#                         elif serial and usb_device and serial == usb_device["serial"]:
#                             usb_parts.append({
#                                 "id": part.device,
#                                 "mount": part.mountpoint,
#                                 "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                 "fstype": part.fstype,
#                                 "opts": part.opts,
#                             })
#                             mapped = True
#                     # If mapping failed, fallback
#                     if not mapped:
#                         for part in partitions:
#                             if "removable" in part.opts and usb_device:
#                                 usb_parts.append({
#                                     "id": part.device,
#                                     "mount": part.mountpoint,
#                                     "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                     "fstype": part.fstype,
#                                     "opts": part.opts,
#                                 })
#                             elif "fixed" in part.opts and disk_device:
#                                 disk_parts.append({
#                                     "id": part.device,
#                                     "mount": part.mountpoint,
#                                     "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                     "fstype": part.fstype,
#                                     "opts": part.opts,
#                                 })
#                 except Exception:
#                     # Fallback: group by opts
#                     for part in partitions:
#                         if "removable" in part.opts and usb_device:
#                             usb_parts.append({
#                                 "id": part.device,
#                                 "mount": part.mountpoint,
#                                 "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                 "fstype": part.fstype,
#                                 "opts": part.opts,
#                             })
#                         elif "fixed" in part.opts and disk_device:
#                             disk_parts.append({
#                                 "id": part.device,
#                                 "mount": part.mountpoint,
#                                 "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
#                                 "fstype": part.fstype,
#                                 "opts": part.opts,
#                             })
#                 # Attach partitions
#                 if disk_device:
#                     disk_device["partitions"] = disk_parts
#                 if usb_device:
#                     usb_device["partitions"] = usb_parts
#                 result_devices = []
#                 if disk_device:
#                     result_devices.append(disk_device)
#                 if usb_device:
#                     result_devices.append(usb_device)
#                 return result_devices
#         except Exception:
#             pass
#         # USB: first found (non-Windows fallback)
#         try:
#             import usb.core
#             import usb.util
#             usb_devs = usb.core.find(find_all=True)
#             for dev in usb_devs:
#                 size_str = None
#                 devices.append({
#                     "type": "usb",
#                     "id": hex(dev.address),
#                     "vendor": hex(dev.idVendor),
#                     "product": hex(dev.idProduct),
#                     "serial": usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else "",
#                     "manufacturer": usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "",
#                     "name": usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "",
#                     "size": size_str,
#                 })
#                 break
#         except Exception:
#             pass
#         return devices



"""
list_devices.py
Cross-platform device listing (Windows, Linux, macOS).
Returns a list of devices with metadata and partitions.  
Uses best-effort approach with multiple fallbacks to maximize compatibility and robustness.
"""

import platform
import os


def list_devices() -> list:
    system = platform.system()
    if system == "Windows":
        return _list_devices_windows()
    elif system == "Linux":
        return _list_devices_linux()
    elif system == "Darwin":
        return _list_devices_macos()
    else:
        return []


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _bytes_to_gb_str(size_bytes) -> str | None:
    try:
        return f"{float(size_bytes) / (1024 ** 3):.2f} GB"
    except Exception:
        return None


def _partition_entry(part) -> dict:
    return {
        "id": part.device,
        "mount": part.mountpoint,
        "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
        "fstype": part.fstype,
        "opts": part.opts,
    }


# ──────────────────────────────────────────────
# Windows
# ──────────────────────────────────────────────

def _list_devices_windows() -> list:
    import json
    import subprocess
    import psutil

    devices = []
    usb_device = None
    disk_device = None

    # --- PowerShell: get physical disk metadata ---
    try:
        ps_script = (
            "Get-PhysicalDisk | "
            "Select-Object FriendlyName, SerialNumber, MediaType, Size | "
            "ConvertTo-Json"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            try:
                ps_disks = json.loads(result.stdout)
            except Exception:
                ps_disks = []
            if isinstance(ps_disks, dict):
                ps_disks = [ps_disks]
            elif not isinstance(ps_disks, list):
                ps_disks = []

            for pd in ps_disks:
                fname = pd.get("FriendlyName", "")
                serial = pd.get("SerialNumber", "")
                media = pd.get("MediaType", "")
                size_str = _bytes_to_gb_str(pd.get("Size"))

                if not usb_device and (media == "Unspecified" or "USB" in fname.upper()):
                    usb_device = {
                        "type": "usb",
                        "id": fname,
                        "name": fname,
                        "serial": serial,
                        "manufacturer": "",
                        "size": size_str,
                    }
                if not disk_device and (media in ("SSD", "HDD") or "USB" not in fname.upper()):
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
    except Exception:
        pass

    # --- Map partitions via WMI, fall back to psutil opts ---
    disk_parts, usb_parts = [], []
    partitions = psutil.disk_partitions(all=False)

    try:
        import wmi
        c = wmi.WMI()
        drive_to_serial: dict[str, str] = {}
        for disk in c.Win32_DiskDrive():
            serial = getattr(disk, "SerialNumber", None)
            model = getattr(disk, "Model", None)
            for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                for logical in partition.associators("Win32_LogicalDiskToPartition"):
                    letter = logical.DeviceID
                    drive_to_serial[letter] = (serial or model or "").strip()

        mapped = False
        for part in partitions:
            letter = part.device.split(":")[0] + ":\\"
            serial = drive_to_serial.get(letter, "")
            if serial and disk_device and serial == disk_device.get("serial"):
                disk_parts.append(_partition_entry(part))
                mapped = True
            elif serial and usb_device and serial == usb_device.get("serial"):
                usb_parts.append(_partition_entry(part))
                mapped = True

        if not mapped:
            raise RuntimeError("WMI mapping produced no results, use fallback")

    except Exception:
        for part in partitions:
            if "removable" in part.opts and usb_device:
                usb_parts.append(_partition_entry(part))
            elif "fixed" in part.opts and disk_device:
                disk_parts.append(_partition_entry(part))

    if disk_device:
        disk_device["partitions"] = disk_parts
        devices.append(disk_device)
    if usb_device:
        usb_device["partitions"] = usb_parts
        devices.append(usb_device)

    return devices


# ──────────────────────────────────────────────
# Linux
# ──────────────────────────────────────────────

def _list_devices_linux() -> list:
    """
    Uses pyudev for rich device metadata and psutil for partition info.
    Falls back to /sys parsing if pyudev is unavailable.
    """
    import psutil

    devices = []
    partitions = psutil.disk_partitions(all=False)
    mount_to_part: dict[str, object] = {p.mountpoint: p for p in partitions}

    def _parts_for_devname(devname: str) -> list[dict]:
        """Return psutil partition entries whose device starts with devname."""
        result = []
        for part in partitions:
            # e.g. /dev/sda -> matches /dev/sda1, /dev/sda2
            if part.device == devname or part.device.startswith(devname):
                result.append(_partition_entry(part))
        return result

    # ── Try pyudev ──
    try:
        import pyudev
        context = pyudev.Context()

        # Internal disks (block, non-partition, non-loop/ram)
        for device in context.list_devices(subsystem="block", DEVTYPE="disk"):
            dev_node = device.get("DEVNAME", "")
            if not dev_node or any(x in dev_node for x in ("loop", "ram", "zram")):
                continue
            # Skip USB mass-storage here; handled separately below
            if device.get("ID_BUS") == "usb":
                continue

            size_str = None
            try:
                size_bytes = int(device.get("ID_PART_TABLE_SIZE") or 0)
                if size_bytes == 0:
                    sys_size_path = f"/sys/block/{os.path.basename(dev_node)}/size"
                    with open(sys_size_path) as f:
                        size_bytes = int(f.read().strip()) * 512
                size_str = _bytes_to_gb_str(size_bytes)
            except Exception:
                pass

            disk_entry = {
                "type": "disk",
                "id": dev_node,
                "model": device.get("ID_MODEL", ""),
                "serial": device.get("ID_SERIAL_SHORT", device.get("ID_SERIAL", "")),
                "manufacturer": device.get("ID_VENDOR", ""),
                "size": size_str,
                "partitions": _parts_for_devname(dev_node),
            }
            devices.append(disk_entry)

        # USB storage devices
        for device in context.list_devices(subsystem="block", DEVTYPE="disk", ID_BUS="usb"):
            dev_node = device.get("DEVNAME", "")
            if not dev_node:
                continue

            size_str = None
            try:
                sys_size_path = f"/sys/block/{os.path.basename(dev_node)}/size"
                with open(sys_size_path) as f:
                    size_str = _bytes_to_gb_str(int(f.read().strip()) * 512)
            except Exception:
                pass

            usb_entry = {
                "type": "usb",
                "id": dev_node,
                "name": device.get("ID_MODEL", ""),
                "serial": device.get("ID_SERIAL_SHORT", device.get("ID_SERIAL", "")),
                "manufacturer": device.get("ID_VENDOR", ""),
                "size": size_str,
                "partitions": _parts_for_devname(dev_node),
            }
            devices.append(usb_entry)

        return devices

    except ImportError:
        pass  # pyudev not installed, use /sys fallback

    # ── /sys fallback (no third-party lib) ──
    sys_block = "/sys/block"
    if os.path.isdir(sys_block):
        for name in os.listdir(sys_block):
            if any(name.startswith(p) for p in ("loop", "ram", "zram")):
                continue
            dev_path = f"/dev/{name}"
            sys_path = f"{sys_block}/{name}"

            # Size
            size_str = None
            try:
                with open(f"{sys_path}/size") as f:
                    size_str = _bytes_to_gb_str(int(f.read().strip()) * 512)
            except Exception:
                pass

            # Detect USB via symlink path
            is_usb = False
            try:
                real = os.path.realpath(sys_path)
                is_usb = "usb" in real.lower()
            except Exception:
                pass

            # Model / vendor from /sys
            def _read_sys(path):
                try:
                    with open(path) as f:
                        return f.read().strip()
                except Exception:
                    return ""

            model = _read_sys(f"{sys_path}/device/model")
            vendor = _read_sys(f"{sys_path}/device/vendor")

            entry = {
                "type": "usb" if is_usb else "disk",
                "id": dev_path,
                "model": model,
                "name": model,
                "serial": "",
                "manufacturer": vendor,
                "size": size_str,
                "partitions": _parts_for_devname(dev_path),
            }
            devices.append(entry)

    return devices


# ──────────────────────────────────────────────
# macOS
# ──────────────────────────────────────────────

def _list_devices_macos() -> list:
    """
    Uses system_profiler (built-in) for USB and disk info.
    Falls back to diskutil for partition details.
    """
    import subprocess
    import json
    import psutil

    devices = []
    partitions = psutil.disk_partitions(all=False)

    def _parts_for_devname(devname: str) -> list[dict]:
        result = []
        for part in partitions:
            if part.device == devname or part.device.startswith(devname):
                result.append(_partition_entry(part))
        return result

    # ── USB devices via system_profiler ──
    try:
        result = subprocess.run(
            ["system_profiler", "SPUSBDataType", "-json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usb_items = data.get("SPUSBDataType", [])

            def _walk_usb(items):
                for item in items:
                    name = item.get("_name", "")
                    serial = item.get("serial_num", "")
                    manufacturer = item.get("manufacturer", "")
                    bsd_name = item.get("bsd_name", "")  # e.g. "disk2"
                    capacity = item.get("Media", [{}])
                    size_str = None
                    try:
                        size_str = item.get("capacity") or item.get("size")
                    except Exception:
                        pass

                    # Only yield items that are storage (have a bsd_name or media)
                    if bsd_name or capacity:
                        dev_path = f"/dev/{bsd_name}" if bsd_name else ""
                        devices.append({
                            "type": "usb",
                            "id": dev_path or name,
                            "name": name,
                            "serial": serial,
                            "manufacturer": manufacturer,
                            "size": size_str,
                            "partitions": _parts_for_devname(dev_path) if dev_path else [],
                        })
                    # Recurse into hubs
                    for key, val in item.items():
                        if isinstance(val, list) and key not in ("Media",):
                            _walk_usb(val)

            _walk_usb(usb_items)
    except Exception:
        pass

    # ── Internal disks via diskutil ──
    try:
        result = subprocess.run(
            ["diskutil", "list", "-plist"],
            capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            import plistlib
            plist = plistlib.loads(result.stdout)
            all_disks = plist.get("AllDisksAndPartitions", [])

            for disk in all_disks:
                dev_name = disk.get("DeviceIdentifier", "")  # e.g. "disk0"
                dev_path = f"/dev/{dev_name}"
                size_str = _bytes_to_gb_str(disk.get("Size"))

                # Skip if already captured as USB
                already_usb = any(
                    d["type"] == "usb" and d["id"] == dev_path for d in devices
                )
                if already_usb:
                    continue

                # Get model info from system_profiler SATA/NVMe
                model = ""
                try:
                    sp_result = subprocess.run(
                        ["system_profiler", "SPStorageDataType", "-json"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if sp_result.returncode == 0:
                        sp_data = json.loads(sp_result.stdout)
                        for item in sp_data.get("SPStorageDataType", []):
                            if dev_name in item.get("bsd_name", ""):
                                model = item.get("_name", "")
                                break
                except Exception:
                    pass

                disk_entry = {
                    "type": "disk",
                    "id": dev_path,
                    "model": model or dev_name,
                    "serial": "",
                    "manufacturer": "",
                    "size": size_str,
                    "partitions": _parts_for_devname(dev_path),
                }
                devices.append(disk_entry)
    except Exception:
        pass

    return devices