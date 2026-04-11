
import sys
import os
import tkinter as tk
from tkinter import messagebox
import platform

# Ensure parent directory is in sys.path for imports
parent = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent not in sys.path:
    sys.path.insert(0, parent)

from shared.utils.fingerprint import generate_fingerprint, _cpu_id, _board_uuid, _mac_address




# Use list_devices from shared.utils.storage_devices
from shared.utils.storage_devices import list_devices

def get_selected_device_serial():
    selected = device_var.get()
    for dev in devices:
        label = device_label(dev)
        if label == selected:
            return dev.get("serial") or dev.get("id")
    return ""

def device_label(dev):
    # Show type, name/model, serial, size
    name = dev.get("name") or dev.get("model") or dev.get("id")
    serial = dev.get("serial")
    size = dev.get("size")
    label = f"[{dev.get('type','?').upper()}] {name}"
    if serial:
        label += f" | SN: {serial}"
    if size:
        label += f" | {size}"
    return label

def collect_fingerprint():
    try:
        selected_label = device_var.get()
        if not selected_label:
            messagebox.showerror("Error", "Please select a storage device.")
            return
        serial = get_selected_device_serial()
        if not serial:
            messagebox.showerror("Error", f"Could not get serial for selected device.")
            return
        parts = [serial]
        if cpu_var.get():
            parts.append(_cpu_id())
        if board_var.get():
            parts.append(_board_uuid())
        if mac_var.get():
            parts.append(_mac_address())
        fingerprint = generate_fingerprint(parts)
        result_var.set(fingerprint)
    except Exception as e:
        messagebox.showerror("Error", str(e))


def copy_to_clipboard():
    root.clipboard_clear()
    root.clipboard_append(result_var.get())
    messagebox.showinfo("Copied", "Fingerprint copied to clipboard.")




root = tk.Tk()
root.title("Machine Fingerprint Generator")
# Center the window
window_width = 600
window_height = 400
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
x = int((screen_width / 2) - (window_width / 2))
y = int((screen_height / 2) - (window_height / 2))
root.geometry(f"{window_width}x{window_height}+{x}+{y}")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack(expand=True, fill=tk.BOTH)

title = tk.Label(frame, text="Machine Fingerprint Generator", font=("Arial", 16, "bold"))
title.pack(pady=(0, 10))

# Storage device selection
tk.Label(frame, text="Select Storage Device (required):", font=("Arial", 12)).pack(anchor="w")
devices = list_devices()
device_labels = [device_label(d) for d in devices]
device_var = tk.StringVar()
device_menu = tk.OptionMenu(frame, device_var, *device_labels)
device_menu.config(font=("Arial", 12), width=40)
device_menu.pack(pady=5, anchor="w")

# Optional hardware parts
tk.Label(frame, text="Include in fingerprint (optional):", font=("Arial", 12)).pack(anchor="w", pady=(10,0))
cpu_var = tk.BooleanVar(value=True)
board_var = tk.BooleanVar(value=True)
mac_var = tk.BooleanVar(value=True)
tk.Checkbutton(frame, text="CPU ID", variable=cpu_var, font=("Arial", 11)).pack(anchor="w")
tk.Checkbutton(frame, text="Motherboard UUID", variable=board_var, font=("Arial", 11)).pack(anchor="w")
tk.Checkbutton(frame, text="MAC Address", variable=mac_var, font=("Arial", 11)).pack(anchor="w")

btn_generate = tk.Button(frame, text="Generate Fingerprint", command=collect_fingerprint, font=("Arial", 12))
btn_generate.pack(pady=10)

result_var = tk.StringVar()
result_entry = tk.Entry(frame, textvariable=result_var, font=("Consolas", 12), width=60, state="readonly", readonlybackground="#f0f0f0")
result_entry.pack(pady=10)

btn_copy = tk.Button(frame, text="Copy to Clipboard", command=copy_to_clipboard, font=("Arial", 12))
btn_copy.pack(pady=5)

root.mainloop()
