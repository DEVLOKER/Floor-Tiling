// Base URL for all API calls. Empty string = same origin (served by uvicorn).
// Change to "http://127.0.0.1:8000" if you open index.html directly from disk.
const API_URL = "/api";

// ── App state ─────────────────────────────────────────────────────────────────
let state = {
  originalImage: null,
  canvas: null,
  ctx: null,
  floorMask: null,
  floorConfidence: 0,
  isLoading: false,
  imageDimensions: { width: 0, height: 0 },
  tileMode: "color", // "color" | "texture"
  tileTextureDataUrl: null, // base64 data URL of primary (light) texture
  tileTextureDarkDataUrl: null, // base64 data URL of secondary (dark) texture
  resultUrl: null, // object URL of last applied-tiles result
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  state.canvas = document.getElementById("mainCanvas");
  state.ctx = state.canvas.getContext("2d");
  initEventListeners();
  initTextureUpload();
  updateTilePreview();
  syncPatternUI();
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function val(id) {
  return document.getElementById(id).value;
}
function badge(id, text) {
  document.getElementById(id).textContent = text;
}

// ── Loading overlay + toast notifications ────────────────────────────────────
function showStatus(msg, type) {
  const overlay = document.getElementById("loadingOverlay");
  if (type === "info") {
    // Show loading overlay while processing
    const plain = msg.replace(/<[^>]*>/g, "").trim();
    document.getElementById("loadingText").textContent =
      plain || "Processing\u2026";
    overlay.style.display = "flex";
  } else {
    // Hide loading overlay and show a toast
    overlay.style.display = "none";
    _showToast(msg, type);
  }
}

function _showToast(msg, type) {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  const dur = type === "error" ? 6000 : 3500;
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 320);
  }, dur);
}

function isCheckerPattern() {
  return ["checkerboard", "diagonal_checkerboard"].includes(val("tilePattern"));
}

// ── Pattern / colour UI sync ──────────────────────────────────────────────────
function syncPatternUI() {
  const isChecker = isCheckerPattern();
  document.getElementById("normalColorRow").style.display = isChecker
    ? "none"
    : "";
  document
    .getElementById("checkerColorRow")
    .classList.toggle("visible", isChecker);

  // Texture mode: show/hide dark texture slot and switch to dual-column layout
  const darkGroup = document.getElementById("textureDarkGroup");
  const pairRow = document.getElementById("texturePairRow");
  const lightLbl = document.getElementById("textureLightLabel");
  if (darkGroup) darkGroup.style.display = isChecker ? "" : "none";
  if (pairRow) pairRow.classList.toggle("dual", isChecker);
  if (lightLbl)
    lightLbl.textContent = isChecker ? "Light Texture" : "Tile Texture";
}

// ── Side panel ───────────────────────────────────────────────────────────────
function openPanel() {
  document.getElementById("sidePanel").classList.add("open");
  document.getElementById("panelBackdrop").classList.add("visible");
}
function closePanel() {
  document.getElementById("sidePanel").classList.remove("open");
  document.getElementById("panelBackdrop").classList.remove("visible");
}

// ── Tile mode toggle (Color / Texture) ───────────────────────────────────────
function setTileMode(mode) {
  state.tileMode = mode;
  document
    .getElementById("btnModeColor")
    .classList.toggle("active", mode === "color");
  document
    .getElementById("btnModeTexture")
    .classList.toggle("active", mode === "texture");
  document
    .getElementById("colorModePanel")
    .classList.toggle("active", mode === "color");
  document
    .getElementById("textureModePanel")
    .classList.toggle("active", mode === "texture");
  updateTilePreview();
}

// ── Texture upload ────────────────────────────────────────────────────────────
function initTextureUpload() {
  _bindTextureSlot(
    document.getElementById("textureUploadArea"),
    document.getElementById("textureFileInput"),
    "light",
  );
  _bindTextureSlot(
    document.getElementById("textureDarkUploadArea"),
    document.getElementById("textureDarkFileInput"),
    "dark",
  );
}

