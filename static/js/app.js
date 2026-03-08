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
function badge(id, txt) {
  document.getElementById(id).textContent = txt;
}

// ── Loading overlay + toast notifications ─────────────────────────────────────
function showStatus(msg, type) {
  const overlay = document.getElementById("loadingOverlay");
  if (type === "info") {
    const plain = msg.replace(/<[^>]*>/g, "").trim();
    document.getElementById("loadingText").textContent =
      plain || "Processing\u2026";
    overlay.style.display = "flex";
  } else {
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

// ── Pattern type helpers ──────────────────────────────────────────────────────
function isCheckerPattern() {
  return ["checkerboard", "diagonal_checkerboard"].includes(val("tilePattern"));
}

/** Patterns that use two colours / two textures (is_second flag active). */
function isDualColorPattern() {
  return [
    "checkerboard",
    "diagonal_checkerboard",
    "chevron",
    "basketweave",
    "versailles",
  ].includes(val("tilePattern"));
}

// ── Pattern / colour UI sync ──────────────────────────────────────────────────
function syncPatternUI() {
  const pattern = val("tilePattern");
  const isChevron = pattern === "chevron";
  const isBasketweave = pattern === "basketweave";
  const isVersionailles = pattern === "versailles";
  const isChecker = isCheckerPattern();
  const isDual = isDualColorPattern();

  // Show/hide single-colour vs dual-colour row
  document.getElementById("normalColorRow").style.display = isDual
    ? "none"
    : "";
  document
    .getElementById("checkerColorRow")
    .classList.toggle("visible", isDual);

  // Update dual-colour labels to match pattern context
  const lbl1 = document.getElementById("dualColorLabel1");
  const lbl2 = document.getElementById("dualColorLabel2");
  if (lbl1 && lbl2) {
    if (isChevron) {
      lbl1.textContent = "Left Arm";
      lbl2.textContent = "Right Arm";
    } else if (isBasketweave) {
      lbl1.textContent = "Horizontal";
      lbl2.textContent = "Vertical";
    } else if (isVersionailles) {
      lbl1.textContent = "Large / Wide";
      lbl2.textContent = "Tall / Small";
    } else {
      lbl1.textContent = "Light";
      lbl2.textContent = "Dark";
    }
  }

  // Texture mode: show/hide second texture slot + dual layout
  const darkGroup = document.getElementById("textureDarkGroup");
  const pairRow = document.getElementById("texturePairRow");
  const lightLbl = document.getElementById("textureLightLabel");
  const darkLbl = document.getElementById("textureDarkLabel");

  if (darkGroup) darkGroup.style.display = isDual ? "" : "none";
  if (pairRow) pairRow.classList.toggle("dual", isDual);

  if (lightLbl) {
    lightLbl.textContent = isChevron
      ? "Left Arm Texture"
      : isBasketweave
        ? "H Bundle Texture"
        : isChecker
          ? "Light Texture"
          : "Tile Texture";
  }
  if (darkLbl) {
    darkLbl.textContent = isChevron
      ? "Right Arm Texture"
      : isBasketweave
        ? "V Bundle Texture"
        : "Dark Texture";
  }
}

// ── Side panel ────────────────────────────────────────────────────────────────
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
function originalImageToBlob() {
  const tmp = document.createElement("canvas");
  tmp.width = state.canvas.width;
  tmp.height = state.canvas.height;
  tmp
    .getContext("2d")
    .drawImage(state.originalImage, 0, 0, tmp.width, tmp.height);
  return new Promise((resolve) => tmp.toBlob(resolve, "image/jpeg", 0.95));
}

async function dataUrlToBlob(dataUrl) {
  const res = await fetch(dataUrl);
  return res.blob();
}

// ── Event listeners ───────────────────────────────────────────────────────────
function initEventListeners() {
  const fileInput = document.getElementById("fileInput");

  document
    .getElementById("uploadBtn")
    .addEventListener("click", () => fileInput.click());
  document
    .getElementById("welcomeUploadBtn")
    .addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files[0]) handleImageUpload(e.target.files[0]);
  });

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

  const isDual = isDualColorPattern();
  if (state.tileMode === "texture" && isDual && !state.tileTextureDarkDataUrl) {
    showStatus("Please upload a second texture for this pattern", "error");
    return;
  }

  showStatus("🎨 Applying tiles to floor…", "info");
  state.isLoading = true;

  const tileColor = isDual ? val("tileColorLight") : val("tileColor");
  const tileColor2 = isDual ? val("tileColorDark") : "#333333";
  const groutColor =
    state.tileMode === "texture"
      ? val("groutColorTexture")
      : isDual
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
      if (isDual && state.tileTextureDarkDataUrl)
        fd.append(
          "tile_texture2",
          await dataUrlToBlob(state.tileTextureDarkDataUrl),
          "texture2.jpg",
        );
    }

    const res = await fetch(`${API_URL}/apply-tiles`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`Tile application failed: ${res.status}`);

    const resultBlob = await res.blob();
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(resultBlob);

    const img = new Image();
    img.onload = () => {
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
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
  const bdg = document.getElementById("floorBadge");
  if (!state.floorMask) {
    list.innerHTML = '<div class="no-floor-msg">No floor selected yet.</div>';
    bdg.style.display = "none";
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
  bdg.style.display = "flex";
}

// ── Chevron preview renderer ──────────────────────────────────────────────────
/**
 * Draws a chevron (V-arrow parquet) preview onto a canvas context.
 *
 * FIX: canvas is clipped to its own bounds so no drawing leaks outside,
 * and the geometry is recalculated to always fill the 90×55 thumbnail
 * regardless of aspect ratio.
 *
 * Left arm  (/) → color1 / texPatLight
 * Right arm (\) → color2 / texPatDark
 */
function drawChevronPreview(
  ctx,
  W,
  H,
  aspectRatio,
  color1,
  color2,
  grout,
  texLight = null,
  texDark = null,
) {
  // Clip drawing to canvas bounds — prevents bleed into adjacent thumbnails
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, W, H);
  ctx.clip();

  // Size planks so ~3 full V-shapes fit across the width
  // plankW = height of one V-row, plankL = half-width of one V (one arm width)
  const plankL = Math.max(10, Math.round(W / 3)); // one arm width in px
  const plankW = Math.max(5, Math.round(plankL / Math.max(aspectRatio, 0.5))); // arm height in px

  const rows = Math.ceil(H / plankW) + 2;
  const cols = Math.ceil(W / (plankL * 2)) + 2;

  // Offset so pattern starts above the canvas top (fully covers the thumbnail)
  ctx.translate(0, -plankW);

  for (let row = 0; row < rows; row++) {
    for (let col = -1; col < cols; col++) {
      // Each "cell" = one full V = left arm + right arm
      // Cell origin at top-left of the left arm
      const ox = col * plankL * 2;
      const oy = row * plankW;

      // Left arm parallelogram (/)
      //   TL=(ox, oy)  TR=(ox+plankL, oy+plankW)
      //   BR=(ox+plankL, oy+2*plankW)  BL=(ox, oy+plankW)
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.lineTo(ox, oy + plankW);
      ctx.closePath();
      ctx.fillStyle = texLight || color1;
      ctx.fill();

      // Right arm parallelogram (\)
      //   TL=(ox+plankL, oy+plankW)  TR=(ox+2*plankL, oy)
      //   BR=(ox+2*plankL, oy+plankW)  BL=(ox+plankL, oy+2*plankW)
      ctx.beginPath();
      ctx.moveTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL * 2, oy);
      ctx.lineTo(ox + plankL * 2, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.closePath();
      ctx.fillStyle = texDark || color2;
      ctx.fill();
    }
  }

  // ── Grout lines (second pass so they appear on top of fill) ──────────
  ctx.strokeStyle = grout;
  ctx.lineWidth = 1.2;

  for (let row = 0; row < rows; row++) {
    for (let col = -1; col < cols; col++) {
      const ox = col * plankL * 2;
      const oy = row * plankW;

      // Left arm outline
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.lineTo(ox, oy + plankW);
      ctx.closePath();
      ctx.stroke();

      // Right arm outline
      ctx.beginPath();
      ctx.moveTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL * 2, oy);
      ctx.lineTo(ox + plankL * 2, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.closePath();
      ctx.stroke();

      // Individual plank end-cut lines inside each arm
      // Each arm contains ceil(plankL / plankW) individual planks
      const numPlanks = Math.max(1, Math.ceil(plankL / plankW));
      for (let p = 1; p < numPlanks; p++) {
        const t = p / numPlanks;

        // Left arm: vertical cut lines spaced evenly along the diagonal
        const lx = ox + t * plankL;
        const ly = oy + t * plankW;
        ctx.beginPath();
        ctx.moveTo(lx, ly);
        ctx.lineTo(lx, ly + plankW);
        ctx.stroke();

        // Right arm: mirrored
        const rx = ox + plankL + (1 - t) * plankL;
        const ry = oy + t * plankW;
        ctx.beginPath();
        ctx.moveTo(rx, ry);
        ctx.lineTo(rx, ry + plankW);
        ctx.stroke();
      }
    }
  }

  ctx.restore(); // removes clip
}

