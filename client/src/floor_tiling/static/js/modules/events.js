import { badge, val, syncSliderTrack } from "./helpers.js";
import {
  updateTilePreview,
  syncPatternUI,
  showStatus,
  updateTogglePreviewVisibility,
  setMarkersAutoHide,
} from "./ui.js";
import {
  handleImageUpload,
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
  document
    .getElementById("paintTextureScale")
    ?.addEventListener("input", (e) => {
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

  // ── Quick presets (primary controls; exact sliders live in Advanced) ──────
  // Highlight the preset chip that matches the current exact value (or none).
  function refreshTileSizeChips() {
    const w = val("tileWidth"),
      h = val("tileHeight");
    document.querySelectorAll("#tileSizePresets .preset-chip").forEach((c) => {
      c.classList.toggle("active", +c.dataset.w === +w && +c.dataset.h === +h);
    });
  }
  function refreshGroutChips() {
    const g = val("groutThickness");
    document.querySelectorAll("#groutPresets .preset-chip").forEach((c) => {
      c.classList.toggle("active", +c.dataset.grout === +g);
    });
  }
  // Clicking a size preset sets BOTH exact sliders, refreshes the UI, applies.
  document.querySelectorAll("#tileSizePresets .preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const ws = document.getElementById("tileWidth");
      const hs = document.getElementById("tileHeight");
      ws.value = chip.dataset.w;
      hs.value = chip.dataset.h;
      ws.dispatchEvent(new Event("input", { bubbles: true })); // badge/track/preview
      hs.dispatchEvent(new Event("input", { bubbles: true }));
      refreshTileSizeChips();
      ws.dispatchEvent(new Event("change", { bubbles: true })); // save + liveApply (once)
    });
  });
  document.querySelectorAll("#groutPresets .preset-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const gs = document.getElementById("groutThickness");
      gs.value = chip.dataset.grout;
      gs.dispatchEvent(new Event("input", { bubbles: true }));
      refreshGroutChips();
      gs.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  // Keep chip highlight in sync when the exact (advanced) sliders are used.
  document
    .getElementById("tileWidth")
    .addEventListener("input", refreshTileSizeChips);
  document
    .getElementById("tileHeight")
    .addEventListener("input", refreshTileSizeChips);
  document
    .getElementById("groutThickness")
    .addEventListener("input", refreshGroutChips);
  refreshTileSizeChips();
  refreshGroutChips();

  // ── Preset colour palettes (click a swatch → set the colour picker) ───────
  document.querySelectorAll(".color-presets").forEach((row) => {
    const inp = document.getElementById(row.dataset.target);
    if (!inp) return;
    const syncActive = () => {
      const cur = (inp.value || "").toLowerCase();
      row
        .querySelectorAll(".color-preset")
        .forEach((s) =>
          s.classList.toggle(
            "active",
            (s.dataset.color || "").toLowerCase() === cur,
          ),
        );
    };
    row.querySelectorAll(".color-preset").forEach((sw) => {
      sw.addEventListener("click", () => {
        inp.value = sw.dataset.color;
        inp.dispatchEvent(new Event("input", { bubbles: true })); // preview + save
        syncActive();
        inp.dispatchEvent(new Event("change", { bubbles: true })); // liveApply
      });
    });
    inp.addEventListener("input", syncActive); // reflect manual picker choice
    syncActive();
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
      if (
        isDualColorPattern(val("tilePattern")) &&
        !state.tileTextureDarkDataUrl
      )
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
  // Each toggle, when ON, also paints OVER its category sitting on the surface,
  // instead of leaving it unpainted. Both categories are tagged with their
  // surface id (255 = ceiling): fixtures/decor in autoMasks.objects, doors &
  // windows in autoMasks.openings.
  const paintObjects = !!document.getElementById("paintWallObjectsToggle")
    ?.checked;
  const paintOpenings = !!document.getElementById("paintWallOpeningsToggle")
    ?.checked;
  const om = paintObjects ? state.autoMasks.objects : null;
  const opm = paintOpenings ? state.autoMasks.openings : null;
  // A pixel belongs to surface `sid` if it's the surface itself or an enabled
  // extra category tagged with that surface id.
  const extra = (y, x, sid) =>
    (om && om[y] && om[y][x] === sid) || (opm && opm[y] && opm[y][x] === sid);
  for (const id of state.selectedSurfaces) {
    if (id === "floor") continue;
    pid += 1;
    if (id === "ceiling") {
      const cm = state.autoMasks.ceiling;
      if (!cm) continue;
      for (let y = 0; y < height; y++) {
        if (!cm[y]) continue;
        for (let x = 0; x < width; x++)
          if (cm[y][x] > 0 || extra(y, x, 255)) {
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
          if (wm[y][x] === wid || extra(y, x, wid)) {
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
    // Paint onto the paint-FREE base (floor-tiled result, or original) — never
    // the previous painted result — so a recolour or a smaller mask (toggling
    // wall objects off) replaces the paint instead of leaving the old one.
    const blob = state.paintBaseBlob || (await originalImageToBlob(state));
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
    // Painting over objects/openings: tell the backend to skip the matting
    // refinement, whose colour cue would otherwise keep these (non-wall-coloured)
    // regions unpainted, defeating the toggle.
    fd.append("paint_objects", paintObjects || paintOpenings ? "1" : "0");
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
    state.hasPaint = true; // paint is now applied (re-derived from paintBaseBlob)
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
      setMarkersAutoHide(true); // result shown → auto-hide markers (hover/FAB reveals)
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
    // Tiles derive from the ORIGINAL (not the accumulated result) so re-tiling
    // replaces the previous tiling; wall paint is re-chained afterwards so the
    // two edits (disjoint regions) both stay in the final composite.
    const blob = await originalImageToBlob(state);
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
    fd.append("translate_x", (val("translateX") || 0) / 200);
    fd.append("translate_y", (val("translateY") || 0) / 200);
    fd.append("rotation", val("gridRotation") || 0);
    fd.append(
      "perspective_compression",
      (val("perspectiveCompression") || 0) / 100.0,
    );
    fd.append("pattern", val("tilePattern"));
    fd.append("algorithm", val("tileAlgorithm") || "depth");
    // Auto-align grid to walls (depth algorithm) — off by default, user opt-in.
    fd.append(
      "auto_align",
      document.getElementById("autoAlignToggle")?.checked ? "1" : "0",
    );
    const _lines = state.tileAlignLines || [];
    if (_lines[0]) {
      const [[x1, y1], [x2, y2]] = _lines[0];
      fd.append("align_x1", x1);
      fd.append("align_y1", y1);
      fd.append("align_x2", x2);
      fd.append("align_y2", y2);
    }
    if (_lines[1]) {
      const [[x1, y1], [x2, y2]] = _lines[1];
      fd.append("align2_x1", x1);
      fd.append("align2_y1", y1);
      fd.append("align2_x2", x2);
      fd.append("align2_y2", y2);
    }
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
    // This tiles-only composite is the base future wall paints build on.
    state.paintBaseBlob = resultBlob;
    updateTogglePreviewVisibility();
    const img = new Image();
    img.onload = () => {
      state.editedImage = img;
      state.ctx.drawImage(img, 0, 0, state.canvas.width, state.canvas.height);
      // If walls were painted, re-apply that paint over the new tiled base so
      // both edits persist — using the SAVED paint selection (not the current
      // floor selection, which would build an empty wall mask and error).
      const paintSel = state.surfaceSelections && state.surfaceSelections.paint;
      if (state.hasPaint && paintSel && paintSel.size) {
        const tileSel = new Set(state.selectedSurfaces);
        state.selectedSurfaces = new Set(paintSel);
        applyPaintToWalls(); // builds the wall mask synchronously, then awaits
        state.selectedSurfaces = tileSel; // restore floor selection for the UI
      }
      document.getElementById("downloadFabWrap").style.display = "";
      showStatus(
        "✅ Carrelage appliqué ! Cliquez sur l'icône ⬇ pour télécharger.",
        "success",
      );
      state.isLoading = false;
      state.showingTiledResult = true;
      setMarkersAutoHide(true); // result shown → auto-hide markers (hover/FAB reveals)
    };
    img.src = state.resultUrl;
  } catch (err) {
    console.error(err);
    showStatus(`Erreur lors de l'application : ${err.message}`, "error");
  } finally {
    state.isLoading = false;
  }
}
