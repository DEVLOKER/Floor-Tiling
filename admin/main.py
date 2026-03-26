
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import generate_keypair, get_public_key_pem, get_private_key_pem, has_private_key, issue_license
from shared.utils.fingerprint import _cpu_id, _board_uuid, _mac_address, generate_fingerprint
from shared.utils.storage_devices import list_devices
from shared.config.settings import LICENSE_DIR, LICENSE_FILE

class AdminGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Floor Tiling Admin Panel")
        window_width = 800
        window_height = 600
        # Get screen width and height
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        # Calculate position x, y to center the window
        x = int((screen_width / 2) - (window_width / 2))
        y = int((screen_height / 2) - (window_height / 2))
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.resizable(True, True)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.keygen_tab = ttk.Frame(self.notebook)
        self.fingerprint_tab = ttk.Frame(self.notebook)
        self.license_tab = ttk.Frame(self.notebook)
        self.build_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.keygen_tab, text="Key Generation")
        self.notebook.add(self.fingerprint_tab, text="Hardware Fingerprint")
        self.notebook.add(self.license_tab, text="Issue License")
        self.notebook.add(self.build_tab, text="Build Client App")
        self.create_keygen_ui()
        self.create_fingerprint_ui()
        self.create_license_ui()
        self.create_build_ui()
        self.refresh_key_status()
        self.refresh_devices_and_hw()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.cancel_build()
        self.destroy()

    def create_keygen_ui(self):
        frame = self.keygen_tab
        ttk.Label(frame, text="Key Generation", font=("Arial", 16, "bold")).pack(pady=10)
        self.keygen_status = ttk.Label(frame, text="", foreground="blue")
        self.keygen_status.pack(pady=5)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Generate Key Pair", command=lambda: self.keygen(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Force Regenerate", command=lambda: self.keygen(True)).pack(side=tk.LEFT, padx=5)
        self.pubkey_text = tk.Text(frame, height=6, width=80, wrap=tk.WORD)
        self.pubkey_text.pack(pady=5)
        self.privkey_text = tk.Text(frame, height=6, width=80, wrap=tk.WORD)
        self.privkey_text.pack(pady=5)
        self.privkey_text.config(state=tk.DISABLED)

    def keygen(self, force):
        try:
            generate_keypair(force=force)
            self.keygen_status.config(text="Key pair generated.", foreground="green")
            # Always reload keys from disk to avoid blanks
            pubkey = get_public_key_pem() or ""
            privkey = get_private_key_pem() or ""
            self.pubkey_text.config(state=tk.NORMAL)
            self.pubkey_text.delete("1.0", tk.END)
            self.pubkey_text.insert(tk.END, pubkey)
            self.pubkey_text.config(state=tk.DISABLED)
            self.pubkey_text.update_idletasks()
            self.privkey_text.config(state=tk.NORMAL)
            self.privkey_text.delete("1.0", tk.END)
            self.privkey_text.insert(tk.END, privkey)
            self.privkey_text.config(state=tk.DISABLED)
            self.privkey_text.update_idletasks()
        except Exception as e:
            self.keygen_status.config(text=f"Error: {e}", foreground="red")

    def refresh_key_status(self):
        try:
            if has_private_key():
                self.keygen_status.config(text="Key pair found.", foreground="green")
                self.pubkey_text.delete("1.0", tk.END)
                self.pubkey_text.insert(tk.END, get_public_key_pem() or "")
                self.privkey_text.config(state=tk.NORMAL)
                self.privkey_text.delete("1.0", tk.END)
                self.privkey_text.insert(tk.END, get_private_key_pem() or "")
                self.privkey_text.config(state=tk.DISABLED)
            else:
                self.keygen_status.config(text="No key pair found.", foreground="orange")
        except Exception as e:
            self.keygen_status.config(text=f"Error: {e}", foreground="red")

    def create_fingerprint_ui(self):
        frame = self.fingerprint_tab
        ttk.Label(frame, text="Hardware Fingerprint", font=("Arial", 16, "bold")).pack(pady=10)
        self.device_combo = ttk.Combobox(frame, state="readonly", width=60)
        self.device_combo.pack(pady=5)
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self.update_fp_table())
        opt_frame = ttk.Frame(frame)
        opt_frame.pack(pady=5)
        self.cpu_var = tk.BooleanVar(value=True)
        self.board_var = tk.BooleanVar(value=True)
        self.mac_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="CPU ID", variable=self.cpu_var, command=self.update_fp_table).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(opt_frame, text="Board UUID", variable=self.board_var, command=self.update_fp_table).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(opt_frame, text="MAC Address", variable=self.mac_var, command=self.update_fp_table).pack(side=tk.LEFT, padx=5)
        self.fp_table = tk.Text(frame, height=6, width=80, wrap=tk.WORD, state=tk.DISABLED)
        self.fp_table.pack(pady=5)
        ttk.Button(frame, text="Collect Fingerprint", command=self.collect_fingerprint).pack(pady=5)
        self.fp_hash_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.fp_hash_var, width=70, state="readonly").pack(pady=5)

    def refresh_devices_and_hw(self):
        try:
            self.devices = list_devices()
            self.cpu_id = _cpu_id()
            self.board_uuid = _board_uuid()
            self.mac_address = _mac_address()
            labels = [f"[{d.get('type','?').upper()}] {d.get('name') or d.get('model') or d.get('id')} | SN: {d.get('serial','')} | {d.get('size','')}" for d in self.devices]
            self.device_combo['values'] = labels
            if labels:
                self.device_combo.current(0)
            self.update_fp_table()
        except Exception as e:
            self.device_combo['values'] = ["(Error loading devices)"]
            self.device_combo.current(0)

    def update_fp_table(self):
        idx = self.device_combo.current()
        if not hasattr(self, 'devices') or idx < 0 or idx >= len(self.devices):
            return
        dev = self.devices[idx]
        rows = [f"Storage Device ({dev.get('type')}) Serial: {dev.get('serial') or dev.get('id')}"]
        if self.cpu_var.get():
            rows.append(f"CPU ID: {self.cpu_id or '(not available)'}")
        if self.board_var.get():
            rows.append(f"Board UUID: {self.board_uuid or '(not available)'}")
        if self.mac_var.get():
            rows.append(f"MAC Address: {self.mac_address or '(not available)'}")
        self.fp_table.config(state=tk.NORMAL)
        self.fp_table.delete("1.0", tk.END)
        self.fp_table.insert(tk.END, "\n".join(rows))
        self.fp_table.config(state=tk.DISABLED)

    def collect_fingerprint(self):
        idx = self.device_combo.current()
        if not hasattr(self, 'devices') or idx < 0 or idx >= len(self.devices):
            messagebox.showerror("Error", "Please select a storage device.")
            return
        dev = self.devices[idx]
        parts = [dev.get("serial") or dev.get("id")]
        if self.cpu_var.get():
            parts.append(self.cpu_id)
        if self.board_var.get():
            parts.append(self.board_uuid)
        if self.mac_var.get():
            parts.append(self.mac_address)
        try:
            fp = generate_fingerprint(parts)
            self.fp_hash_var.set(fp)
        except Exception as e:
            self.fp_hash_var.set("")
            messagebox.showerror("Error", f"Failed to collect fingerprint: {e}")

    def create_license_ui(self):
        frame = self.license_tab
        ttk.Label(frame, text="Issue License", font=("Arial", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Customer Name:").pack()
        self.customer_entry = ttk.Entry(frame, width=40)
        self.customer_entry.pack(pady=2)
        ttk.Label(frame, text="Fingerprint (from previous tab):").pack()
        self.license_fp_entry = ttk.Entry(frame, width=70)
        self.license_fp_entry.pack(pady=2)
        ttk.Label(frame, text="Expires (YYYY-MM-DD, optional):").pack()
        self.expires_entry = ttk.Entry(frame, width=20)
        self.expires_entry.pack(pady=2)
        ttk.Button(frame, text="Issue License", command=self.issue_license).pack(pady=5)
        self.license_output = tk.Text(frame, height=10, width=80, wrap=tk.WORD)
        self.license_output.pack(pady=5)

    def issue_license(self):
        customer = self.customer_entry.get().strip()
        fingerprint = self.license_fp_entry.get().strip()
        expires = self.expires_entry.get().strip() or None
        privkey = self.privkey_text.get("1.0", tk.END).strip()
        if not customer or not fingerprint or not privkey:
            messagebox.showerror("Error", "Customer, fingerprint, and private key are required.")
            return
        try:
            # Determine output path for license file
            licenses_path = Path(__file__).resolve().parent / LICENSE_DIR
            licenses_path.mkdir(parents=True, exist_ok=True)
            out_path = licenses_path / LICENSE_FILE
            result = issue_license(
                customer=customer,
                fingerprint=fingerprint,
                expires=expires,
                out=str(out_path),
                private_key=privkey,
            )
            lic_content = Path(result["path"]).read_text() if isinstance(result, dict) and "path" in result else ""
            self.license_output.delete("1.0", tk.END)
            self.license_output.insert(tk.END, lic_content)
        except Exception as e:
            self.license_output.delete("1.0", tk.END)
            self.license_output.insert(tk.END, f"Error: {e}")

    def create_build_ui(self):
        frame = self.build_tab
        ttk.Label(frame, text="Build Client App", font=("Arial", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Target Partition (mount path):").pack()
        self.build_partition_combo = ttk.Combobox(frame, state="readonly", width=60)
        self.build_partition_combo.pack(pady=5)
        ttk.Button(frame, text="Refresh Partitions", command=self.refresh_partitions).pack(pady=2)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Build & Copy License", command=self.build_client).pack(side=tk.LEFT, padx=5)
        self.cancel_build_btn = ttk.Button(btn_frame, text="Cancel Build", command=self.cancel_build, state=tk.DISABLED)
        self.cancel_build_btn.pack(side=tk.LEFT, padx=5)
        self.build_output = tk.Text(frame, height=10, width=80, wrap=tk.WORD)
        self.build_output.pack(pady=5)
        self.refresh_partitions()

    def refresh_partitions(self):
        try:
            devices = list_devices()
            partitions = []
            for dev in devices:
                for part in dev.get("partitions", []):
                    # label = f"{part.get('volname') or part.get('mount') or part.get('id')} ({part.get('mount') or part.get('id')})"
                    label = f"{part.get('mount') or part.get('id')}"
                    partitions.append((label, part.get('mount') or part.get('id')))
            self.build_partition_combo['values'] = [p[0] for p in partitions]
            self._partition_map = {p[0]: p[1] for p in partitions}
            if partitions:
                self.build_partition_combo.current(0)
        except Exception as e:
            self.build_partition_combo['values'] = ["(Error loading partitions)"]
            self.build_partition_combo.current(0)

    def build_client(self):
        import subprocess
        import threading
        label = self.build_partition_combo.get()
        if not hasattr(self, '_partition_map') or label not in self._partition_map:
            messagebox.showerror("Error", "Please select a partition.")
            return
        partition = self._partition_map[label]
        license_data = self.license_output.get("1.0", tk.END).strip()
        public_key = self.pubkey_text.get("1.0", tk.END).strip()
        if not license_data or not public_key:
            messagebox.showerror("Error", "License data and public key required.")
            return
        def do_build():
            try:
                from shared.config.settings import LICENSE_DIR, LICENSE_FILE
                from pathlib import Path
                import time
                import subprocess
                import sys
                import signal
                root_dir = Path(partition)
                license_path = root_dir / LICENSE_DIR / LICENSE_FILE
                license_path.parent.mkdir(parents=True, exist_ok=True)
                license_path.write_text(license_data)
                secrets_path = Path(__file__).resolve().parent.parent / "client" / "config" / "secrets.py"
                secrets_py = f"import os\nPUBLIC_KEY_PEM = b\"\"\"\\\n{public_key}\n\"\"\""
                secrets_path.write_text(secrets_py)
                def append_output(text):
                    def _append():
                        self.build_output.insert(tk.END, text)
                        self.build_output.see(tk.END)
                    self.build_output.after(0, _append)
                self.build_output.after(0, lambda: self.build_output.delete("1.0", tk.END))
                append_output(f"License copied to {license_path}. Public key updated in client/config/secrets.py.\n")
                build_script = Path(__file__).resolve().parent.parent / "client" / "scripts" / "build_exe.bat"
                self._build_proc = None
                self._build_proc_group = None
                self.build_output.after(0, lambda: self.cancel_build_btn.config(state=tk.NORMAL))
                if build_script.exists():
                    append_output(f"Running build script: {build_script}\n")
                    try:
                        if sys.platform == "win32":
                            proc = subprocess.Popen([str(build_script), "tiny"], cwd=build_script.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                        else:
                            proc = subprocess.Popen([str(build_script), "tiny"], cwd=build_script.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
                        self._build_proc = proc
                        self._build_proc_group = True
                        while True:
                            if self._build_proc is None:
                                append_output("\n[Build cancelled]\n")
                                break
                            line = proc.stdout.readline()
                            if not line and proc.poll() is not None:
                                break
                            if line:
                                append_output(line)
                        err = proc.stderr.read()
                        if err:
                            append_output("\n[STDERR]\n" + err)
                        append_output("\n[Build complete]\n")
                    except Exception as e:
                        append_output(f"\nError running build script: {e}\n")
                else:
                    append_output(f"Build script not found: {build_script}\n")
                self.build_output.after(0, lambda: self.cancel_build_btn.config(state=tk.DISABLED))
                self._build_proc = None
                self._build_proc_group = None
            except Exception as e:
                self.build_output.after(0, lambda: self.build_output.delete("1.0", tk.END))
                self.build_output.after(0, lambda: self.build_output.insert(tk.END, f"Error: {e}"))
                self.build_output.after(0, lambda: self.cancel_build_btn.config(state=tk.DISABLED))
                self._build_proc = None
                self._build_proc_group = None
        self._build_proc = None
        threading.Thread(target=do_build).start()

    def cancel_build(self):
        import sys
        import signal
        if hasattr(self, '_build_proc') and self._build_proc is not None:
            try:
                if sys.platform == "win32":
                    # Send CTRL_BREAK_EVENT to the process group
                    self._build_proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    import os
                    os.killpg(os.getpgid(self._build_proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    self._build_proc.terminate()
                except Exception:
                    pass
            self._build_proc = None
        self._build_proc_group = None

if __name__ == "__main__":
    app = AdminGUI()
    app.mainloop()
