import { state } from "./state.js";
import { CONFIG } from "./config.js";
import {
  showStatus,
  updateFloorList,
  redrawWithFloorHighlight,
  updateTogglePreviewVisibility,
  invalidateCachedResult,
  clearAutoLabels,
  drawAutoLabels,
  updateFooterHint,
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
      // Invalidate any cached result from previous image
      invalidateCachedResult();
      updateTogglePreviewVisibility();
      state.floorMask = null;
      state.paintBaseBlob = null; // new image → drop the paint base / paint state
      state.hasPaint = false;
      state.tileAlignLines = []; // alignment is per-image (image coords)
      clearAutoLabels();
      const welcomeOverlay = document.getElementById("welcomeOverlay");
      if (welcomeOverlay) welcomeOverlay.classList.add("hidden");
      updateFloorList();
      const coordsInfo = document.getElementById("coordsInfo");
      if (coordsInfo)
        coordsInfo.textContent = "Cliquez sur le sol pour le sélectionner";

      // Reset wall detection state for new image
      state.wallDetectionDone = false;
      state.wallDetectionPending = false;
      state.autoMasks.wall = null;
      state.autoMasks.ceiling = null;
      state.autoMasks.objects = null;
      state.autoMasks.openings = null;

      // Phase 1: fast floor-only detection
      runFloorDetection();
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

// Returns the image edits should build upon: the accumulated composite if one
// exists (so floor tiles + wall paint stack into one result), otherwise the
// pristine original.
export async function baseImageToBlob(state) {
  if (state.resultUrl) {
    try {
      const res = await fetch(state.resultUrl);
      return await res.blob();
    } catch (e) {
      /* fall back to original */
    }
  }
  return originalImageToBlob(state);
}

// ── Detection helpers ─────────────────────────────────────────────────────

/** Read an SSE stream to completion, returning the final base64 payload + mode. */
async function _readSseStream(response) {
  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let binaryB64 = null;
  let mode = "all";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.step === "error") throw new Error(payload.message);
      if (payload.step === "done") {
        binaryB64 = payload.binary;
        mode = payload.mode || "all";
      } else {
        showStatus(`🤖 [${payload.step}/${payload.total}] ${payload.message}`, "info");
      }
    }
  }
  if (!binaryB64) throw new Error("Aucune donnée reçue du serveur");
  return { binaryB64, mode };
}

/** Decompress a gzipped base64 payload into parsed masks + labels. */
async function _decodeBinaryPayload(binaryB64) {
  const compressed = Uint8Array.from(atob(binaryB64), (c) => c.charCodeAt(0));
  const decompressed = new Uint8Array(
    await new Response(
      new Blob([compressed]).stream().pipeThrough(new DecompressionStream("gzip")),
    ).arrayBuffer(),
  );

  const view       = new DataView(decompressed.buffer);
  const labelsLen  = view.getUint32(0, true);
  const h          = view.getUint32(4, true);
  const w          = view.getUint32(8, true);
  const headerSize = 12;
  const base       = headerSize + labelsLen;

  const labels = JSON.parse(
    new TextDecoder().decode(decompressed.slice(headerSize, headerSize + labelsLen))
  );

  const flat2d = (flat) => {
    const out = [];
    for (let y = 0; y < h; y++) {
      const off = y * w;
      out.push(Array.from(flat.subarray(off, off + w)));
    }
    return out;
  };

  const hasObjects  = decompressed.length >= base + 4 * h * w;
  const hasOpenings = decompressed.length >= base + 5 * h * w;

  return {
    labels,
    floor_mask:   flat2d(decompressed.slice(base,         base + h * w)),
    wall_mask:    flat2d(decompressed.slice(base + h*w,   base + 2*h*w)),
    ceiling_mask: flat2d(decompressed.slice(base + 2*h*w, base + 3*h*w)),
    object_mask:  hasObjects  ? flat2d(decompressed.slice(base + 3*h*w, base + 4*h*w)) : null,
    opening_mask: hasOpenings ? flat2d(decompressed.slice(base + 4*h*w, base + 5*h*w)) : null,
  };
}

// ── Phase 1: floor-only detection (fast, called on image upload) ─────────────

