import { badge, val } from "./helpers.js";
import {
  updateTilePreview,
  syncPatternUI,
  updateFloorList,
  showStatus,
  updateTogglePreviewVisibility,
  drawAutoLabels,
  clearAutoLabels,
  redrawWithFloorHighlight,
} from "./ui.js";
import {
  handleImageUpload,
  originalImageToBlob,
  dataUrlToBlob,
  runAutoDetection,
} from "./image.js";
import { state } from "./state.js";
import { isDualColorPattern } from "./patterns.js";
import { CONFIG } from "./config.js";

export function initEventListeners() {
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


  document.getElementById("tileWidth").addEventListener("input", (e) => {
    badge("tileWidthValue", e.target.value + " cm");
    updateTilePreview();
  });
  document.getElementById("tileHeight").addEventListener("input", (e) => {
    badge("tileHeightValue", e.target.value + " cm");
    updateTilePreview();
  });
  document.getElementById("gridRotation").addEventListener("input", (e) => {
    badge("gridRotationValue", e.target.value + "°");
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

  // ── FAB: download & toggle preview ──
  const downloadBtn = document.getElementById("downloadBtn");
  if (downloadBtn) downloadBtn.addEventListener("click", downloadResultImage);

  const togglePreviewBtn = document.getElementById("togglePreviewBtn");
  if (togglePreviewBtn)
    togglePreviewBtn.addEventListener("click", togglePreview);

  // Initial FAB visibility
  updateTogglePreviewVisibility();
}

// ── Download button handler ──
export function downloadResultImage() {
  if (state.resultUrl) {
    const a = document.createElement("a");
    a.href = state.resultUrl;
    a.download = "carrelage_resultat.jpg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

// ── Toggle preview handler ──
export function togglePreview() {
  if (!state.originalImage || !state.resultUrl) return;
  if (!state.ctx) return;
  if (state.showingTiledResult) {
    // Show original
    state.ctx.drawImage(
      state.originalImage,
      0,
      0,
      state.canvas.width,
      state.canvas.height,
    );
  } else {
    // Show tiled result
    const img = new Image();
    img.onload = () => {
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
    };
    img.src = state.resultUrl;
  }
  state.showingTiledResult = !state.showingTiledResult;
}

// ── Apply tiles ──
export async function applyTilesToFloor() {
  if (!state.originalImage) {
    showStatus("Veuillez d'abord importer une image", "error");
    return;
  }
  if (!state.floorMask) {
    showStatus("Veuillez d'abord sélectionner un sol", "error");
    return;
  }
  if (state.tileMode === "texture" && !state.tileTextureDataUrl) {
    showStatus("Veuillez d'abord importer une image de texture", "error");
    return;
  }
  const isDual = isDualColorPattern(val("tilePattern"));
  if (state.tileMode === "texture" && isDual && !state.tileTextureDarkDataUrl) {
    showStatus("Veuillez importer une deuxième texture pour ce motif", "error");
    return;
  }
  showStatus("🎨 Application du carrelage…", "info");
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
    const blob = await originalImageToBlob(state);
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
    fd.append("rotation", val("gridRotation") || 0);
    fd.append("pattern", val("tilePattern"));
    if (state.tileMode === "texture" && state.tileTextureDataUrl) {
      fd.append(
        "tile_texture",
        await dataUrlToBlob(state.tileTextureDataUrl),
        "texture.jpg",
      );
      if (isDual && state.tileTextureDarkDataUrl) {
        fd.append(
          "tile_texture2",
          await dataUrlToBlob(state.tileTextureDarkDataUrl),
          "texture2.jpg",
        );
      }
    }
    const res = await fetch(`${CONFIG.apiUrl}/apply-tiles`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok)
      throw new Error(`Échec de l'application du carrelage : ${res.status}`);
    const resultBlob = await res.blob();
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(resultBlob);
    updateTogglePreviewVisibility();
    const img = new Image();
    img.onload = () => {
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
      document.getElementById("downloadFabWrap").style.display = "";
      showStatus(
        "✅ Carrelage appliqué ! Cliquez sur l'icône ⬇ pour télécharger.",
        "success",
      );
      state.isLoading = false;
      state.showingTiledResult = true;
    };
    img.src = state.resultUrl;
  } catch (err) {
    console.error(err);
    showStatus(`Erreur lors de l'application : ${err.message}`, "error");
  } finally {
    state.isLoading = false;
  }
}

