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

// ── Fixed neutral palette used by ALL pattern previews ───────────────────────
// These never change — previews are static schematic diagrams, not live colour previews.
const _PRV = {
  tile1: "#c8c8c8", // main tile — medium gray
  tile2: "#a0a0a0", // secondary tile — darker gray
  grout: "#f0f0f0", // grout — near-white
  bg: "#e4e4e4", // canvas background
};

function _drawPatternPreview(ctx, patternId) {
  const W = 90,
    H = 55;
  const c1 = _PRV.tile1,
    c2 = _PRV.tile2,
    gr = _PRV.grout;

  ctx.fillStyle = _PRV.bg;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = gr;
  ctx.lineWidth = 1.5;

  switch (patternId) {
    case "grid": {
      const pW = 18,
        pH = 14;
      for (let row = 0; row * pH < H + pH; row++) {
        for (let col = 0; col * pW < W + pW; col++) {
          ctx.fillStyle = c1;
          ctx.fillRect(col * pW, row * pH, pW - 1.5, pH - 1.5);
        }
      }
      break;
    }

    case "brick": {
      const pW = 28,
        pH = 13;
      for (let row = 0; row * pH < H + pH; row++) {
        const off = (row % 2) * (pW / 2);
        for (let col = -1; col * pW < W + pW; col++) {
          ctx.fillStyle = c1;
          ctx.fillRect(col * pW + off, row * pH, pW - 1.5, pH - 1.5);
        }
      }
      break;
    }

    case "herringbone": {
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, W, H);
      ctx.clip();
      ctx.translate(W / 2, H / 2);
      ctx.rotate(Math.PI / 4);
      const L = 26,
        S = 13,
        span = 110;
      ctx.lineWidth = 1;
      for (let row = -span; row < span; row += L + S) {
        for (let col = -span; col < span; col += L + S) {
          ctx.fillStyle = c1;
          ctx.fillRect(col, row, L - 1, S - 1);
          ctx.fillStyle = c2;
          ctx.fillRect(col + L, row, S - 1, L - 1);
        }
      }
      ctx.restore();
      break;
    }

    case "chevron": {
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, W, H);
      ctx.clip();
      const pL = 22,
        pW2 = 11;
      ctx.lineWidth = 1;
      for (let row = -1; row < Math.ceil(H / pW2) + 2; row++) {
        for (let col = -1; col < Math.ceil(W / (pL * 2)) + 2; col++) {
          const ox = col * pL * 2,
            oy = row * pW2;
          ctx.beginPath();
          ctx.moveTo(ox, oy);
          ctx.lineTo(ox + pL, oy + pW2);
          ctx.lineTo(ox + pL, oy + pW2 * 2);
          ctx.lineTo(ox, oy + pW2);
          ctx.closePath();
          ctx.fillStyle = c1;
          ctx.fill();
          ctx.strokeStyle = gr;
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(ox + pL, oy + pW2);
          ctx.lineTo(ox + pL * 2, oy);
          ctx.lineTo(ox + pL * 2, oy + pW2);
          ctx.lineTo(ox + pL, oy + pW2 * 2);
          ctx.closePath();
          ctx.fillStyle = c2;
          ctx.fill();
          ctx.strokeStyle = gr;
          ctx.stroke();
        }
      }
      ctx.restore();
      break;
    }

    case "windmill": {
      const tW = 20,
        tH = 10,
        cell = tW + tH;
      ctx.lineWidth = 1;
      for (let row = -1; row * cell < H + cell; row++) {
        for (let col = -1; col * cell < W + cell; col++) {
          const ox = col * cell,
            oy = row * cell;
          ctx.fillStyle = c1;
          ctx.fillRect(ox, oy, tW - 1, tH - 1); // top H
          ctx.fillRect(ox + tW, oy, tH - 1, tW - 1); // right V
          ctx.fillRect(ox + tH, oy + tW, tW - 1, tH - 1); // bottom H
          ctx.fillRect(ox, oy + tH, tH - 1, tW - 1); // left V
          const cSz = tW - tH - 1;
          if (cSz > 1) {
            ctx.fillStyle = c2;
            ctx.fillRect(ox + tH, oy + tH, cSz, cSz); // centre
          }
        }
      }
      break;
    }

    case "straightweave": {
      const pW = 18,
        pH = 14;
      ctx.lineWidth = 1;
      for (let row = 0; row * pH < H + pH; row++) {
        for (let col = 0; col * pW < W + pW; col++) {
          ctx.fillStyle = col % 2 === 0 ? c1 : c2;
          ctx.fillRect(col * pW, row * pH, pW - 1.5, pH - 1.5);
        }
      }
      break;
    }

    case "bookmatch": {
      // 2×2 mirrored tile blocks — the four tiles meet to form a diamond at centre.
      const bW = 22,
        bH = 16; // single tile size
      const cellW = bW * 2,
        cellH = bH * 2; // one full 2×2 block
      ctx.lineWidth = 1;

      for (let row = -1; row * cellH < H + cellH; row++) {
        for (let col = -1; col * cellW < W + cellW; col++) {
          const ox = col * cellW,
            oy = row * cellH;

          // Fill all four tiles with the base tile color
          ctx.fillStyle = c1;
          ctx.fillRect(ox, oy, bW - 1, bH - 1);
          ctx.fillRect(ox + bW, oy, bW - 1, bH - 1);
          ctx.fillRect(ox, oy + bH, bW - 1, bH - 1);
          ctx.fillRect(ox + bW, oy + bH, bW - 1, bH - 1);

          // Diamond formed at the centre where the 4 tiles meet
          const cx2 = ox + bW,
            cy2 = oy + bH;
          const dR = Math.min(bW, bH) * 0.72; // diamond "radius"
          ctx.beginPath();
          ctx.moveTo(cx2, cy2 - dR);
          ctx.lineTo(cx2 + dR, cy2);
          ctx.lineTo(cx2, cy2 + dR);
          ctx.lineTo(cx2 - dR, cy2);
          ctx.closePath();
          ctx.fillStyle = c2;
          ctx.fill();
        }
      }

      // Grout lines on top
      ctx.strokeStyle = gr;
      ctx.lineWidth = 1;
      for (let row = -1; row * cellH < H + cellH; row++) {
        for (let col = -1; col * cellW < W + cellW; col++) {
          const ox = col * cellW,
            oy = row * cellH;
          ctx.strokeRect(ox, oy, bW - 1, bH - 1);
          ctx.strokeRect(ox + bW, oy, bW - 1, bH - 1);
          ctx.strokeRect(ox, oy + bH, bW - 1, bH - 1);
          ctx.strokeRect(ox + bW, oy + bH, bW - 1, bH - 1);
        }
      }
      break;
    }

    case "hopscotch": {
      const L = 22,
        S = 11,
        CELL = L + S;
      ctx.lineWidth = 1;
      for (let row = -1; row * CELL < H + CELL; row++) {
        for (let col = -1; col * CELL < W + CELL; col++) {
          const ox = col * CELL,
            oy = row * CELL;
          ctx.fillStyle = c1;
          ctx.fillRect(ox, oy, L - 1, L - 1);
          ctx.fillStyle = c2;
          ctx.fillRect(ox + L, oy, S - 1, S - 1);
          ctx.fillRect(ox + L, oy + S, S - 1, S - 1);
          ctx.fillRect(ox, oy + L, S - 1, S - 1);
          ctx.fillRect(ox + S, oy + L, S - 1, S - 1);
          ctx.fillRect(ox + L, oy + L, S - 1, S - 1);
        }
      }
      break;
    }

    case "checkerboard": {
      const pW = 16,
        pH = 14;
      ctx.lineWidth = 1;
      for (let row = 0; row * pH < H + pH; row++) {
        for (let col = 0; col * pW < W + pW; col++) {
          ctx.fillStyle = (row + col) % 2 === 0 ? c1 : c2;
          ctx.fillRect(col * pW, row * pH, pW - 1.5, pH - 1.5);
        }
      }
      break;
    }
  }
}

export function updateTilePreview() {
  const preview = document.getElementById("tilePreview");
  const active = val("tilePattern");

  const patterns = [
    { id: "grid", name: "Grille" },
    { id: "brick", name: "Brique" },
    { id: "herringbone", name: "Chevrons" },
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
    div.className = "tile-option" + (p.id === active ? " selected" : "");
    div.onclick = () => {
      const patternSelect = document.getElementById("tilePattern");
      patternSelect.value = p.id;
      patternSelect.dispatchEvent(new Event("change", { bubbles: true }));
    };

    const c = document.createElement("canvas");
    c.width = 90;
    c.height = 55;
    _drawPatternPreview(c.getContext("2d"), p.id);

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
