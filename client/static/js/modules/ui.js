import { state } from "./state.js";
import { CONFIG } from "./config.js";
import { val } from "./helpers.js";
import { hexToRgbArray } from "./utils.js";
import { isCheckerPattern, isDualColorPattern } from "./patterns.js";

// ── AI Label Management ───────────────────────────────────────────
export function clearAutoLabels() {
  const overlay = document.getElementById("markersOverlay");
  if (overlay) {
    overlay.innerHTML = "";
    overlay.style.display = "none";
  }
}

export function drawAutoLabels(labels, onToggle) {
  if (labels) state.currentLabels = labels;
  if (onToggle) state.onLabelToggle = onToggle;

  const activeLabels = state.currentLabels;
  const activeOnToggle = state.onLabelToggle;

  const overlay = document.getElementById("markersOverlay");
  if (!overlay) {
    console.error("❌ [UI] markersOverlay not found in DOM");
    return;
  }

  overlay.innerHTML = "";
  if (!activeLabels || activeLabels.length === 0 || !state.canvas) {
    overlay.style.display = "none";
    return;
  }

  // Pin the overlay to exactly match the canvas's rendered bounding rect.
  // This accounts for the side panel, topbar, and any CSS scaling.
  overlay.style.display = "block";
  const imgW = state.canvas.width;
  const imgH = state.canvas.height;
  const rect = state.canvas.getBoundingClientRect();
  overlay.style.left = `${rect.left}px`;
  overlay.style.top = `${rect.top}px`;
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;
  overlay.style.transform = "none";

  activeLabels.forEach((l) => {
    // Container group: Centers label + marker
    const group = document.createElement("div");
    group.className =
      "surface-marker-group" +
      (state.selectedSurfaces.has(l.id) ? " active" : "");
    group.setAttribute("data-id", l.id);

    // Text Label
    const labelTranslations = { floor: "Sol", wall: "Mur" };
    const labelText = document.createElement("span");
    labelText.className = "surface-label";
    labelText.textContent = labelTranslations[l.type] || l.text;

    // The circular marker point
    const marker = document.createElement("div");
    marker.className = `surface-marker ${l.type}`;
    marker.title = `Sélectionner ${l.type === "floor" ? "le sol" : "les murs"}`;

    // Percentage-based positioning for zero-drift responsive scaling
    const px = (l.x / imgW) * 100;
    const py = (l.y / imgH) * 100;

    group.style.left = `${px}%`;
    group.style.top = `${py}%`;

    // Visual feedback: only animate if this is a fresh detection
    if (labels) {
      group.style.opacity = "0";
      requestAnimationFrame(() => (group.style.opacity = "1"));
    } else {
      group.style.opacity = "1";
    }

    group.appendChild(labelText);
    group.appendChild(marker);
    overlay.appendChild(group);

    // Interactivity
    marker.onclick = (e) => {
      e.stopPropagation();
      if (activeOnToggle) activeOnToggle(l.id);
    };
  });
}

// ── FAB visibility ──
export function updateTogglePreviewVisibility() {
  const wrap = document.getElementById("togglePreviewFabWrap");
  if (!wrap) return;
  wrap.style.display = state.originalImage && state.resultUrl ? "" : "none";
}

