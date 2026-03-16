import { state } from "./state.js";
import { CONFIG } from "./config.js";
import { val } from "./helpers.js";
import { isCheckerPattern, isDualColorPattern } from "./patterns.js";

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
    { id: "diagonal", name: "Diagonale" },
    { id: "brick", name: "Brique" },
    { id: "herringbone", name: "Chevrons classiques" },
    { id: "chevron", name: "Chevron ∧" },
    { id: "basketweave", name: "Natte" },
    { id: "versailles", name: "Versailles" },
    { id: "checkerboard", name: "Damier" },
    { id: "diagonal_checkerboard", name: "Damier diagonal ◇" },
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
      case "basketweave": {
        const bW = Math.max(14, Math.round(pW));
        const bH = Math.max(14, Math.round(pH));
        const colsB = Math.ceil(90 / bW) + 2;
        const rowsB = Math.ceil(55 / bH) + 2;
        for (let row = -1; row < rowsB; row++) {
          for (let col = -1; col < colsB; col++) {
            const isH = (((row + col) % 2) + 2) % 2 === 0;
            const ox = col * bW,
              oy = row * bH;
            ctx.fillStyle = useTexture
              ? isH
                ? texPatLight || color1
                : texPatDark || color2
              : isH
                ? color1
                : color2;
            ctx.fillRect(ox, oy, bW, bH);
          }
        }
        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;
        for (let row = -1; row < rowsB; row++) {
          for (let col = -1; col < colsB; col++) {
            const isH = (((row + col) % 2) + 2) % 2 === 0;
            const ox = col * bW,
              oy = row * bH;
            ctx.strokeRect(ox, oy, bW, bH);
            ctx.beginPath();
            if (isH) {
              ctx.moveTo(ox, oy + bH / 2);
              ctx.lineTo(ox + bW, oy + bH / 2);
            } else {
              ctx.moveTo(ox + bW / 2, oy);
              ctx.lineTo(ox + bW / 2, oy + bH);
            }
            ctx.stroke();
          }
        }
        break;
      }
      case "versailles": {
        const CELL = 90 / 2.5;
        const u1 = CELL / 4;
        const v1 = CELL / 4;
        const cols = Math.ceil(90 / CELL) + 2;
        const rows = Math.ceil(55 / CELL) + 2;
        for (let row = -1; row < rows; row++) {
          for (let col = -1; col < cols; col++) {
            const ox = col * CELL;
            const oy = row * CELL;
            const tiles = [
              { x: ox + u1, y: oy + v1, w: u1 * 2, h: v1 * 2, second: false },
              { x: ox + u1, y: oy, w: u1 * 2, h: v1, second: true },
              { x: ox + u1, y: oy + v1 * 3, w: u1 * 2, h: v1, second: true },
              { x: ox, y: oy + v1, w: u1, h: v1 * 2, second: true },
              { x: ox + u1 * 3, y: oy + v1, w: u1, h: v1 * 2, second: true },
              { x: ox, y: oy, w: u1, h: v1, second: true },
              { x: ox + u1 * 3, y: oy, w: u1, h: v1, second: true },
              { x: ox, y: oy + v1 * 3, w: u1, h: v1, second: true },
              { x: ox + u1 * 3, y: oy + v1 * 3, w: u1, h: v1, second: true },
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
            });
          }
        }
        ctx.strokeStyle = grout;
        ctx.lineWidth = 1.0;
        for (let row = -1; row < rows; row++) {
          for (let col = -1; col < cols; col++) {
            const ox = col * CELL;
            const oy = row * CELL;
            const tiles = [
              { x: ox + u1, y: oy + v1, w: u1 * 2, h: v1 * 2 },
              { x: ox + u1, y: oy, w: u1 * 2, h: v1 },
              { x: ox + u1, y: oy + v1 * 3, w: u1 * 2, h: v1 },
              { x: ox, y: oy + v1, w: u1, h: v1 * 2 },
              { x: ox + u1 * 3, y: oy + v1, w: u1, h: v1 * 2 },
              { x: ox, y: oy, w: u1, h: v1 },
              { x: ox + u1 * 3, y: oy, w: u1, h: v1 },
              { x: ox, y: oy + v1 * 3, w: u1, h: v1 },
              { x: ox + u1 * 3, y: oy + v1 * 3, w: u1, h: v1 },
            ];
            tiles.forEach(({ x, y, w, h }) => ctx.strokeRect(x, y, w, h));
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
                ? texPatDark || CONFIG.textureFallbackDark
                : texPatLight || CONFIG.textureFallbackLight
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

export function syncPatternUI() {
  const pattern = val("tilePattern");
  const isChevron = pattern === "chevron";
  const isBasketweave = pattern === "basketweave";
  const isVersionailles = pattern === "versailles";
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
    } else if (isBasketweave) {
      lbl1.textContent = "Horizontal";
      lbl2.textContent = "Vertical";
    } else if (isVersionailles) {
      lbl1.textContent = "Grand / Large";
      lbl2.textContent = "Haut / Petit";
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
      : isBasketweave
        ? "Texture bundle H"
        : isChecker
          ? "Texture claire"
          : "Texture du carrelage";
  }
  if (darkLbl) {
    darkLbl.textContent = isChevron
      ? "Texture bras droit"
      : isBasketweave
        ? "Texture bundle V"
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
