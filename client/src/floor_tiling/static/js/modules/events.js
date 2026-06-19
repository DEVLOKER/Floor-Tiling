import { badge, val, syncSliderTrack } from "./helpers.js";
import {
  updateTilePreview,
  syncPatternUI,
  showStatus,
  updateTogglePreviewVisibility,
} from "./ui.js";
import {
  handleImageUpload,
  baseImageToBlob,
  originalImageToBlob,
  dataUrlToBlob,
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

  // --- Pattern-based tile ratio enforcement ---
  function getPatternTileRatio(pattern) {
    switch (pattern) {
      case "windmill":
        return { type: "ratio", ratio: 2 };
      case "herringbone":
        return { type: "ratio", ratio: 3 };
      case "chevron":
        return { type: "square" };
      case "hopscotch":
        return { type: "square" };
      case "checkerboard":
      case "grid":
        return { type: "square" };
      case "brick":
        return { type: "ratio", ratio: 2 };
      default:
        return null;
    }
  }

  function enforcePatternTileRatio(pattern, changed) {
    const wSlider = document.getElementById("tileWidth");
    const hSlider = document.getElementById("tileHeight");
    if (!wSlider || !hSlider) return;
    const minW = parseInt(wSlider.min || 10);
    const maxW = parseInt(wSlider.max || 200);
    const minH = parseInt(hSlider.min || 10);
    const maxH = parseInt(hSlider.max || 200);
    let width = parseInt(wSlider.value);
    let height = parseInt(hSlider.value);
    const constraint = getPatternTileRatio(pattern);
    if (!constraint) return;
    if (constraint.type === "square") {
      if (changed === "width") {
        height = Math.max(minH, Math.min(maxH, width));
        hSlider.value = height;
        badge("tileHeightValue", height + " cm");
        hSlider.dispatchEvent(new Event("input", { bubbles: true }));
      } else if (changed === "height") {
        width = Math.max(minW, Math.min(maxW, height));
        wSlider.value = width;
        badge("tileWidthValue", width + " cm");
        wSlider.dispatchEvent(new Event("input", { bubbles: true }));
      }
    } else if (constraint.type === "ratio") {
      if (changed === "width") {
        height = Math.max(
          minH,
          Math.min(maxH, Math.round(width / constraint.ratio / 5) * 5),
        );
        hSlider.value = height;
        badge("tileHeightValue", height + " cm");
        hSlider.dispatchEvent(new Event("input", { bubbles: true }));
      } else if (changed === "height") {
        width = Math.max(
          minW,
          Math.min(maxW, Math.round((height * constraint.ratio) / 5) * 5),
        );
        wSlider.value = width;
        badge("tileWidthValue", width + " cm");
        wSlider.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  }

  document.getElementById("tileWidth").addEventListener("input", (e) => {
    badge("tileWidthValue", e.target.value + " cm");
    syncSliderTrack(e.target);
    // const pattern = val("tilePattern");
    // enforcePatternTileRatio(pattern, "width");
    updateTilePreview();
  });
  document.getElementById("tileHeight").addEventListener("input", (e) => {
    badge("tileHeightValue", e.target.value + " cm");
    syncSliderTrack(e.target);
    // const pattern = val("tilePattern");
    // enforcePatternTileRatio(pattern, "height");
    updateTilePreview();
  });
  document.getElementById("gridRotation").addEventListener("input", (e) => {
    badge("gridRotationValue", e.target.value + "°");
    syncSliderTrack(e.target);
  });
  document
    .getElementById("perspectiveCompression")
    .addEventListener("input", (e) => {
      badge("perspectiveCompressionValue", e.target.value + "%");
      syncSliderTrack(e.target);
    });
  document.getElementById("translateX").addEventListener("input", (e) => {
    badge("translateXValue", e.target.value);
    syncSliderTrack(e.target);
  });
  document.getElementById("translateY").addEventListener("input", (e) => {
    badge("translateYValue", e.target.value);
    syncSliderTrack(e.target);
  });
  document.getElementById("paintTextureScale")?.addEventListener("input", (e) => {
    badge("paintTextureScaleValue", e.target.value + " cm");
    syncSliderTrack(e.target);
  });
  [
    ["wallPaintOpacity", "wallPaintOpacityValue"],
    ["wallPaintLight", "wallPaintLightValue"],
    ["wallPaintSat", "wallPaintSatValue"],
  ].forEach(([id, badgeId]) => {
    document.getElementById(id)?.addEventListener("input", (e) => {
      badge(badgeId, e.target.value + " %");
      syncSliderTrack(e.target);
    });
  });

  // Live-apply when a texture is (re)loaded — fired from texture.js.
  document.addEventListener("liveapply", liveApply);

  document.getElementById("groutThickness").addEventListener("input", (e) => {
    badge("groutValue", e.target.value + " px");
    syncSliderTrack(e.target);
    document
      .getElementById("hintGrout")
      .style.setProperty("--th", e.target.value + "px");
  });

  document.getElementById("tilePattern").addEventListener("change", () => {
    syncPatternUI();
    const pattern = val("tilePattern");
    enforcePatternTileRatio(pattern, "width");
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

// ── Footer CTA dispatcher (depends on the open activity) ──
export function applyActiveAction() {
  if (state.activeMode === "paint") return applyPaintToWalls();
  return applyTilesToFloor();
}

// ── Live apply: re-render on any control change, for the active activity ──
// Silently skips when not ready (no selection, missing texture, mid-render) so
// it never spams errors or stacks calls. Called on `change` (mouse release), so
// it doesn't fire continuously during a drag.
export function liveApply() {
  if (!state.liveApply) return; // user turned live preview off → apply via button only
  if (!state.originalImage || state.isLoading || !state.floorMask) return;
  if (state.activeMode === "paint") {
    if (state.paintMode === "texture" && !state.paintTextureDataUrl) return;
    applyPaintToWalls();
  } else {
    if (state.tileMode === "texture") {
      if (!state.tileTextureDataUrl) return;
      if (isDualColorPattern(val("tilePattern")) && !state.tileTextureDarkDataUrl)
        return;
    }
    applyTilesToFloor();
  }
}

// ── Apply paint (walls / ceiling) ──
export async function applyPaintToWalls() {
  if (!state.originalImage) {
    showStatus("Veuillez d'abord importer une image", "error");
    return;
  }
  // In paint mode the combined mask holds exactly the selected paint surfaces
  // (walls and/or ceiling) — the floor can't be selected in this mode.
  if (!state.floorMask) {
    showStatus("Veuillez d'abord sélectionner un mur ou le plafond", "error");
    return;
  }
  if (state.paintMode === "texture" && !state.paintTextureDataUrl) {
    showStatus("Veuillez d'abord importer une texture de peinture", "error");
    return;
  }

  // Build a LABELED mask: each selected surface (wall plane / ceiling) gets a
  // distinct id so the backend can map textures per plane (perspective + corners).
  const width = state.canvas.width;
  const height = state.canvas.height;
  const maskData = new Uint8Array(width * height);
  let pid = 0;
  let total = 0;
  for (const id of state.selectedSurfaces) {
    if (id === "floor") continue;
    pid += 1;
    if (id === "ceiling") {
      const cm = state.autoMasks.ceiling;
      if (!cm) continue;
      for (let y = 0; y < height; y++) {
        if (!cm[y]) continue;
        for (let x = 0; x < width; x++)
          if (cm[y][x] > 0) {
            maskData[y * width + x] = pid;
            total++;
          }
      }
    } else {
      const wm = state.autoMasks.wall;
      if (!wm) continue;
      const wid = parseInt(id);
      for (let y = 0; y < height; y++) {
        if (!wm[y]) continue;
        for (let x = 0; x < width; x++)
          if (wm[y][x] === wid) {
            maskData[y * width + x] = pid;
            total++;
          }
      }
    }
  }
  if (total === 0) {
    showStatus("Veuillez d'abord sélectionner un mur ou le plafond", "error");
    return;
  }

  showStatus("🎨 Application de la peinture…", "info");
  state.isLoading = true;
  try {
    const blob = await baseImageToBlob(state);
    const sourceBlob = await originalImageToBlob(state);
    const maskBlob = new Blob([maskData], { type: "application/octet-stream" });
    const fd = new FormData();
    fd.append("image", blob, "room.jpg");
    fd.append("source", sourceBlob, "source.jpg");
    fd.append("mask", maskBlob, "mask.bin");
    fd.append("paint_color", val("wallPaintColor"));
    fd.append("finish", val("wallPaintFinish") || "matte");
    fd.append("opacity", (val("wallPaintOpacity") || 100) / 100.0);
    fd.append("light_strength", (val("wallPaintLight") || 100) / 100.0);
    fd.append("saturation", (val("wallPaintSat") || 86) / 100.0);
    if (state.paintMode === "texture" && state.paintTextureDataUrl) {
      fd.append(
        "paint_texture",
        await dataUrlToBlob(state.paintTextureDataUrl),
        "paint_texture.jpg",
      );
      // cm → metres for the real-world texture repeat size
      fd.append("texture_scale", (val("paintTextureScale") || 130) / 100.0);
    }
    const res = await fetch(`${CONFIG.apiUrl}/apply-paint`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok)
      throw new Error(`Échec de l'application de la peinture : ${res.status}`);
    const resultBlob = await res.blob();
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(resultBlob);
    updateTogglePreviewVisibility();
    const img = new Image();
    img.onload = () => {
      state.editedImage = img;
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
      document.getElementById("downloadFabWrap").style.display = "";
      showStatus(
        "✅ Peinture appliquée ! Cliquez sur l'icône ⬇ pour télécharger.",
        "success",
      );
      state.isLoading = false;
      state.showingTiledResult = true;
    };
    img.src = state.resultUrl;
  } catch (err) {
    console.error(err);
    showStatus(`Erreur lors de l'application : ${err.message}`, "error");
  } finally {
    state.isLoading = false;
  }
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
    const blob = await baseImageToBlob(state);
    const sourceBlob = await originalImageToBlob(state);
    const maskData = new Uint8Array(state.floorMask.flat());
    const maskBlob = new Blob([maskData], { type: "application/octet-stream" });
    const fd = new FormData();
    fd.append("image", blob, "room.jpg");
    fd.append("source", sourceBlob, "source.jpg");
    fd.append("mask", maskBlob, "mask.bin");
    fd.append("tile_width", val("tileWidth"));
    fd.append("tile_height", val("tileHeight"));
    fd.append("tile_color", tileColor);
    fd.append("tile_color2", tileColor2);
    fd.append("grout_color", groutColor);
    fd.append("grout_thickness", val("groutThickness"));
    fd.append("translate_x", val("translateX") || 0);
    fd.append("translate_y", val("translateY") || 0);
    fd.append("rotation", val("gridRotation") || 0);
    fd.append(
      "perspective_compression",
      (val("perspectiveCompression") || 0) / 100.0,
    );
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
      state.editedImage = img;
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