// UI-related functions (to be filled in next steps)
export function showStatus(msg, type) {
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

export function updateTilePreview() {
  const preview = document.getElementById("tilePreview");
  const tw = parseInt(val("tileWidth") || CONFIG.defaultTileWidth);
  const th = parseInt(val("tileHeight") || CONFIG.defaultTileHeight);
  const isDual = isDualColorPattern(val("tilePattern"));
  const color1 = isDual ? val("tileColorLight") : val("tileColor");
  const color2 = isDual ? val("tileColorDark") : CONFIG.previewColorFallback;
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
    { id: "grid", name: "Grille" },
    { id: "brick", name: "Brique" },
    { id: "herringbone", name: "Chevrons classiques" },
    { id: "chevron", name: "Chevron ∧" },
    { id: "windmill", name: "Moulin" },
    { id: "straightweave", name: "Tissage Droit" },
    { id: "bookmatch", name: "Bookmatch" },
    { id: "hopscotch", name: "Hopscotch" },
    { id: "checkerboard", name: "Damier" },
  ];

  preview.innerHTML = "";

  patterns.forEach((p) => {
    const div = document.createElement("div");
    // Only the active pattern gets the 'selected' class
    div.className = "tile-option" + (p.id === active ? " selected" : "");
    div.onclick = () => {
      const patternSelect = document.getElementById("tilePattern");
      patternSelect.value = p.id;
      patternSelect.dispatchEvent(new Event("change", { bubbles: true }));
      // Do NOT manually toggle 'selected' class here; let the render loop handle it
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
      case "herringbone": {
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, 90, 55);
        ctx.clip();

        ctx.translate(45, 27.5);
        ctx.rotate(Math.PI / 4.0);

        const L = Math.max(pW, pH * 2);
        const S = Math.min(pW, pH);

        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;

        const span = 120;
        for (let row = -span; row < span; row += L + S) {
          for (let col = -span; col < span; col += L + S) {
            // H-tile → primary colour
            ctx.fillStyle = useTexture ? texPatLight || color1 : color1;
            ctx.fillRect(col, row, L, S);
            ctx.strokeRect(col, row, L, S);

            // V-tile → secondary colour
            ctx.fillStyle = useTexture ? texPatDark || color2 : color2;
            ctx.fillRect(col + L, row, S, L);
            ctx.strokeRect(col + L, row, S, L);
          }
        }

        ctx.restore();
        break;
      }
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
      case "windmill": {
        // Windmill (pinwheel): 4 big rectangular tiles (color1) around a
        // small centre square (color2).
        // Cell size = tW + tH (square cell).
        const tW = Math.max(14, Math.round(pW));
        const tH = Math.max(7, Math.round(tW / 2));
        const cellSize = tW + tH;
        const colsW = Math.ceil(90 / cellSize) + 2;
        const rowsW = Math.ceil(55 / cellSize) + 2;
        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;
        for (let row = -1; row < rowsW; row++) {
          for (let col = -1; col < colsW; col++) {
            const ox = col * cellSize;
            const oy = row * cellSize;
            const bigFill = useTexture ? texPatLight || color1 : color1;
            const ctrFill = useTexture ? texPatDark || color2 : color2;
            // Top H-tile (ox, oy, tW × tH)
            ctx.fillStyle = bigFill;
            ctx.fillRect(ox, oy, tW, tH);
            ctx.strokeRect(ox, oy, tW, tH);
            // Right V-tile (ox+tW, oy, tH × tW)
            ctx.fillStyle = bigFill;
            ctx.fillRect(ox + tW, oy, tH, tW);
            ctx.strokeRect(ox + tW, oy, tH, tW);
            // Bottom H-tile (ox+tH, oy+tW, tW × tH)
            ctx.fillStyle = bigFill;
            ctx.fillRect(ox + tH, oy + tW, tW, tH);
            ctx.strokeRect(ox + tH, oy + tW, tW, tH);
            // Left V-tile (ox, oy+tH, tH × tW)
            ctx.fillStyle = bigFill;
            ctx.fillRect(ox, oy + tH, tH, tW);
            ctx.strokeRect(ox, oy + tH, tH, tW);
            // Centre square (ox+tH, oy+tH, tW-tH × tW-tH)  ← (1-inv_a) × (a-1) in tile units
            const cW = tW - tH;
            const cH = tW - tH;
            if (cW > 1) {
              ctx.fillStyle = ctrFill;
              ctx.fillRect(ox + tH, oy + tH, cW, cH);
              ctx.strokeRect(ox + tH, oy + tH, cW, cH);
            }
          }
        }
        break;
      }
      case "straightweave": {
        // Simple striped grid: colors alternate by column
        const bW = Math.max(8, Math.round(pW));
        const bH = Math.max(8, Math.round(pH));
        const colsB = Math.ceil(90 / bW) + 2;
        const rowsB = Math.ceil(55 / bH) + 2;

        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;

        for (let row = -1; row < rowsB; row++) {
          for (let col = -1; col < colsB; col++) {
            const isSecond = col % 2 !== 0;
            const ox = col * bW;
            const oy = row * bH;

            ctx.fillStyle = useTexture
              ? isSecond
                ? texPatDark || color2
                : texPatLight || color1
              : isSecond
                ? color2
                : color1;

            ctx.fillRect(ox, oy, bW, bH);
            ctx.strokeRect(ox, oy, bW, bH);
          }
        }
        break;
      }
      case "bookmatch": {
        // Bookmatch lays out simple tiles but mirrors the texture across axes
        const bW = Math.max(12, Math.round(pW));
        const bH = Math.max(12, Math.round(pH));
        const colsB = Math.ceil(90 / bW) + 2;
        const rowsB = Math.ceil(55 / bH) + 2;

        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;

        for (let row = -1; row < rowsB; row++) {
          for (let col = -1; col < colsB; col++) {
            const ox = col * bW;
            const oy = row * bH;

            const flipX = col % 2 !== 0;
            const flipY = row % 2 !== 0;

            ctx.save();
            ctx.translate(ox + bW / 2, oy + bH / 2);
            ctx.scale(flipX ? -1 : 1, flipY ? -1 : 1);

            ctx.fillStyle = texPatLight || color1;
            ctx.fillRect(-bW / 2, -bH / 2, bW, bH);
            ctx.restore();

            ctx.strokeRect(ox, oy, bW, bH);
          }
        }
        break;
      }
      case "hopscotch": {
        // Cell = large (L×L) + five small (S×S) where S = L/2.
        // Layout (3×3 in S units):
        //   [Large ][Large ][Sm]
        //   [Large ][Large ][Sm]
        //   [Sm    ][Sm    ][Sm]
        const L = Math.max(16, Math.round(pW));
        const S = Math.round(L / 2);
        const CELL = L + S;
        const cols = Math.ceil(90 / CELL) + 2;
        const rows = Math.ceil(55 / CELL) + 2;
        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;
        for (let row = -1; row < rows; row++) {
          for (let col = -1; col < cols; col++) {
            const ox = col * CELL;
            const oy = row * CELL;
            // Large tile (primary)
            ctx.fillStyle = useTexture ? texPatLight || color1 : color1;
            ctx.fillRect(ox, oy, L, L);
            ctx.strokeRect(ox, oy, L, L);
            // Small tiles (secondary) – right column (2 tiles) + bottom row (3 tiles)
            ctx.fillStyle = useTexture ? texPatDark || color2 : color2;
            // right-top small
            ctx.fillRect(ox + L, oy, S, S);
            ctx.strokeRect(ox + L, oy, S, S);
            // right-bottom small
            ctx.fillRect(ox + L, oy + S, S, S);
            ctx.strokeRect(ox + L, oy + S, S, S);
            // bottom-left small
            ctx.fillRect(ox, oy + L, S, S);
            ctx.strokeRect(ox, oy + L, S, S);
            // bottom-mid small
            ctx.fillRect(ox + S, oy + L, S, S);
            ctx.strokeRect(ox + S, oy + L, S, S);
            // bottom-right small (corner)
            ctx.fillRect(ox + L, oy + L, S, S);
            ctx.strokeRect(ox + L, oy + L, S, S);
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
                ? texPatDark || CONFIG.textureFallbackDark
                : texPatLight || CONFIG.textureFallbackLight
              : isSecond
                ? color2
                : color1;
            ctx.fillRect(col * pW, row * pH, pW, pH);
            ctx.strokeStyle = grout;
            ctx.strokeRect(col * pW, row * pH, pW, pH);
          }
        break;
    }

    const previewDiv = document.createElement("div");
    previewDiv.className = "tile-pattern-preview";
    previewDiv.style.backgroundImage = `url(${c.toDataURL()})`;
    div.appendChild(previewDiv);
    div.appendChild(document.createTextNode(p.name));
    preview.appendChild(div);
  });
}

export function syncPatternUI() {
  const pattern = val("tilePattern");
  const isChevron = pattern === "chevron";
  const isHerringbone = pattern === "herringbone";
  const isBasketweave = pattern === "windmill" || pattern === "straightweave";
  const isHopscotch = pattern === "hopscotch";
  const isChecker = isCheckerPattern(pattern);
  const isDual = isDualColorPattern(pattern);

  document.getElementById("normalColorRow").style.display = isDual
    ? "none"
    : "";
  document
    .getElementById("checkerColorRow")
    .classList.toggle("visible", isDual);

  const lbl1 = document.getElementById("dualColorLabel1");
  const lbl2 = document.getElementById("dualColorLabel2");
  if (lbl1 && lbl2) {
    if (isChevron) {
      lbl1.textContent = "Bras gauche";
      lbl2.textContent = "Bras droit";
    } else if (isHerringbone) {
      lbl1.textContent = "Tuile H";
      lbl2.textContent = "Tuile V";
    } else if (isBasketweave) {
      lbl1.textContent = "Grand carrelage";
      lbl2.textContent = "Carreau central";
    } else if (isHopscotch) {
      lbl1.textContent = "Grand carrelage";
      lbl2.textContent = "Petit carrelage";
    } else {
      lbl1.textContent = "Clair";
      lbl2.textContent = "Foncé";
    }
  }

  const darkGroup = document.getElementById("textureDarkGroup");
  const pairRow = document.getElementById("texturePairRow");
  const lightLbl = document.getElementById("textureLightLabel");
  const darkLbl = document.getElementById("textureDarkLabel");

  if (darkGroup) darkGroup.style.display = isDual ? "" : "none";
  if (pairRow) pairRow.classList.toggle("dual", isDual);

  if (lightLbl) {
    lightLbl.textContent = isChevron
      ? "Texture bras gauche"
      : isHerringbone
        ? "Texture tuile H"
        : isBasketweave
          ? "Texture grand carrelage"
          : isHopscotch
            ? "Texture grand carrelage"
            : isChecker
              ? "Texture claire"
              : "Texture du carrelage";
  }
  if (darkLbl) {
    darkLbl.textContent = isChevron
      ? "Texture bras droit"
      : isHerringbone
        ? "Texture tuile V"
        : isBasketweave
          ? "Texture carreau central"
          : isHopscotch
            ? "Texture petit carrelage"
            : "Texture foncée";
  }
}

export function updateFloorList() {
  // Move updateFloorList logic from app.js here
  // For now, just a stub to fix import error
}

// ── Fullscreen / kiosk detection ──
export function initFullscreenDetection() {
  function updateFullscreenClass() {
    const isFullscreen =
      !!document.fullscreenElement ||
      !!document.webkitFullscreenElement ||
      (window.innerWidth === screen.width &&
        window.innerHeight === screen.height);
    document.body.classList.toggle("fullscreen-mode", isFullscreen);
  }
  document.addEventListener("fullscreenchange", updateFullscreenClass);
  document.addEventListener("webkitfullscreenchange", updateFullscreenClass);
  window.addEventListener("resize", updateFullscreenClass);
  updateFullscreenClass();
}

// ── Side panel controls ──
export function openPanel() {
  document.getElementById("sidePanel").classList.add("open");
  document.getElementById("panelBackdrop").classList.add("visible");
}
export function closePanel() {
  document.getElementById("sidePanel").classList.remove("open");
  document.getElementById("panelBackdrop").classList.remove("visible");
}

// ── Tile mode toggle ──
export function setTileMode(mode) {
  state.tileMode = mode;
  document.body.classList.toggle("texture-mode", mode === "texture");
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

// ── Floor highlight overlay ──
export function redrawWithFloorHighlight() {
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
  // Use helper to parse CONFIG.floorHighlightColor
  const highlightRGB = hexToRgbArray(CONFIG.floorHighlightColor);
  const opacity = 0.8;
  for (let y = 0; y < state.canvas.height; y++) {
    for (let x = 0; x < state.canvas.width; x++) {
      if (state.floorMask[y]?.[x] > 0) {
        const i = (y * state.canvas.width + x) * 4;
        d[i] = d[i] * opacity + highlightRGB[0];
        d[i + 1] = d[i + 1] * opacity + highlightRGB[1];
        d[i + 2] = d[i + 2] * opacity + highlightRGB[2];
      }
    }
  }
  state.ctx.putImageData(imageData, 0, 0);
  drawFloorOutline();
}

export function drawFloorOutline() {
  state.ctx.fillStyle = CONFIG.floorHighlightColor;
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

// ── Chevron preview renderer ──
export function drawChevronPreview(
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
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, W, H);
  ctx.clip();
  const plankL = Math.max(10, Math.round(W / 3));
  const plankW = Math.max(5, Math.round(plankL / Math.max(aspectRatio, 0.5)));
  const rows = Math.ceil(H / plankW) + 2;
  const cols = Math.ceil(W / (plankL * 2)) + 2;
  ctx.translate(0, -plankW);
  for (let row = 0; row < rows; row++) {
    for (let col = -1; col < cols; col++) {
      const ox = col * plankL * 2;
      const oy = row * plankW;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.lineTo(ox, oy + plankW);
      ctx.closePath();
      ctx.fillStyle = texLight || color1;
      ctx.fill();
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
  ctx.strokeStyle = grout;
  ctx.lineWidth = 1.2;
  for (let row = 0; row < rows; row++) {
    for (let col = -1; col < cols; col++) {
      const ox = col * plankL * 2;
      const oy = row * plankW;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.lineTo(ox, oy + plankW);
      ctx.closePath();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(ox + plankL, oy + plankW);
      ctx.lineTo(ox + plankL * 2, oy);
      ctx.lineTo(ox + plankL * 2, oy + plankW);
      ctx.lineTo(ox + plankL, oy + plankW * 2);
      ctx.closePath();
      ctx.stroke();
      const numPlanks = Math.max(1, Math.ceil(plankL / plankW));
      for (let p = 1; p < numPlanks; p++) {
        const t = p / numPlanks;
        const lx = ox + t * plankL;
        const ly = oy + t * plankW;
        ctx.beginPath();
        ctx.moveTo(lx, ly);
        ctx.lineTo(lx, ly + plankW);
        ctx.stroke();
        const rx = ox + plankL + (1 - t) * plankL;
        const ry = oy + t * plankW;
        ctx.beginPath();
        ctx.moveTo(rx, ry);
        ctx.lineTo(rx, ry + plankW);
        ctx.stroke();
      }
    }
  }
  ctx.restore();
}
