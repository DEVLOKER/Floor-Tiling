def list_devices() -> list:
    import platform
    import os
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
                # Robust mapping: always return devices, fallback if WMI fails
                import psutil
                partitions = psutil.disk_partitions(all=False)
                disk_parts = []
                usb_parts = []
                try:
                    import wmi
                    c = wmi.WMI()
                    drive_to_serial = {}
                    for disk in c.Win32_DiskDrive():
                        serial = getattr(disk, "SerialNumber", None)
                        model = getattr(disk, "Model", None)
                        for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                            for logical in partition.associators("Win32_LogicalDiskToPartition"):
                                drive_letter = logical.DeviceID
                                if serial:
                                    drive_to_serial[drive_letter] = serial.strip()
                                elif model:
                                    drive_to_serial[drive_letter] = model.strip()
                    # Assign partitions
                    mapped = False
                    for part in partitions:
                        drive_letter = part.device.split(":")[0] + ":\\"
                        serial = drive_to_serial.get(drive_letter)
                        if serial and disk_device and serial == disk_device["serial"]:
                            disk_parts.append({
                                "id": part.device,
                                "mount": part.mountpoint,
                                "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                "fstype": part.fstype,
                                "opts": part.opts,
                            })
                            mapped = True
                        elif serial and usb_device and serial == usb_device["serial"]:
                            usb_parts.append({
                                "id": part.device,
                                "mount": part.mountpoint,
                                "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                "fstype": part.fstype,
                                "opts": part.opts,
                            })
                            mapped = True
                    # If mapping failed, fallback
                    if not mapped:
                        for part in partitions:
                            if "removable" in part.opts and usb_device:
                                usb_parts.append({
                                    "id": part.device,
                                    "mount": part.mountpoint,
                                    "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                    "fstype": part.fstype,
                                    "opts": part.opts,
                                })
                            elif "fixed" in part.opts and disk_device:
                                disk_parts.append({
                                    "id": part.device,
                                    "mount": part.mountpoint,
                                    "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                    "fstype": part.fstype,
                                    "opts": part.opts,
                                })
                except Exception:
                    # Fallback: group by opts
                    for part in partitions:
                        if "removable" in part.opts and usb_device:
                            usb_parts.append({
                                "id": part.device,
                                "mount": part.mountpoint,
                                "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                "fstype": part.fstype,
                                "opts": part.opts,
                            })
                        elif "fixed" in part.opts and disk_device:
                            disk_parts.append({
                                "id": part.device,
                                "mount": part.mountpoint,
                                "volname": os.path.basename(part.mountpoint) if part.mountpoint else "",
                                "fstype": part.fstype,
                                "opts": part.opts,
                            })
                # Attach partitions
                if disk_device:
                    disk_device["partitions"] = disk_parts
                if usb_device:
                    usb_device["partitions"] = usb_parts
                result_devices = []
                if disk_device:
                    result_devices.append(disk_device)
                if usb_device:
                    result_devices.append(usb_device)
                return result_devices
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

