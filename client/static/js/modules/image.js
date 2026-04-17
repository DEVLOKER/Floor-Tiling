import { state } from "./state.js";
import { CONFIG } from "./config.js";
import {
  showStatus,
  updateFloorList,
  redrawWithFloorHighlight,
  updateTogglePreviewVisibility,
  clearAutoLabels,
  drawAutoLabels,
} from "./ui.js";

export async function handleImageUpload(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      // Defensive: check canvas/context existence
      if (!state.canvas || !state.ctx) {
        state.canvas = document.getElementById("mainCanvas");
        state.ctx = state.canvas ? state.canvas.getContext("2d") : null;
      }
      if (!state.canvas || !state.ctx) return;
      const maxW = CONFIG.imageMaxWidth;
      let w = img.width,
        h = img.height;
      if (w > maxW) {
        h = Math.round((h * maxW) / w);
        w = maxW;
      }
      state.canvas.width = w;
      state.canvas.height = h;
      // Set CSS variable for aspect-ratio locking
      document.documentElement.style.setProperty("--image-ar", `${w}/${h}`);
      state.imageDimensions = { width: w, height: h };
      state.ctx.drawImage(img, 0, 0, w, h);
      state.originalImage = img;
      updateTogglePreviewVisibility();
      state.floorMask = null;
      clearAutoLabels();
      const welcomeOverlay = document.getElementById("welcomeOverlay");
      if (welcomeOverlay) welcomeOverlay.classList.add("hidden");
      updateFloorList();
      const coordsInfo = document.getElementById("coordsInfo");
      if (coordsInfo)
        coordsInfo.textContent = "Cliquez sur le sol pour le sélectionner";

      // Automatically trigger AI detection
      runAutoDetection();
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

// ── Image helpers ──
export function originalImageToBlob(state) {
  const tmp = document.createElement("canvas");
  tmp.width = state.canvas.width;
  tmp.height = state.canvas.height;
  tmp
    .getContext("2d")
    .drawImage(state.originalImage, 0, 0, tmp.width, tmp.height);
  return new Promise((resolve) =>
    tmp.toBlob(resolve, "image/jpeg", state.CONFIG?.imageJpegQuality || 0.95),
  );
}

export async function dataUrlToBlob(dataUrl) {
  const res = await fetch(dataUrl);
  return res.blob();
}

// ── Canvas click → floor segmentation ──

export async function runAutoDetection() {
  if (!state.originalImage) {
    showStatus("Veuillez d'abord importer une image", "error");
    return;
  }
  showStatus("🤖 IA en cours d'analyse…", "info");
  state.isLoading = true;
  try {
    const blob = await originalImageToBlob(state);
    const fd = new FormData();
    fd.append("image", blob, "room.jpg");

    const res = await fetch(`${CONFIG.apiUrl}/auto-detect`, {
      method: "POST",
      body: fd,
    });

    if (!res.ok) throw new Error(`Erreur API\u00A0: ${res.status}`);

    // ── Read SSE progress stream ────────────────────────────────────────
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let binaryB64 = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));

        if (payload.step === "error") {
          throw new Error(payload.message);
        }
        if (payload.step === "done") {
          binaryB64 = payload.binary;
        } else {
          // Show step progress: "🤖 (2/4) Détection sémantique…"
          showStatus(
            `🤖 [${payload.step}/${payload.total}] ${payload.message}`,
            "info",
          );
        }
      }
    }

    if (!binaryB64) throw new Error("Aucune donnée reçue du serveur");

    // ── Decode binary payload (gzipped) ─────────────────────────────────
    const compressed = Uint8Array.from(atob(binaryB64), (c) => c.charCodeAt(0));
    const decompressed = new Uint8Array(
      await new Response(
        new Blob([compressed])
          .stream()
          .pipeThrough(new DecompressionStream("gzip")),
      ).arrayBuffer(),
    );

    const view = new DataView(decompressed.buffer);
    const labelsLen = view.getUint32(0, true);
    const h = view.getUint32(4, true);
    const w = view.getUint32(8, true);
    const headerSize = 12;

    const labelsJson = new TextDecoder().decode(
      decompressed.slice(headerSize, headerSize + labelsLen),
    );
    const resultLabels = JSON.parse(labelsJson);

    const floorFlat = decompressed.slice(
      headerSize + labelsLen,
      headerSize + labelsLen + h * w,
    );
    const wallFlat = decompressed.slice(
      headerSize + labelsLen + h * w,
      headerSize + labelsLen + 2 * h * w,
    );

    // Convert flat buffers to 2D arrays (backward compat with mask[y][x])
    const floorMask2D = [];
    const wallMask2D = [];
    for (let y = 0; y < h; y++) {
      const offset = y * w;
      floorMask2D.push(Array.from(floorFlat.subarray(offset, offset + w)));
      wallMask2D.push(Array.from(wallFlat.subarray(offset, offset + w)));
    }

    const result = {
      labels: resultLabels,
      floor_mask: floorMask2D,
      wall_mask: wallMask2D,
    };

    if (!result.labels || result.labels.length === 0) {
      showStatus(
        "IA : Aucune surface détectée. Veuillez importer une autre image.",
        "error",
      );
      state.autoMasks.floor = null;
      state.autoMasks.wall = null;
      state.selectedSurfaces.clear();
      state.floorMask = null;
      const overlay = document.getElementById("markersOverlay");
      if (overlay) overlay.style.display = "none";
      return;
    }

    // Enforce that the image MUST have a floor
    const hasFloor = result.labels.some(
      (l) => l.type === "floor" || l.id === "floor",
    );
    if (!hasFloor) {
      showStatus(
        "Aucun sol détecté dans cette image. Veuillez utiliser une photo contenant un sol.",
        "error",
      );
      state.autoMasks.floor = null;
      state.autoMasks.wall = null;
      state.selectedSurfaces.clear();
      state.floorMask = null;
      const overlay = document.getElementById("markersOverlay");
      if (overlay) overlay.style.display = "none";
      return;
    }

    state.autoMasks.floor = result.floor_mask;
    state.autoMasks.wall = result.wall_mask;

    // Reset selection and default to floor
    state.selectedSurfaces.clear();
    state.selectedSurfaces.add("floor");
    updateCombinedMask();

    // Safety: individual try-catch blocks for rendering
    try {
      drawAutoLabels(result.labels, (id) => {
        if (state.selectedSurfaces.has(id)) {
          state.selectedSurfaces.delete(id);
        } else {
          state.selectedSurfaces.add(id);
        }
        updateCombinedMask();
        redrawWithFloorHighlight();
        // Update UI markers active state
        const markers = document.querySelectorAll(".surface-marker-group");
        markers.forEach((m) => {
          const mId = m.getAttribute("data-id");
          if (state.selectedSurfaces.has(mId)) {
            m.classList.add("active");
          } else {
            m.classList.remove("active");
          }
        });
      });
    } catch (err) {
      console.error("❌ drawAutoLabels fail:", err);
    }

    try {
      redrawWithFloorHighlight();
    } catch (err) {
      console.error("❌ redrawWithFloorHighlight fail:", err);
    }
    updateFloorList();

    showStatus("D\u00E9tection automatique termin\u00E9e\u00A0!", "success");
  } catch (err) {
    console.error(err);
    showStatus(`Erreur IA\u00A0: ${err.message}`, "error");
  } finally {
    state.isLoading = false;
  }
}

export function updateCombinedMask() {
  if (!state.canvas) return;
  const height = state.canvas.height;
  const width = state.canvas.width;

  if (state.selectedSurfaces.size === 0) {
    state.floorMask = null;
    return;
  }

  // Merging all selected masks into a single active mask
  // We use regular arrays to ensure perfect JSON serialization for the backend
  const combined = Array.from({ length: height }, () =>
    new Array(width).fill(0),
  );

  state.selectedSurfaces.forEach((id) => {
    if (id === "floor") {
      const mask = state.autoMasks.floor;
      if (!mask) return;
      for (let y = 0; y < height; y++) {
        if (!mask[y]) continue;
        for (let x = 0; x < width; x++) {
          if (mask[y][x] > 0) combined[y][x] = 1;
        }
      }
    } else {
      const mask = state.autoMasks.wall; // Use the labeled wall mask
      if (!mask) return;
      const wallId = parseInt(id);
      for (let y = 0; y < height; y++) {
        if (!mask[y]) continue;
        for (let x = 0; x < width; x++) {
          if (mask[y][x] === wallId) combined[y][x] = 1;
        }
      }
    }
  });

  state.floorMask = combined;
}