// ── Tile pattern preview grid ─────────────────────────────────────────────────
function updateTilePreview() {
  const preview = document.getElementById("tilePreview");
  const tw = parseInt(val("tileWidth") || 30);
  const th = parseInt(val("tileHeight") || 30);
  const isDual = isDualColorPattern();
  const color1 = isDual ? val("tileColorLight") : val("tileColor");
  const color2 = isDual ? val("tileColorDark") : "#cccccc";
  const grout =
    state.tileMode === "texture"
      ? val("groutColorTexture")
      : isDual
        ? val("groutColorChecker")
        : val("groutColor");
  const active = val("tilePattern");
  const useTexture = state.tileMode === "texture" && state.tileTextureDataUrl;

  // ── All patterns including chevron ───────────────────────────────────
  const patterns = [
    { id: "grid", name: "Grid" },
    { id: "diagonal", name: "Diagonal" },
    { id: "brick", name: "Brick" },
    { id: "herringbone", name: "Herringbone" },
    { id: "chevron", name: "Chevron ∧" },
    { id: "basketweave", name: "Basketweave" },
    { id: "versailles", name: "Versailles" },
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
    ctx.fillStyle = color1;
    ctx.fillRect(0, 0, 90, 55);

    // Texture pattern objects (only valid if image is already decoded)
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
        for (let row = 0; row < 6; row++)
          for (let col = 0; col < 6; col++) {
            const x = col * (L + S),
              y = row * (L + S);
            ctx.strokeRect(x, y, L, S);
            ctx.strokeRect(x + L, y, S, L);
          }
        break;
      }

      // ── Chevron: fixed geometry, always fills the thumbnail ─────────
      case "chevron": {
        const ar = Math.max(0.5, Math.min(3.5, th > 0 ? th / tw : 1));
        drawChevronPreview(
          ctx,
          90,
          55,
          ar,
          color1,
          color2,
          grout,
          texPatLight,
          texPatDark,
        );
        break;
      }

      // ── Basketweave ──────────────────────────────────────────────────
      case "basketweave": {
        // N=2 plank bundles alternating H and V in a checkerboard of 2×2 blocks.
        // Bundle size in px: bW wide × bH tall (= N planks per bundle).
        const N = 2;
        const bW = Math.max(8, Math.round(pW));
        const bH = Math.max(8, Math.round(pH));

        // Helper: draw one N-plank bundle
        const drawBundle = (ox, oy, horiz, fill) => {
          ctx.fillStyle = fill;
          if (horiz) {
            for (let p = 0; p < N; p++)
              ctx.fillRect(ox, oy + p * (bH / N), bW, bH / N);
          } else {
            for (let p = 0; p < N; p++)
              ctx.fillRect(ox + p * (bW / N), oy, bW / N, bH);
          }
        };
        const strokeBundle = (ox, oy, horiz) => {
          ctx.strokeRect(ox, oy, bW, bH);
          if (horiz) {
            for (let p = 1; p < N; p++) {
              ctx.beginPath();
              ctx.moveTo(ox, oy + p * (bH / N));
              ctx.lineTo(ox + bW, oy + p * (bH / N));
              ctx.stroke();
            }
          } else {
            for (let p = 1; p < N; p++) {
              ctx.beginPath();
              ctx.moveTo(ox + p * (bW / N), oy);
              ctx.lineTo(ox + p * (bW / N), oy + bH);
              ctx.stroke();
            }
          }
        };

        // Fill pass
        for (let row = -1; row < Math.ceil(55 / bH) + 2; row++) {
          for (let col = -1; col < Math.ceil(90 / bW) + 2; col++) {
            const horiz = (((row + col) % 2) + 2) % 2 === 0;
            const fill = useTexture
              ? horiz
                ? texPatLight || color1
                : texPatDark || color2
              : horiz
                ? color1
                : color2;
            drawBundle(col * bW, row * bH, horiz, fill);
          }
        }
        // Grout pass
        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.2;
        for (let row = -1; row < Math.ceil(55 / bH) + 2; row++) {
          for (let col = -1; col < Math.ceil(90 / bW) + 2; col++) {
            strokeBundle(col * bW, row * bH, (((row + col) % 2) + 2) % 2 === 0);
          }
        }
        break;
      }

      // ── Versailles ───────────────────────────────────────────────────
      case "versailles": {
        // Cell = 3×3 units. Scale so ~2 full cells fit in 90×55 thumbnail.
        const cellW = Math.round(90 / 2.5); // ~36px per cell
        const cellH = Math.round(55 / 1.8); // ~30px per cell
        const u1 = cellW / 3; // 1 unit in x
        const v1 = cellH / 3; // 1 unit in y

        // Draw 3×3 grid of cells
        for (let row = -1; row < 3; row++) {
          for (let col = -1; col < 4; col++) {
            const ox = col * cellW;
            const oy = row * cellH;

            // 4 tile shapes within each cell
            const tiles = [
              { x: ox, y: oy, w: u1 * 2, h: v1 * 2, second: false }, // large
              { x: ox + u1 * 2, y: oy, w: u1, h: v1 * 2, second: true }, // tall
              { x: ox, y: oy + v1 * 2, w: u1, h: v1, second: true }, // small
              { x: ox + u1, y: oy + v1 * 2, w: u1 * 2, h: v1, second: false }, // wide
            ];

            tiles.forEach(({ x, y, w, h, second }) => {
              ctx.fillStyle = useTexture
                ? second
                  ? texPatDark || color2
                  : texPatLight || color1
                : second
                  ? color2
                  : color1;
              ctx.fillRect(x, y, w, h);
              ctx.strokeStyle = grout;
              ctx.lineWidth = 1.2;
              ctx.strokeRect(x, y, w, h);
            });
          }
        }
        break;
      }

      case "checkerboard":
        for (let row = 0; row < 10; row++)
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
        break;

      case "diagonal_checkerboard": {
        ctx.save();
        ctx.translate(45, 27.5);
        ctx.rotate(Math.PI / 4);
        const d = pW;
        for (let row = -4; row < 8; row++)
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
