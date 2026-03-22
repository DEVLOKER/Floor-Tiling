document.addEventListener("DOMContentLoaded", function () {
  // Add skip button logic for step 2 (bind once on DOMContentLoaded)
  const btnSkipFingerprint = document.getElementById("btn-skip-fingerprint");
  if (btnSkipFingerprint) {
    btnSkipFingerprint.addEventListener("click", function () {
      fingerprintSkipped = true;
      currentStep = 2;
      showStep(currentStep);
    });
  }

  // ── Multistep Form Logic ──────────────────────────────────────────────
  const steps = Array.from(document.querySelectorAll(".step-card"));
  // Add a summary step dynamically if not present
  let summaryStep = document.getElementById("step-summary");
  if (!summaryStep) {
    summaryStep = document.createElement("section");
    summaryStep.className = "card step-card";
    summaryStep.id = "step-summary";
    summaryStep.innerHTML = `
      <h2>5. Summary</h2>
      <div id="summary-content">
        <!-- Populated dynamically -->
      </div>
      <div style="margin-top:2em;">
        <button id="btn-finish" class="btn btn-primary">Finish</button>
      </div>
    `;
    document.querySelector(".multistep-form").appendChild(summaryStep);
    steps.push(summaryStep);
  }
  const stepIndicators = Array.from(
    document.querySelectorAll(".step-indicator .step"),
  );
  const progressBar = document.querySelector(".step-indicator .progress");
  const btnNext = document.getElementById("step-next");
  const btnBack = document.getElementById("step-back");
  let currentStep = 0;
  function showStep(idx) {
    steps.forEach((card, i) => {
      card.classList.remove("active", "prev");
      if (i === idx) card.classList.add("active");
      else if (i < idx) card.classList.add("prev");
    });
    stepIndicators.forEach((el, i) => {
      el.classList.remove("active", "completed");
      if (i < idx) el.classList.add("completed");
      else if (i === idx) el.classList.add("active");
    });
    // Progress bar width
    if (progressBar)
      progressBar.style.width = (idx / (steps.length - 1)) * 100 + "%";
    // Nav button state
    btnBack.style.display = idx === 0 ? "none" : "inline-block";
    btnNext.textContent =
      idx === steps.length - 2
        ? "Next"
        : idx === steps.length - 1
          ? "Finish"
          : "Next";
    // If summary step, populate summary
    if (idx === steps.length - 1) {
      populateSummary();
      btnNext.style.display = "none";
    } else {
      btnNext.style.display = "inline-block";
    }
  }
  btnNext.addEventListener("click", function () {
    // Step validation logic
    let valid = true;
    let warnMsg = "";
    if (currentStep === 0) {
      // Step 1: Key Generation
      const pubKey = document.getElementById("public-key");
      if (!pubKey || !pubKey.textContent.trim()) {
        valid = false;
        warnMsg = "Please generate a key pair before continuing.";
      }
    } else if (currentStep === 1) {
      // Step 2: Hardware Fingerprint
      const deviceSelect = document.getElementById("device-select");
      const fpValueInput = document.getElementById("fp-value");
      if (!fingerprintSkipped) {
        if (deviceSelect.value === "") {
          valid = false;
          warnMsg = "Please select a storage device.";
        } else if (!fpValueInput || !fpValueInput.value.trim()) {
          valid = false;
          warnMsg =
            "Please collect the hardware fingerprint before continuing.";
        }
      }
    } else if (currentStep === 2) {
      // Step 3: Issue License
      const customerInput = document.getElementById("customer");
      const fpValueInput = document.getElementById("fp-value");
      const expiresInput = document.getElementById("expires");
      const issueOutput = document.getElementById("issue-output");
      if (!customerInput.value.trim()) {
        valid = false;
        warnMsg = "Please enter a customer name.";
      } else if (!fpValueInput.value.trim()) {
        valid = false;
        warnMsg = "Please provide a hardware fingerprint.";
      } else if (!issueOutput.textContent.trim()) {
        valid = false;
        warnMsg = "Please issue a license before continuing.";
      }
    } else if (currentStep === 3) {
      // Step 4: Build Client App
      const buildDeviceSelect = document.getElementById("build-device-select");
      const buildOutput = document.getElementById("build-output");
      // Only allow next if buildOutput contains '[Build complete]'
      if (!buildDeviceSelect || !buildDeviceSelect.value) {
        valid = false;
        warnMsg =
          "Please select a target partition before building the client app.";
      } else if (!buildOutput.textContent.includes("[Build complete]")) {
        valid = false;
        warnMsg =
          "Please wait for the build and license copy to finish before continuing.";
      }
    }
    if (!valid) {
      // Show warning in status banner (always in step 1 for now)
      const statusBanner = document.getElementById("status-banner");
      const statusText = document.getElementById("status-text");
      if (statusBanner && statusText) {
        statusBanner.className = "card status-card error";
        statusText.textContent = warnMsg;
        statusBanner.classList.remove("hidden");
      } else {
        alert(warnMsg);
      }
      return;
    }
    // Hide warning if any
    const statusBanner = document.getElementById("status-banner");
    if (statusBanner) statusBanner.classList.add("hidden");
    if (currentStep < steps.length - 1) {
      currentStep++;
      showStep(currentStep);
    }
    // Populate summary content
    function populateSummary() {
      const summaryContent = document.getElementById("summary-content");
      if (!summaryContent) return;
      // Gather info from previous steps
      const pubKey =
        document.getElementById("public-key")?.textContent.trim() || "";
      const deviceSelect = document.getElementById("device-select");
      const deviceLabel =
        deviceSelect?.options[deviceSelect.selectedIndex]?.text || "";
      const fpValue = document.getElementById("fp-value")?.value || "";
      const customer = document.getElementById("customer")?.value || "";
      const expires = document.getElementById("expires")?.value || "";
      const licenseContent =
        document.querySelector("#issue-output pre")?.textContent || "";
      const buildDeviceSelect = document.getElementById("build-device-select");
      const partitionLabel =
        buildDeviceSelect?.options[buildDeviceSelect.selectedIndex]?.text || "";
      summaryContent.innerHTML = `
        <h3>Key Generation</h3>
        <pre>${pubKey}</pre>
        <h3>Hardware Fingerprint</h3>
        <div>Device: <b>${deviceLabel}</b></div>
        <div>Fingerprint: <b>${fpValue}</b></div>
        <h3>License</h3>
        <div>Customer: <b>${customer}</b></div>
        <div>Expires: <b>${expires}</b></div>
        <pre>${licenseContent}</pre>
        <h3>Build Target</h3>
        <div>Partition: <b>${partitionLabel}</b></div>
      `;
    }
    // Handle finish button
    document.addEventListener("click", function (e) {
      if (e.target && e.target.id === "btn-finish") {
        // Optionally, reset form or redirect
        alert(
          "All steps completed! You may now close the admin panel or start a new operation.",
        );
        // location.reload(); // Uncomment to reset
      }
    });
  });
  btnBack.addEventListener("click", function () {
    if (currentStep > 0) {
      currentStep--;
      showStep(currentStep);
    }
  });
  showStep(currentStep);
  // Optionally, scroll to top on step change
  steps.forEach((card) => {
    card.addEventListener("transitionend", function () {
      if (card.classList.contains("active"))
        window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  // ── Hardware Info Cache ────────────────────────────────────────────────
  let _hardwareInfo = {};
  let _storageDevices = [];
  ("use strict");

  // ── Helpers ──────────────────────────────────────────────────────────────

  /**
   * POST JSON to an API endpoint and return the parsed response.
   * Throws on non-2xx with the detail message from the server.
   */

  async function api(url, body) {
    const opts = {
      method: body !== undefined ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) {
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || res.statusText);
    }
    return data;
  }

  function show(el) {
    el.classList.remove("hidden");
  }

  function hide(el) {
    el.classList.add("hidden");
  }

  // ── DOM Refs ─────────────────────────────────────────────────────────────
  const deviceSelect = document.getElementById("device-select");

  // ── Build Client App ──────────────────────────────────────────────────
  const buildDeviceSelect = document.getElementById("build-device-select");
  const btnBuildClient = document.getElementById("btn-build-client");
  const buildOutput = document.getElementById("build-output");
  btnBuildClient.disabled = true; // Disabled by default

  async function populateBuildDevices() {
    buildDeviceSelect.innerHTML =
      '<option value="">-- Select partition --</option>';
    const selectedDeviceId = deviceSelect.value;
    if (!selectedDeviceId) return;
    try {
      const data = await api("/api/storage-devices");
      const dev = data.devices.find(
        (d) => String(d.id) === String(selectedDeviceId),
      );
      if (
        !dev ||
        !dev.partitions ||
        !Array.isArray(dev.partitions) ||
        dev.partitions.length === 0
      ) {
        buildDeviceSelect.innerHTML =
          '<option value="">(No partitions found)</option>';
        btnBuildClient.disabled = true;
        return;
      }
      dev.partitions.forEach(function (part) {
        let label = part.volname
          ? `${part.volname} (${part.mount || part.id})`
          : part.mount || part.id;
        buildDeviceSelect.innerHTML += `<option value="${part.mount || part.id}">${label}</option>`;
      });
      // Enable if a partition is already selected
      btnBuildClient.disabled = !buildDeviceSelect.value;
    } catch (err) {
      buildDeviceSelect.innerHTML =
        '<option value="">(Error loading partitions)</option>';
      btnBuildClient.disabled = true;
      console.error("Error loading partitions:", err);
    }
  }

  buildDeviceSelect.addEventListener("change", function () {
    // Enable build button only if a partition is selected
    btnBuildClient.disabled = !buildDeviceSelect.value;
  });
  btnBuildClient.addEventListener("click", async function () {
    const partition = buildDeviceSelect.value;
    if (!partition) {
      // Show error in status banner (step 4)
      const statusBanner = document.getElementById("status-banner");
      const statusText = document.getElementById("status-text");
      if (statusBanner && statusText) {
        statusBanner.className = "card status-card error";
        statusText.textContent =
          "Please select a target partition before building the client app.";
        statusBanner.classList.remove("hidden");
      } else {
        alert(
          "Please select a target partition before building the client app.",
        );
      }
      btnBuildClient.disabled = false;
      return;
    }
    // Hide warning if any
    const statusBanner = document.getElementById("status-banner");
    if (statusBanner) statusBanner.classList.add("hidden");
    btnBuildClient.disabled = true;
    buildOutput.classList.remove("hidden");
    buildOutput.textContent = "Building client and copying license...";
    try {
      // Get license data and public key from UI
      var licenseData = "";
      var publicKey = "";
      const licenseContentEl = document.querySelector("#issue-output pre");
      if (licenseContentEl) {
        licenseData = licenseContentEl.textContent.trim();
      }
      const pubKeyEl = document.getElementById("public-key");
      if (pubKeyEl) {
        publicKey = pubKeyEl.textContent.trim();
      }
      // Step 1: Call API to copy license and update secrets
      const result = await api("/api/build-client", {
        partition,
        license_data: licenseData,
        public_key: publicKey,
      });
      buildOutput.textContent = result.detail || JSON.stringify(result);
      // Step 2: Connect to WebSocket for build output
      if (result.build_ws) {
        buildOutput.textContent += "\n\n[Build log follows...]\n";
        const wsProto = location.protocol === "https:" ? "wss" : "ws";
        const wsUrl = wsProto + "://" + location.host + result.build_ws;
        const ws = new WebSocket(wsUrl);
        ws.onopen = function () {
          // Send build parameters (e.g., model)
          ws.send(JSON.stringify({ model: "tiny" })); // TODO: allow user to select model
        };
        ws.onmessage = function (event) {
          if (event.data === "[BUILD END]") {
            buildOutput.textContent += "\n[Build complete]\n";
            btnBuildClient.disabled = false;
            ws.close();
            return;
          }
          buildOutput.textContent += event.data;
          // Auto-scroll to bottom for every new log
          buildOutput.scrollTop = buildOutput.scrollHeight;
        };
        ws.onerror = function (event) {
          buildOutput.textContent += "\n[WebSocket error]\n";
          btnBuildClient.disabled = false;
        };
        ws.onclose = function () {
          btnBuildClient.disabled = false;
        };
      } else {
        btnBuildClient.disabled = false;
      }
    } catch (err) {
      buildOutput.textContent = "Error: " + err.message;
      btnBuildClient.disabled = false;
    }
  });

  deviceSelect.addEventListener("change", function () {
    populateBuildDevices();
  });

  populateBuildDevices();
});

// ── Build Client App ──────────────────────────────────────────────────
// Place all logic inside the main IIFE
// (moved below, after helpers are defined)
/* Floor Tiling  Admin Panel  app.js */

(function () {
  // ── Hardware Info Cache ────────────────────────────────────────────────
  let _hardwareInfo = {};
  let _storageDevices = [];
  ("use strict");

  // ── Helpers ──────────────────────────────────────────────────────────────

  /**
   * POST JSON to an API endpoint and return the parsed response.
   * Throws on non-2xx with the detail message from the server.
   */
  async function api(url, body) {
    const opts = {
      method: body !== undefined ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) {
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || res.statusText);
    }
    return data;
  }

  function show(el) {
    el.classList.remove("hidden");
  }

  function hide(el) {
    el.classList.add("hidden");
  }

  // ── DOM Refs ─────────────────────────────────────────────────────────────
  const optCpu = document.getElementById("opt-cpu");
  const optBoard = document.getElementById("opt-board");
  const optMac = document.getElementById("opt-mac");

  const statusBanner = document.getElementById("status-banner");
  const statusText = document.getElementById("status-text");

  const btnKeygen = document.getElementById("btn-keygen");
  const btnKeygenForce = document.getElementById("btn-keygen-force");
  const keygenOutput = document.getElementById("keygen-output");

  const usbPathInput = document.getElementById("usb-path");
  const btnFingerprint = document.getElementById("btn-fingerprint");
  const fingerprintOutput = document.getElementById("fingerprint-output");
  const fpTbody = document.querySelector("#fp-components tbody");
  const fpHashValue = document.getElementById("fp-hash-value");
  const btnCopyFp = document.getElementById("btn-copy-fp");

  const customerInput = document.getElementById("customer");
  const fpValueInput = document.getElementById("fp-value");
  const expiresInput = document.getElementById("expires");
  const btnIssue = document.getElementById("btn-issue");
  const issueOutput = document.getElementById("issue-output");

  const deviceSelect = document.getElementById("device-select");

  // ── Status ───────────────────────────────────────────────────────────────

  async function refreshStatus() {
    try {
      const data = await api("/api/keys-status");
      const keypairUI = document.getElementById("keypair-ui");
      const pubKey = document.getElementById("public-key");
      const privKey = document.getElementById("private-key");
      const btnCopyPub = document.getElementById("btn-copy-public");
      const btnCopyPriv = document.getElementById("btn-copy-private");
      // Show public and private key if present
      if (data.has_private_key && (data.public_key_pem || data.public_key)) {
        statusBanner.className = "card status-card ok";
        statusText.textContent = "Key pair found. Ready to issue licenses.";
        pubKey.textContent = data.public_key_pem || data.public_key;
        keypairUI.classList.remove("hidden");
        btnCopyPub.onclick = function () {
          navigator.clipboard.writeText(pubKey.textContent);
          btnCopyPub.textContent = "Copied!";
          setTimeout(() => (btnCopyPub.textContent = "Copy"), 1500);
        };
        // Show private key if present
        if (data.private_key_pem || data.private_key) {
          privKey.textContent = data.private_key_pem || data.private_key;
          privKey.parentElement.style.display = "flex";
          btnCopyPriv.onclick = function () {
            navigator.clipboard.writeText(privKey.textContent);
            btnCopyPriv.textContent = "Copied!";
            setTimeout(() => (btnCopyPriv.textContent = "Copy"), 1500);
          };
        } else {
          privKey.textContent = "";
          privKey.parentElement.style.display = "none";
        }
      } else {
        statusBanner.className = "card status-card warn";
        statusText.textContent =
          "No key pair detected. Generate one in step 1.";
        keypairUI.classList.add("hidden");
      }
    } catch (err) {
      statusBanner.className = "card status-card error";
      statusText.textContent = "Cannot reach admin API: " + err.message;
      const keypairUI = document.getElementById("keypair-ui");
      if (keypairUI) keypairUI.classList.add("hidden");
    }
  }

  // ── Keygen ───────────────────────────────────────────────────────────────

  async function handleKeygen(force) {
    btnKeygen.disabled = true;
    btnKeygenForce.disabled = true;
    try {
      const data = await api("/api/keygen", { force });
      // Show paths in keygen-output
      keygenOutput.textContent = `Public Key Path: ${data.public_key_path}\nPrivate Key Path: ${data.private_key_path}`;
      show(keygenOutput);
      // Show keys in UI area
      const keypairUI = document.getElementById("keypair-ui");
      const pubKey = document.getElementById("public-key");
      const privKey = document.getElementById("private-key");
      const btnCopyPub = document.getElementById("btn-copy-public");
      const btnCopyPriv = document.getElementById("btn-copy-private");
      pubKey.textContent = data.public_key_pem || "";
      privKey.textContent = data.private_key_pem || "";
      keypairUI.classList.remove("hidden");
      btnCopyPub.onclick = function () {
        navigator.clipboard.writeText(pubKey.textContent);
        btnCopyPub.textContent = "Copied!";
        setTimeout(() => (btnCopyPub.textContent = "Copy"), 1500);
      };
      btnCopyPriv.onclick = function () {
        navigator.clipboard.writeText(privKey.textContent);
        btnCopyPriv.textContent = "Copied!";
        setTimeout(() => (btnCopyPriv.textContent = "Copy"), 1500);
      };
      await refreshStatus();
    } catch (err) {
      keygenOutput.textContent = "Error: " + err.message;
      show(keygenOutput);
    } finally {
      btnKeygen.disabled = false;
      btnKeygenForce.disabled = false;
    }
  }

  btnKeygen.addEventListener("click", function () {
    handleKeygen(false);
  });

  btnKeygenForce.addEventListener("click", function () {
    if (!confirm("This will overwrite the existing key pair. Continue?")) {
      return;
    }
    handleKeygen(true);
  });

  // ── Fingerprint ──────────────────────────────────────────────────────────
  // Dynamic fingerprint table
  async function updateFingerprintTable() {
    fpTbody.innerHTML = "";
    fpHashValue.textContent = "";
    const fpHashContainer = document.querySelector(".fp-hash");
    fpHashContainer.classList.add("hidden");
    let hasAny = false;
    // Storage device
    const selectedDeviceId = deviceSelect.value;
    // Only show fingerprint-output if a storage device is selected
    if (_storageDevices.length && selectedDeviceId) {
      const dev = _storageDevices.find(
        (d) => String(d.id) === String(selectedDeviceId),
      );
      if (dev) {
        hasAny = true;
        var tr = document.createElement("tr");
        tr.id = "row-storage";
        // Show serial if present, else show device ID
        tr.innerHTML = `<td>Storage Device (${dev.type}) Serial</td><td>${typeof dev.serial !== "undefined" ? dev.serial : dev.id}</td>`;
        fpTbody.appendChild(tr);
      } else {
        // Debug: device not found
        var tr = document.createElement("tr");
        tr.innerHTML = `<td colspan='2'><em>Selected device not found in device list.</em></td>`;
        fpTbody.appendChild(tr);
      }
      // Optional hardware rows (from cache)
      function addOptRow(key, label, value) {
        var tr = document.createElement("tr");
        tr.id = "row-" + key;
        tr.innerHTML = `<td>${label} (optional)</td><td>${value || "(not available)"}</td>`;
        fpTbody.appendChild(tr);
      }
      if (optCpu.checked) {
        hasAny = true;
        addOptRow("cpu", "CPU ID", _hardwareInfo.cpu_id);
      }
      if (optBoard.checked) {
        hasAny = true;
        addOptRow("board", "Board UUID", _hardwareInfo.board_uuid);
      }
      if (optMac.checked) {
        hasAny = true;
        addOptRow("mac", "MAC Address", _hardwareInfo.mac_address);
      }
      show(fingerprintOutput);
      btnFingerprint.disabled = false;
    } else {
      hide(fingerprintOutput);
      btnFingerprint.disabled = true;
    }
  }

  // Initial table
  updateFingerprintTable();

  // Register checkbox event handlers ONCE (not inside updateFingerprintTable)
  [optCpu, optBoard, optMac].forEach(function (el) {
    el.addEventListener("change", function () {
      updateFingerprintTable();
    });
  });

  btnFingerprint.addEventListener("click", async function () {
    btnFingerprint.disabled = true;
    const fpHashContainer = document.querySelector(".fp-hash");
    try {
      // Gather serials from cache/UI
      let storage_serial = "";
      let cpu_serial = "";
      let board_serial = "";
      let mac_serial = "";
      const selectedDeviceId = deviceSelect.value;
      if (_storageDevices.length && selectedDeviceId) {
        const dev = _storageDevices.find(
          (d) => String(d.id) === String(selectedDeviceId),
        );
        if (dev && typeof dev.serial !== "undefined")
          storage_serial = dev.serial;
      }
      if (optCpu.checked) cpu_serial = _hardwareInfo.cpu_id || "";
      if (optBoard.checked) board_serial = _hardwareInfo.board_uuid || "";
      if (optMac.checked) mac_serial = _hardwareInfo.mac_address || "";
      const fingerprint = await api("/api/hardware-fingerprint", {
        storage_serial,
        cpu_serial,
        board_serial,
        mac_serial,
      });
      // Only update the hash value, table remains as per cache/UI
      if (fingerprint) {
        fpHashValue.textContent = fingerprint;
        fpHashContainer.classList.remove("hidden");
      } else {
        fpHashValue.textContent = "";
        fpHashContainer.classList.add("hidden");
      }
      fpValueInput.value = fingerprint || "";
      show(fingerprintOutput);
    } catch (err) {
      fpTbody.innerHTML = `<tr><td colspan='2'>Error: ${err.message}</td></tr>`;
      fpHashValue.textContent = "";
      fpHashContainer.classList.add("hidden");
      show(fingerprintOutput);
    } finally {
      btnFingerprint.disabled = false;
    }
  });

  btnCopyFp.addEventListener("click", function () {
    var hash = fpHashValue.textContent;
    if (!hash) return;
    navigator.clipboard.writeText(hash).then(function () {
      btnCopyFp.textContent = "Copied!";
      setTimeout(function () {
        btnCopyFp.textContent = "Copy";
      }, 1500);
    });
  });

  // ── Issue License ────────────────────────────────────────────────────────

  btnIssue.addEventListener("click", async function () {
    btnIssue.disabled = true;
    try {
      var privKey = document.getElementById("private-key").textContent.trim();
      var body = {
        customer: customerInput.value.trim(),
        fingerprint: fpValueInput.value.trim(),
        expires: expiresInput.value || null,
        private_key: privKey,
      };
      var data = await api("/api/license-issue", body);
      // Show license file content if available
      if (data.license_content) {
        let html = `<pre style="margin-bottom:0;">${data.license_content}</pre>`;
        if (data.download_url) {
          html += `<a href="${data.download_url}" download class="btn btn-secondary" style="position: absolute; top: 8px; right: 8px;">Download</a>`;
        }
        issueOutput.innerHTML = html;
      } else {
        issueOutput.textContent = JSON.stringify(data, null, 2);
      }
      show(issueOutput);
    } catch (err) {
      issueOutput.textContent = "Error: " + err.message;
      show(issueOutput);
    } finally {
      btnIssue.disabled = false;
    }
  });

  // ── Device Dropdown ──────────────────────────────────────────────────────

  async function fetchHardwareInfo() {
    try {
      // Use new endpoint for hardware info only (no fingerprint)
      const data = await api("/api/hardware-info");
      // New API returns { devices, cpu_id, board_uuid, mac_address }
      _hardwareInfo = {
        cpu_id: data.cpu_id,
        board_uuid: data.board_uuid,
        mac_address: data.mac_address,
      };
      _storageDevices = data.devices || [];
    } catch (err) {
      _hardwareInfo = { cpu_id: null, board_uuid: null, mac_address: null };
    }
  }

  async function refreshHardwareAndDevices() {
    await Promise.all([fetchHardwareInfo(), populateDevices()]);
    updateFingerprintTable();
  }

  // Add Refresh button to Hardware Fingerprint card
  const fpCards = document.querySelectorAll("section.card");
  let fpCard = null;
  fpCards.forEach((card) => {
    const h2 = card.querySelector("h2");
    if (h2 && h2.textContent.trim().startsWith("2. Hardware Fingerprint")) {
      fpCard = card;
    }
  });
  if (fpCard) {
    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "Refresh";
    refreshBtn.className = "btn btn-secondary";
    refreshBtn.style.float = "right";
    refreshBtn.onclick = function () {
      refreshBtn.disabled = true;
      refreshBtn.textContent = "Refreshing...";
      refreshHardwareAndDevices().finally(() => {
        refreshBtn.disabled = false;
        refreshBtn.textContent = "Refresh";
      });
    };
    fpCard.querySelector("h2").after(refreshBtn);
  }

  // On page load, fetch all hardware info and devices, then update UI
  (async function () {
    await refreshHardwareAndDevices();
  })();

  async function populateDevices() {
    try {
      const data = await api("/api/storage-devices");
      _storageDevices = data.devices;
      deviceSelect.innerHTML =
        '<option value="">-- Select storage device --</option>';
      data.devices.forEach(function (dev) {
        let label = dev.type.toUpperCase() + ": ";
        if (dev.type === "disk" || dev.type === "usb") {
          label += dev.id + " ";
          if (dev.size) label += `[Size: ${dev.size}] `;
          if (dev.manufacturer) label += `[Manufacturer: ${dev.manufacturer}] `;
        } else if (dev.type === "logical") {
          label += dev.id + " ";
          if (dev.volname) label += dev.volname + " ";
          if (dev.removable) label += "[Removable] ";
          if (dev.desc) label += dev.desc + " ";
        }
        deviceSelect.innerHTML += `<option value="${dev.id}">${label.trim()}</option>`;
      });
    } catch (err) {
      deviceSelect.innerHTML =
        '<option value="">(Error loading devices)</option>';
    }
    updateFingerprintTable();
  }

  deviceSelect.addEventListener("change", function () {
    if (usbPathInput) {
      usbPathInput.value = deviceSelect.value;
    }
    updateFingerprintTable();
  });

  // ── Init ─────────────────────────────────────────────────────────────────

  refreshStatus();
})();
// );