function _bindTextureSlot(area, input, which) {
  area.addEventListener("click", () => input.click());
  area.addEventListener("dragover", (e) => {
    e.preventDefault();
    area.style.borderColor = "#667eea";
  });
  area.addEventListener("dragleave", () => {
    area.style.borderColor = "";
  });
  area.addEventListener("drop", (e) => {
    e.preventDefault();
    area.style.borderColor = "";
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) loadTextureFile(f, which);
  });
  input.addEventListener("change", (e) => {
    if (e.target.files[0]) loadTextureFile(e.target.files[0], which);
  });
}

function loadTextureFile(file, which = "light") {
  const reader = new FileReader();
  reader.onload = (e) => {
    if (which === "dark") {
      state.tileTextureDarkDataUrl = e.target.result;
      document.getElementById("textureDarkThumb").src = e.target.result;
      document.getElementById("textureDarkName").textContent = file.name;
      document.getElementById("textureDarkEmpty").style.display = "none";
      document.getElementById("textureDarkPreview").style.display = "block";
      document
        .getElementById("textureDarkUploadArea")
        .classList.add("has-texture");
    } else {
      state.tileTextureDataUrl = e.target.result;
      document.getElementById("textureThumb").src = e.target.result;
      document.getElementById("textureName").textContent = file.name;
      document.getElementById("textureEmpty").style.display = "none";
      document.getElementById("texturePreview").style.display = "block";
      document.getElementById("textureUploadArea").classList.add("has-texture");
    }
    updateTilePreview();
  };
  reader.readAsDataURL(file);
}

// ── Image helpers ─────────────────────────────────────────────────────────────

/** Blob of original image — no overlays. Used for /api/apply-tiles. */
function originalImageToBlob() {
  const tmp = document.createElement("canvas");
  tmp.width = state.canvas.width;
  tmp.height = state.canvas.height;
  tmp
    .getContext("2d")
    .drawImage(state.originalImage, 0, 0, tmp.width, tmp.height);
  return new Promise((resolve) => tmp.toBlob(resolve, "image/jpeg", 0.95));
}

/** Convert a base64 data URL to a Blob. */
async function dataUrlToBlob(dataUrl) {
  const res = await fetch(dataUrl);
  return res.blob();
}

// ── Event listeners ───────────────────────────────────────────────────────────
function initEventListeners() {
  const fileInput = document.getElementById("fileInput");

  // Upload buttons (top bar + welcome screen)
  document
    .getElementById("uploadBtn")
    .addEventListener("click", () => fileInput.click());
  document
    .getElementById("welcomeUploadBtn")
    .addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files[0]) handleImageUpload(e.target.files[0]);
  });

  // Drag & drop on the entire document (with counter to handle child element events)
  let _dragCount = 0;
  document.addEventListener("dragenter", (e) => {
    if (e.dataTransfer.types.includes("Files")) {
      _dragCount++;
      document.getElementById("dropOverlay").classList.add("visible");
    }
  });
  document.addEventListener("dragleave", () => {
    _dragCount = Math.max(0, _dragCount - 1);
    if (_dragCount === 0)
      document.getElementById("dropOverlay").classList.remove("visible");
  });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    _dragCount = 0;
    document.getElementById("dropOverlay").classList.remove("visible");
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) handleImageUpload(f);
  });

  state.canvas.addEventListener("click", handleCanvasClick);
  document
    .getElementById("clearFloorBtn")
    .addEventListener("click", clearFloorSelection);
  document
    .getElementById("applyTilesBtn")
    .addEventListener("click", applyTilesToFloor);

  // Side panel
  document
    .getElementById("openSettingsBtn")
    .addEventListener("click", openPanel);
  document
    .getElementById("closePanelBtn")
    .addEventListener("click", closePanel);
  document
    .getElementById("panelBackdrop")
    .addEventListener("click", closePanel);

  document.getElementById("downloadBtn").addEventListener("click", () => {
    if (!state.resultUrl) return;
    const a = document.createElement("a");
    a.href = state.resultUrl;
    a.download = "tiled-floor.jpg";
    a.click();
  });

  document.getElementById("tileWidth").addEventListener("input", (e) => {
    badge("tileWidthValue", e.target.value + " cm");
    updateTilePreview();
  });
  document.getElementById("tileHeight").addEventListener("input", (e) => {
    badge("tileHeightValue", e.target.value + " cm");
    updateTilePreview();
  });
  document.getElementById("groutHThickness").addEventListener("input", (e) => {
    badge("groutHValue", e.target.value + " px");
    document
      .getElementById("hintH")
      .style.setProperty("--th", e.target.value + "px");
  });
  document.getElementById("groutVThickness").addEventListener("input", (e) => {
    badge("groutVValue", e.target.value + " px");
    document
      .getElementById("hintV")
      .style.setProperty("--tv", e.target.value + "px");
  });

  document.getElementById("tilePattern").addEventListener("change", () => {
    syncPatternUI();
    updateTilePreview();
  });

  [
    "tileColor",
    "groutColor",
    "tileColorLight",
    "tileColorDark",
    "groutColorChecker",
    "groutColorTexture",
  ].forEach((id) => {
    document.getElementById(id).addEventListener("input", updateTilePreview);
  });
}