export async function runFloorDetection() {
  if (!state.originalImage) {
    showStatus("Veuillez d'abord importer une image", "error");
    return;
  }
  showStatus("🤖 Détection du sol en cours…", "info");
  state.isLoading = true;
  try {
    const blob = await originalImageToBlob(state);
    const fd   = new FormData();
    fd.append("image", blob, "room.jpg");

    const res = await fetch(`${CONFIG.apiUrl}/detect-floor`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`Erreur API : ${res.status}`);

    const { binaryB64 } = await _readSseStream(res);
    const result        = await _decodeBinaryPayload(binaryB64);

    if (!result.labels?.length || !result.labels.some((l) => l.type === "floor")) {
      showStatus("Aucun sol détecté. Veuillez utiliser une photo contenant un sol.", "error");
      state.autoMasks.floor = null;
      state.selectedSurfaces.clear();
      state.floorMask = null;
      return;
    }

    state.autoMasks.floor = result.floor_mask;

    state.selectedSurfaces.clear();
    state.surfaceSelections = { tile: null, paint: null };
    state.activeMode = null;

    drawAutoLabels(result.labels, toggleSurface);
    setActiveMode("tile");
    updateFloorList();
    showStatus("Sol détecté — prêt à carreler !", "success");
  } catch (err) {
    console.error(err);
    showStatus(`Erreur IA : ${err.message}`, "error");
  } finally {
    state.isLoading = false;
  }
}

// ── Phase 2: wall detection (lazy, called on first paint-tab switch) ──────────

export async function runWallDetection() {
  if (!state.originalImage) return;
  if (state.wallDetectionDone || state.wallDetectionPending) return;

  state.wallDetectionPending = true;
  showStatus("🤖 Analyse des murs en cours…", "info");
  try {
    const blob = await originalImageToBlob(state);
    const fd   = new FormData();
    fd.append("image", blob, "room.jpg");

    const res = await fetch(`${CONFIG.apiUrl}/detect-walls`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`Erreur API : ${res.status}`);

    const { binaryB64 } = await _readSseStream(res);
    const result        = await _decodeBinaryPayload(binaryB64);

    state.autoMasks.wall     = result.wall_mask;
    state.autoMasks.ceiling  = result.ceiling_mask;
    state.autoMasks.objects  = result.object_mask;
    state.autoMasks.openings = result.opening_mask;
    state.wallDetectionDone  = true;

    // Merge wall/ceiling labels with existing floor labels
    const wallLabels  = (result.labels || []).filter((l) => l.type === "wall" || l.type === "ceiling");
    const floorLabels = (state.currentLabels || []).filter((l) => l.type === "floor");
    drawAutoLabels([...floorLabels, ...wallLabels], toggleSurface);

    redrawWithFloorHighlight();
    updateFooterHint();

    const nWalls = wallLabels.filter((l) => l.type === "wall").length;
    const hasCeil = wallLabels.some((l) => l.type === "ceiling");
    showStatus(
      `Murs détectés : ${nWalls} plan(s)${hasCeil ? " + plafond" : ""} — cliquez pour sélectionner.`,
      "success",
    );
  } catch (err) {
    console.error(err);
    showStatus(`Erreur détection murs : ${err.message}`, "error");
    state.wallDetectionDone = false;
  } finally {
    state.wallDetectionPending = false;
  }
}

