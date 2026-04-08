import { state } from "./state.js";
import { CONFIG } from "./config.js";
import {
  showStatus,
  updateFloorList,
  redrawWithFloorHighlight,
  updateTogglePreviewVisibility,
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
      state.imageDimensions = { width: w, height: h };
      state.ctx.drawImage(img, 0, 0, w, h);
      state.originalImage = img;
      updateTogglePreviewVisibility();
      state.floorMask = null;
      const welcomeOverlay = document.getElementById("welcomeOverlay");
      if (welcomeOverlay) welcomeOverlay.classList.add("hidden");
      updateFloorList();
      const coordsInfo = document.getElementById("coordsInfo");
      if (coordsInfo)
        coordsInfo.textContent = "Cliquez sur le sol pour le sélectionner";
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
export async function handleCanvasClick(event) {
  if (!state.originalImage) {
    showStatus("Veuillez d'abord importer une image", "error");
    return;
  }
  const rect = state.canvas.getBoundingClientRect();
  const scaleX = state.canvas.width / rect.width;
  const scaleY = state.canvas.height / rect.height;
  const clickX = Math.round((event.clientX - rect.left) * scaleX);
  const clickY = Math.round((event.clientY - rect.top) * scaleY);
  document.getElementById("coordsInfo").textContent =
    `Sélectionné (${clickX}, ${clickY}) — Traitement…`;
  state.isLoading = true;
  showStatus("🎯 Détection du sol…", "info");
  try {
    const blob = await originalImageToBlob(state);
    const fd = new FormData();
    fd.append("image", blob, "room.jpg");
    fd.append("click_x", clickX);
    fd.append("click_y", clickY);
    const res = await fetch(`${CONFIG.apiUrl}/segment-floor`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(`Erreur API : ${res.status}`);
    const result = await res.json();
    state.floorMask = result.mask;
    state.floorConfidence = result.score;
    redrawWithFloorHighlight();
    updateFloorList();
    document.getElementById("coordsInfo").textContent =
      `✅ Sol sélectionné ! (confiance : ${(result.score * 100).toFixed(1)}%)`;
    showStatus(
      "Sol sélectionné ! Ajustez les paramètres et appliquez le carrelage.",
      "success",
    );
  } catch (err) {
    console.error(err);
    showStatus(`Erreur : ${err.message}", "error`);
    document.getElementById("coordsInfo").textContent =
      "❌ Échec — essayez de cliquer sur une autre zone.";
  } finally {
    state.isLoading = false;
  }
}