// ── Image upload ──────────────────────────────────────────────────────────────
async function handleImageUpload(file) {
  showStatus("Loading image...", "info");
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      const maxW = 1000;
      let w = img.width,
        h = img.height;
      if (w > maxW) {
        h = Math.round((h * maxW) / w);
        w = maxW;
      }
      state.canvas.width = w;
      state.canvas.height = h;
      state.imageDimensions = { width: w, height: h };
      state.ctx.drawImage(img, 0, 0, w, h);
      state.originalImage = img;
      state.floorMask = null;
      // Fade out the welcome overlay
      document.getElementById("welcomeOverlay").classList.add("hidden");
      updateFloorList();
      showStatus("Image loaded! Click on the floor to select it.", "success");
      document.getElementById("coordsInfo").textContent =
        "Click on the floor to select it";
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

// ── Canvas click → floor segmentation ────────────────────────────────────────
async function handleCanvasClick(event) {
  if (!state.originalImage) {
    showStatus("Please upload an image first", "error");
    return;
  }
  if (state.isLoading) {
    showStatus("Processing… please wait", "info");
    return;
  }

  const rect = state.canvas.getBoundingClientRect();
  const scaleX = state.canvas.width / rect.width;
  const scaleY = state.canvas.height / rect.height;
  const clickX = Math.round((event.clientX - rect.left) * scaleX);
  const clickY = Math.round((event.clientY - rect.top) * scaleY);

  document.getElementById("coordsInfo").textContent =
    `Selected (${clickX}, ${clickY}) — Processing…`;
  state.isLoading = true;
  showStatus("🎯 Detecting floor…", "info");

  try {
    const blob = await originalImageToBlob();
    const fd = new FormData();
    fd.append("image", blob, "room.jpg");
    fd.append("click_x", clickX);
    fd.append("click_y", clickY);

    const res = await fetch(`${API_URL}/segment-floor`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    const result = await res.json();

    state.floorMask = result.mask;
    state.floorConfidence = result.score;
    redrawWithFloorHighlight();
    updateFloorList();
    document.getElementById("coordsInfo").textContent =
      `✅ Floor selected! (confidence: ${(result.score * 100).toFixed(1)}%)`;
    showStatus("Floor selected! Adjust settings and apply tiles.", "success");
  } catch (err) {
    console.error(err);
    showStatus(`Error: ${err.message}`, "error");
    document.getElementById("coordsInfo").textContent =
      "❌ Failed — try clicking another area.";
  } finally {
    state.isLoading = false;
  }
}

// ── Apply tiles ───────────────────────────────────────────────────────────────
async function applyTilesToFloor() {
  if (!state.originalImage) {
    showStatus("Please upload an image first", "error");
    return;
  }
  if (!state.floorMask) {
    showStatus("Please select a floor first", "error");
    return;
  }
  if (state.tileMode === "texture" && !state.tileTextureDataUrl) {
    showStatus("Please upload a texture image first", "error");
    return;
  }
  const isChecker = isCheckerPattern();
  if (
    state.tileMode === "texture" &&
    isChecker &&
    !state.tileTextureDarkDataUrl
  ) {
    showStatus(
      "Please upload a dark texture for the checkerboard pattern",
      "error",
    );
    return;
  }

  showStatus("🎨 Applying tiles to floor…", "info");
  state.isLoading = true;

  const tileColor = isChecker ? val("tileColorLight") : val("tileColor");
  const tileColor2 = isChecker ? val("tileColorDark") : "#333333";
  const groutColor =
    state.tileMode === "texture"
      ? val("groutColorTexture")
      : isChecker
        ? val("groutColorChecker")
        : val("groutColor");

  try {
    const blob = await originalImageToBlob();
    const maskData = new Uint8Array(state.floorMask.flat());
    const maskBlob = new Blob([maskData], { type: "application/octet-stream" });

    const fd = new FormData();
    fd.append("image", blob, "room.jpg");
    fd.append("mask", maskBlob, "mask.bin");
    fd.append("tile_width", val("tileWidth"));
    fd.append("tile_height", val("tileHeight"));
    fd.append("tile_color", tileColor);
    fd.append("tile_color2", tileColor2);
    fd.append("grout_color", groutColor);
    fd.append("grout_h_thickness", val("groutHThickness"));
    fd.append("grout_v_thickness", val("groutVThickness"));
    fd.append("pattern", val("tilePattern"));

    if (state.tileMode === "texture" && state.tileTextureDataUrl) {
      fd.append(
        "tile_texture",
        await dataUrlToBlob(state.tileTextureDataUrl),
        "texture.jpg",
      );
      if (isChecker && state.tileTextureDarkDataUrl) {
        fd.append(
          "tile_texture2",
          await dataUrlToBlob(state.tileTextureDarkDataUrl),
          "texture2.jpg",
        );
      }
    }

    const res = await fetch(`${API_URL}/apply-tiles`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`Tile application failed: ${res.status}`);

    const resultBlob = await res.blob();
    // Revoke any previous result URL to free memory
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(resultBlob);

    const img = new Image();
    img.onload = () => {
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
      // Show the download FAB
      document.getElementById("downloadFabWrap").style.display = "";
      showStatus("✅ Tiles applied! Click ⬇️ to download.", "success");
      state.isLoading = false;
    };
    img.src = state.resultUrl;
  } catch (err) {
    console.error(err);
    showStatus(`Error: ${err.message}`, "error");
    state.isLoading = false;
  }
}

// ── Floor highlight overlay ───────────────────────────────────────────────────
function redrawWithFloorHighlight() {
  if (!state.originalImage || !state.floorMask) return;
  state.ctx.drawImage(
    state.originalImage,
    0,
    0,
    state.canvas.width,
    state.canvas.height,
  );

  const imageData = state.ctx.getImageData(
    0,
    0,
    state.canvas.width,
    state.canvas.height,
  );
  const d = imageData.data;
  for (let y = 0; y < state.canvas.height; y++) {
    for (let x = 0; x < state.canvas.width; x++) {
      if (state.floorMask[y]?.[x] > 0) {
        const i = (y * state.canvas.width + x) * 4;
        d[i] = d[i] * 0.7 + 100;
        d[i + 1] = d[i + 1] * 0.7 + 150;
        d[i + 2] = d[i + 2] * 0.7 + 100;
      }
    }
  }
  state.ctx.putImageData(imageData, 0, 0);
  drawFloorOutline();
}

function drawFloorOutline() {
  state.ctx.fillStyle = "#00FF00";
  for (let y = 1; y < state.canvas.height - 1; y++) {
    for (let x = 1; x < state.canvas.width - 1; x++) {
      if (state.floorMask[y]?.[x] > 0) {
        const n = [
          state.floorMask[y - 1]?.[x],
          state.floorMask[y + 1]?.[x],
          state.floorMask[y]?.[x - 1],
          state.floorMask[y]?.[x + 1],
        ];
        if (n.some((v) => !v || v === 0)) state.ctx.fillRect(x, y, 1, 1);
      }
    }
  }
}

function clearFloorSelection() {
  if (!state.originalImage) return;
  state.floorMask = null;
  state.ctx.drawImage(
    state.originalImage,
    0,
    0,
    state.canvas.width,
    state.canvas.height,
  );
  updateFloorList();
  showStatus("Floor selection cleared", "success");
  document.getElementById("coordsInfo").textContent =
    "Click on the floor to select it";
}

function updateFloorList() {
  const list = document.getElementById("floorList");
  const badge = document.getElementById("floorBadge");
  if (!state.floorMask) {
    list.innerHTML = '<div class="no-floor-msg">No floor selected yet.</div>';
    badge.style.display = "none";
    return;
  }
  const confText = `${(state.floorConfidence * 100).toFixed(0)}%`;
  list.innerHTML = `
    <div class="wall-item">
      <span style="display:flex;align-items:center">
        <span class="wall-color" style="background:#00FF00"></span>Floor Selected
      </span>
      <span>${confText} confidence</span>
    </div>`;
  document.getElementById("floorBadgeConf").textContent = confText;
  badge.style.display = "flex";
}

// ── Tile pattern preview canvases ─────────────────────────────────────────────
function updateTilePreview() {
  const preview = document.getElementById("tilePreview");
  const tw = parseInt(val("tileWidth") || 30);
  const th = parseInt(val("tileHeight") || 30);
  const isChecker = isCheckerPattern();
  const color1 = isChecker ? val("tileColorLight") : val("tileColor");
  const color2 = isChecker ? val("tileColorDark") : "#cccccc";
  const grout =
    state.tileMode === "texture"
      ? val("groutColorTexture")
      : isChecker
        ? val("groutColorChecker")
        : val("groutColor");
  const active = val("tilePattern");
  const useTexture = state.tileMode === "texture" && state.tileTextureDataUrl;

  const patterns = [
    { id: "grid", name: "Grid" },
    { id: "brick", name: "Brick" },
    { id: "diagonal", name: "Diagonal" },
    { id: "herringbone", name: "Herringbone" },
    { id: "checkerboard", name: "Checkerboard" },
    { id: "diagonal_checkerboard", name: "Diagonal Chess ◇" },
  ];

  preview.innerHTML = "";

  patterns.forEach((p) => {
    const div = document.createElement("div");
    div.className = "tile-option" + (p.id === active ? " selected" : "");
    div.onclick = () => {
      document.getElementById("tilePattern").value = p.id;
      document
        .querySelectorAll(".tile-option")
        .forEach((el) => el.classList.remove("selected"));
      div.classList.add("selected");
      syncPatternUI();
      updateTilePreview();
    };

    const c = document.createElement("canvas");
    c.width = 90;
    c.height = 55;
    const ctx = c.getContext("2d");

    const scale = Math.min(90 / (tw * 3), 55 / (th * 3), 1);
    const pW = Math.max(8, tw * scale * 2);
    const pH = Math.max(8, th * scale * 2);

    // Base fill
    if (useTexture) {
      const texImg = new Image();
      texImg.src = state.tileTextureDataUrl;
      ctx.fillStyle =
        texImg.complete && texImg.naturalWidth > 0
          ? ctx.createPattern(texImg, "repeat") || color1
          : "#d4b896";
    } else {
      ctx.fillStyle = color1;
    }
    ctx.fillRect(0, 0, 90, 55);

    // Precompute checker texture patterns
    let texPatLight = null,
      texPatDark = null;
    if (useTexture) {
      const li = new Image();
      li.src = state.tileTextureDataUrl;
      if (li.complete && li.naturalWidth > 0)
        texPatLight = ctx.createPattern(li, "repeat");
      if (state.tileTextureDarkDataUrl) {
        const di = new Image();
        di.src = state.tileTextureDarkDataUrl;
        if (di.complete && di.naturalWidth > 0)
          texPatDark = ctx.createPattern(di, "repeat");
      }
    }

    ctx.strokeStyle = grout;
    ctx.lineWidth = 1.5;

    switch (p.id) {
      case "grid":
        for (let x = 0; x <= 90; x += pW) {
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, 55);
          ctx.stroke();
        }
        for (let y = 0; y <= 55; y += pH) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(90, y);
          ctx.stroke();
        }
        break;

      case "brick":
        for (let row = 0; row < 10; row++) {
          const off = ((row % 2) * pW) / 2;
          for (let col = -1; col < 10; col++)
            ctx.strokeRect(col * pW + off, row * pH, pW, pH);
        }
        break;

      case "diagonal": {
        ctx.save();
        ctx.translate(45, 27.5);
        ctx.rotate(Math.PI / 4);
        for (let x = -90; x <= 180; x += pW) {
          ctx.beginPath();
          ctx.moveTo(x, -90);
          ctx.lineTo(x, 90);
          ctx.stroke();
        }
        for (let y = -90; y <= 90; y += pH) {
          ctx.beginPath();
          ctx.moveTo(-90, y);
          ctx.lineTo(180, y);
          ctx.stroke();
        }
        ctx.restore();
        break;
      }

      case "herringbone": {
        const L = pW,
          S = pH / 2;
        for (let row = 0; row < 6; row++) {
          for (let col = 0; col < 6; col++) {
            const x = col * (L + S),
              y = row * (L + S);
            ctx.strokeRect(x, y, L, S);
            ctx.strokeRect(x + L, y, S, L);
          }
        }
        break;
      }

      case "checkerboard":
        for (let row = 0; row < 10; row++) {
          for (let col = 0; col < 10; col++) {
            const isSecond = (row + col) % 2 === 1;
            ctx.fillStyle = useTexture
              ? isSecond
                ? texPatDark || "#666666"
                : texPatLight || "#d4b896"
              : isSecond
                ? color2
                : color1;
            ctx.fillRect(col * pW, row * pH, pW, pH);
            ctx.strokeStyle = grout;
            ctx.strokeRect(col * pW, row * pH, pW, pH);
          }
        }
        break;

      case "diagonal_checkerboard": {
        ctx.save();
        ctx.translate(45, 27.5);
        ctx.rotate(Math.PI / 4);
        const d = pW;
        for (let row = -4; row < 8; row++) {
          for (let col = -4; col < 8; col++) {
            const isSecond = (row + col) % 2 === 1;
            ctx.fillStyle = useTexture
              ? isSecond
                ? texPatDark || "#666666"
                : texPatLight || "#d4b896"
              : isSecond
                ? color2
                : color1;
            ctx.fillRect(col * d, row * d, d, d);
            ctx.strokeStyle = grout;
            ctx.lineWidth = 1.5;
            ctx.strokeRect(col * d, row * d, d, d);
          }
        }
        ctx.restore();
        break;
      }
    }

    const previewDiv = document.createElement("div");
    previewDiv.className = "tile-pattern-preview";
    previewDiv.style.backgroundImage = `url(${c.toDataURL()})`;
    div.appendChild(previewDiv);
    div.appendChild(document.createTextNode(p.name));
    preview.appendChild(div);
  });
}