// ── Legacy: combined floor + wall detection (backward-compat) ────────────────

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

    const base = headerSize + labelsLen;
    const floorFlat = decompressed.slice(base, base + h * w);
    const wallFlat = decompressed.slice(base + h * w, base + 2 * h * w);
    const ceilingFlat = decompressed.slice(base + 2 * h * w, base + 3 * h * w);
    // 4th/5th channels — objects (fixtures/decor) and openings (doors&windows),
    // each labelled by the surface they sit on. Only in newer payloads; guard on
    // the buffer length.
    const hasObjects = decompressed.length >= base + 4 * h * w;
    const hasOpenings = decompressed.length >= base + 5 * h * w;
    const objectFlat = hasObjects
      ? decompressed.slice(base + 3 * h * w, base + 4 * h * w)
      : null;
    const openingFlat = hasOpenings
      ? decompressed.slice(base + 4 * h * w, base + 5 * h * w)
      : null;

    // Convert flat buffers to 2D arrays (backward compat with mask[y][x])
    const floorMask2D = [];
    const wallMask2D = [];
    const ceilingMask2D = [];
    const objectMask2D = hasObjects ? [] : null;
    const openingMask2D = hasOpenings ? [] : null;
    for (let y = 0; y < h; y++) {
      const offset = y * w;
      floorMask2D.push(Array.from(floorFlat.subarray(offset, offset + w)));
      wallMask2D.push(Array.from(wallFlat.subarray(offset, offset + w)));
      ceilingMask2D.push(Array.from(ceilingFlat.subarray(offset, offset + w)));
      if (hasObjects)
        objectMask2D.push(Array.from(objectFlat.subarray(offset, offset + w)));
      if (hasOpenings)
        openingMask2D.push(Array.from(openingFlat.subarray(offset, offset + w)));
    }

    const result = {
      labels: resultLabels,
      floor_mask: floorMask2D,
      wall_mask: wallMask2D,
      ceiling_mask: ceilingMask2D,
      object_mask: objectMask2D,
      opening_mask: openingMask2D,
    };

    if (!result.labels || result.labels.length === 0) {
      showStatus(
        "IA : Aucune surface détectée. Veuillez importer une autre image.",
        "error",
      );
      state.autoMasks.floor = null;
      state.autoMasks.wall = null;
      state.autoMasks.ceiling = null;
      state.autoMasks.objects = null;
      state.autoMasks.openings = null;
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
      state.autoMasks.ceiling = null;
      state.autoMasks.objects = null;
      state.autoMasks.openings = null;
      state.selectedSurfaces.clear();
      state.floorMask = null;
      const overlay = document.getElementById("markersOverlay");
      if (overlay) overlay.style.display = "none";
      return;
    }

    state.autoMasks.floor = result.floor_mask;
    state.autoMasks.wall = result.wall_mask;
    state.autoMasks.ceiling = result.ceiling_mask;
    state.autoMasks.objects = result.object_mask;
    state.autoMasks.openings = result.opening_mask;

    // Fresh image → reset to the default: floor auto-selected for tiling,
    // walls & ceiling deselected. We clear the live selection and the per-tab
    // memory, and null out activeMode so setActiveMode doesn't save the
    // previous image's (now stale) selection.
    state.selectedSurfaces.clear();
    state.surfaceSelections = { tile: null, paint: null };
    state.activeMode = null;

    // Cache labels + the (mode-aware) click handler, then open the floor tab
    // with the floor selected.
    try {
      drawAutoLabels(result.labels, toggleSurface);
    } catch (err) {
      console.error("❌ drawAutoLabels fail:", err);
    }

    try {
      setActiveMode("tile");
    } catch (err) {
      console.error("❌ setActiveMode fail:", err);
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
    if (id === "floor" || id === "ceiling") {
      // Single-region surfaces (binary masks).
      const mask = id === "floor" ? state.autoMasks.floor : state.autoMasks.ceiling;
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
  // NOTE: we intentionally do NOT clear the accumulated composite here.
  // Changing which surface is selected must keep previously applied edits
  // (e.g. selecting a wall to paint must not discard the tiled floor).
}

// ── Surface selection (mode-aware) ──────────────────────────────────────
// Toggling respects the active activity so floor and walls can never be
// selected at the same time: floor is selectable only while tiling, walls
// only while painting (and several walls may be picked at once).
export function toggleSurface(id) {
  const isFloor = id === "floor";
  const neededMode = isFloor ? "tile" : "paint";

  // Clicking a surface that belongs to the other activity switches to it
  // (and selects the clicked surface) — floor and walls are never mixed.
  if (state.activeMode !== neededMode) {
    setActiveMode(neededMode); // tiling pre-selects floor; painting starts empty
    if (!isFloor) state.selectedSurfaces.add(id);
  } else if (isFloor) {
    // The floor is the sole tiling target — clicking always (re)selects it and
    // never toggles it off, so a click on the already-selected floor doesn't
    // silently clear the selection ("it forgot the floor").
    state.selectedSurfaces.add("floor");
  } else if (state.selectedSurfaces.has(id)) {
    state.selectedSurfaces.delete(id);
  } else {
    state.selectedSurfaces.add(id);
  }

  updateCombinedMask();
  redrawWithFloorHighlight();
  drawAutoLabels(); // refresh active / inactive marker states
  updateFooterHint();
}

// ── Rapid paint selection (all walls, optionally + ceiling, or clear) ───
export function quickSelectPaint(target) {
  // target: "walls" | "walls_ceiling" | "clear"
  if (state.activeMode !== "paint") setActiveMode("paint");
  if (target === "clear") {
    clearWallPaint();
    return;
  }
  state.selectedSurfaces.clear();
  (state.currentLabels || []).forEach((l) => {
    if (l.type === "wall") state.selectedSurfaces.add(l.id);
    if (target === "walls_ceiling" && l.type === "ceiling")
      state.selectedSurfaces.add(l.id);
  });
  updateCombinedMask();
  redrawWithFloorHighlight();
  drawAutoLabels();
  updateFooterHint();
}

// ── Clear wall paint: deselect walls AND remove applied paint ──────────────
// "Effacer" reverts the wall paint, restoring the paint-free base (the tiled
// floor if the floor was tiled, otherwise the original photo). Selection is
// cleared too, so the user starts fresh.
export function clearWallPaint() {
  state.selectedSurfaces.clear();
  if (state.surfaceSelections) state.surfaceSelections.paint = new Set();
  state.hasPaint = false;

  const finish = () => {
    updateCombinedMask();
    redrawWithFloorHighlight();
    drawAutoLabels();
    updateFooterHint();
    updateTogglePreviewVisibility();
  };

  if (state.paintBaseBlob) {
    // Floor was tiled → restore that tiled (paint-free) result.
    if (state.resultUrl) URL.revokeObjectURL(state.resultUrl);
    state.resultUrl = URL.createObjectURL(state.paintBaseBlob);
    const img = new Image();
    img.onload = () => {
      state.editedImage = img;
      finish();
    };
    img.src = state.resultUrl;
  } else {
    // Nothing tiled → back to the pristine original.
    if (state.resultUrl) {
      URL.revokeObjectURL(state.resultUrl);
      state.resultUrl = null;
    }
    state.editedImage = null;
    finish();
  }
  showStatus("Peinture effacée.", "success");
}

// ── Activity switch (tabs ↔ selection ↔ footer CTA) ─────────────────────
export function setActiveMode(mode) {
  if (mode !== "tile" && mode !== "paint") mode = "tile";

  // Lazy wall detection: trigger on first paint-tab visit if walls not loaded yet.
  if (mode === "paint" && CONFIG.wallPaintEnabled
      && !state.wallDetectionDone && !state.wallDetectionPending
      && state.originalImage) {
    runWallDetection(); // runs async in background, updates markers when done
  }

  // Remember the selection of the tab we're leaving so it's restored when the
  // user comes back (otherwise switching to paint and back loses the walls).
  const prev = state.activeMode;
  if (prev && state.surfaceSelections) {
    state.surfaceSelections[prev] = new Set(state.selectedSurfaces);
  }
  state.activeMode = mode;

  // Tabs: activate the chosen activity's tab + panel.
  const tileBtn = document.getElementById("tabTileBtn");
  const paintBtn = document.getElementById("tabPaintBtn");
  tileBtn?.classList.toggle("active", mode === "tile");
  paintBtn?.classList.toggle("active", mode === "paint");
  tileBtn?.setAttribute("aria-selected", String(mode === "tile"));
  paintBtn?.setAttribute("aria-selected", String(mode === "paint"));
  document
    .getElementById("tabTilePanel")
    ?.classList.toggle("active", mode === "tile");
  document
    .getElementById("tabPaintPanel")
    ?.classList.toggle("active", mode === "paint");

  // Restore this tab's previously-selected surfaces. The first time a tab is
  // opened (saved === null) we apply its default: tiling pre-selects the
  // floor; painting starts empty so the user picks the wall(s)/ceiling.
  const saved = state.surfaceSelections ? state.surfaceSelections[mode] : null;
  state.selectedSurfaces.clear();
  if (saved) {
    saved.forEach((id) => state.selectedSurfaces.add(id));
  } else if (mode === "tile" && state.autoMasks.floor) {
    state.selectedSurfaces.add("floor");
  }
  updateCombinedMask();

  // Footer CTA label tracks the activity.
  const btn = document.getElementById("applyActionBtn");
  if (btn)
    btn.textContent =
      mode === "tile" ? "Appliquer le carrelage" : "Appliquer la peinture";

  redrawWithFloorHighlight();
  drawAutoLabels();
  updateFooterHint();
}
