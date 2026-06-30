// Main entry point for the app
import { CONFIG, APP_NAME, APP_LOGO_SRC } from "./config.js";
import { state } from "./state.js";
import { applyDefaults } from "./helpers.js";
import { saveTilePreferences, loadTilePreferences } from "./persistence.js";
import {
  updateTilePreview,
  syncPatternUI,
  initFullscreenDetection,
  openPanel,
  closePanel,
  setTileMode,
  setPaintMode,
  setPaintFinish,
  setTileAlgorithm,
  updateTogglePreviewVisibility,
  drawAutoLabels,
} from "./ui.js";
import {
  applyActiveAction,
  liveApply,
  initEventListeners,
  downloadResultImage,
} from "./events.js";
import { setActiveMode, quickSelectPaint } from "./image.js";
import { startAlignMode, resetAlign } from "./align.js";
import { initTextureUpload } from "./texture.js";
import { initOnboarding } from "./onboarding.js";

// ── Bootstrap ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Inject app name everywhere from single source of truth
  document.title = APP_NAME;
  document
    .querySelectorAll("[data-app-name]")
    .forEach((el) => (el.textContent = APP_NAME));

  // Inject logo src everywhere from single source of truth
  document.querySelectorAll("img[data-app-logo]").forEach((img) => {
    img.src = APP_LOGO_SRC;
    img.alt = APP_NAME;
  });

  applyDefaults(CONFIG);

  // 1. Initialize listeners and basic modules first
  initEventListeners();
  initTextureUpload();
  initFullscreenDetection();

  // 2. Load saved state (this triggers the listeners above to update UI)
  loadTilePreferences();

  // 3. Initial sync and first preview render (texture UI already restored inside loadTilePreferences)
  syncPatternUI();
  updateTilePreview();
  // Save preferences on setting changes
  [
    "tileColor",
    "groutColor",
    "tileColorLight",
    "tileColorDark",
    "groutColorChecker",
    "groutColorTexture",
    "tilePattern",
    "gridRotation",
    "perspectiveCompression",
    "tileWidth",
    "tileHeight",
    "groutThickness",
    "translateX",
    "translateY",
    "wallPaintColor",
    "wallPaintFinish",
    "paintTextureScale",
    "wallPaintOpacity",
    "wallPaintLight",
    "wallPaintSat",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      const eventType = el.tagName === "SELECT" ? "change" : "input";
      el.addEventListener(eventType, () => {
        // invalidateCachedResult();
        saveTilePreferences();
      });
    }
  });

  // ── Live apply: re-render on release of ANY tile/paint control ───────────
  // `change` fires on mouse release (sliders) / close (colour) / select, so it
  // updates the result without firing continuously during a drag.
  [
    // tiling
    "tileColor", "groutColor", "tileColorLight", "tileColorDark",
    "groutColorChecker", "groutColorTexture", "tilePattern", "gridRotation",
    "perspectiveCompression", "tileWidth", "tileHeight", "groutThickness",
    "translateX", "translateY", "autoAlignToggle",
    // painting
    "wallPaintColor", "wallPaintFinish", "wallPaintOpacity", "wallPaintLight",
    "wallPaintSat", "paintTextureScale", "paintWallObjectsToggle",
    "paintWallOpeningsToggle",
  ].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", liveApply);
  });

  // Buttons are handled explicitly at the bottom to ensure state is updated first
  // Save textures after upload
  ["textureFileInput", "textureDarkFileInput"].forEach((id) => {
    const el = document.getElementById(id);
    if (el)
      el.addEventListener("change", () => {
        // Don't wipe the applied result — the texture only affects the NEXT
        // apply. The composite stays on screen until the user re-applies.
        saveTilePreferences();
      });
  });
  // Wire up panel and tile mode controls
  document
    .getElementById("openSettingsBtn")
    ?.addEventListener("click", openPanel);
  document
    .getElementById("closePanelBtn")
    ?.addEventListener("click", closePanel);
  document
    .getElementById("panelBackdrop")
    ?.addEventListener("click", closePanel);
  // Fill-style tabs only change which inputs feed the NEXT apply — they must
  // NOT clear the already-applied result from the canvas.
  document.getElementById("btnModeColor")?.addEventListener("click", () => {
    setTileMode("color");
    saveTilePreferences();
    liveApply();
  });
  document.getElementById("btnModeTexture")?.addEventListener("click", () => {
    setTileMode("texture");
    saveTilePreferences();
    liveApply();
  });
  // Paint fill-style tabs (colour / texture)
  document.getElementById("btnPaintModeColor")?.addEventListener("click", () => {
    setPaintMode("color");
    saveTilePreferences();
    liveApply();
  });
  document
    .getElementById("btnPaintModeTexture")
    ?.addEventListener("click", () => {
      setPaintMode("texture");
      saveTilePreferences();
      liveApply();
    });
  // Paint finish segmented badges (Mat / Satiné / Brillant)
  document
    .querySelectorAll("#paintFinishToggle .tile-source-btn")
    .forEach((btn) =>
      btn.addEventListener("click", () => {
        setPaintFinish(btn.dataset.finish);
        saveTilePreferences();
      }),
    );
  // Sync the badges to the restored value after preferences load
  setPaintFinish(document.getElementById("wallPaintFinish")?.value || "matte");

  // Tiling perspective algorithm segmented badges (Lignes de fuite / Profondeur)
  document
    .querySelectorAll("#tileAlgoToggle .tile-source-btn")
    .forEach((btn) =>
      btn.addEventListener("click", () => {
        setTileAlgorithm(btn.dataset.algo);
        saveTilePreferences();
        liveApply();
      }),
    );
  setTileAlgorithm(document.getElementById("tileAlgorithm")?.value || "vanishing");

  // Manual 2-click tile alignment
  const alignHint = document.getElementById("tileAlignHint");
  const updateAlignUI = () => {
    const n = (state.tileAlignLines || []).length;
    document.getElementById("tileAlignBtn")?.classList.toggle("active", n > 0);
    if (!alignHint) return;
    if (n === 0)
      alignHint.textContent =
        "Activez l'alignement automatique ci-dessus, ou tracez une ligne le long d'un mur pour aligner manuellement.";
    else if (n === 1)
      alignHint.textContent =
        "1 ligne : rotation alignée. Tracez une 2e ligne sur un mur perpendiculaire si un côté reste de travers.";
    else
      alignHint.textContent =
        "Aligné sur 2 murs. « Effacer » pour retirer les lignes.";
  };
  document.getElementById("tileAlignBtn")?.addEventListener("click", () => {
    if (!state.originalImage) return;
    if (alignHint) alignHint.textContent = "Tracez la ligne sur l'image…";
    startAlignMode(() => {
      updateAlignUI();
      liveApply();
    });
  });
  document
    .getElementById("tileAlignReset")
    ?.addEventListener("click", () =>
      resetAlign(() => {
        updateAlignUI();
        liveApply();
      }),
    );
  updateAlignUI();
  // Canvas click for floor selection
  // Clear/apply floor selection
  // Activity tabs → switch selection mode + footer CTA
  document
    .getElementById("tabTileBtn")
    ?.addEventListener("click", () => setActiveMode("tile"));
  document
    .getElementById("tabPaintBtn")
    ?.addEventListener("click", () => setActiveMode("paint"));

  // Single context-aware apply button (tiles in tiling mode, paint in paint mode)
  document
    .getElementById("applyActionBtn")
    ?.addEventListener("click", applyActiveAction);

  // Rapid surface selection (paint tab)
  document.getElementById("qsWalls")?.addEventListener("click", () => {
    quickSelectPaint("walls");
    liveApply(); // select-and-paint in one click
  });
  document.getElementById("qsWallsCeiling")?.addEventListener("click", () => {
    quickSelectPaint("walls_ceiling");
    liveApply();
  });
  document
    .getElementById("qsClear")
    ?.addEventListener("click", () => quickSelectPaint("clear"));

  // Live-preview toggle (off = apply only via the button)
  const liveToggle = document.getElementById("liveApplyToggle");
  if (liveToggle) {
    liveToggle.checked = state.liveApply;
    liveToggle.addEventListener("change", () => {
      state.liveApply = liveToggle.checked;
      saveTilePreferences();
    });
  }

  // Initialise the panel to the default activity (footer label + accordion state)
  setActiveMode("tile");

  document
    .getElementById("downloadBtn")
    ?.addEventListener("click", downloadResultImage);

  // Markers FAB: pin the surface markers visible (overrides the auto-hide), so
  // they stay shown on touch or when the user wants to keep selecting.
  document.getElementById("markersToggleBtn")?.addEventListener("click", () => {
    const ws = document.querySelector(".canvas-workspace");
    if (!ws) return;
    const pinned = ws.classList.toggle("markers-pinned");
    document
      .getElementById("markersToggleBtn")
      .classList.toggle("active", pinned);
  });

  // Redraw highlight if needed (optional)
  // redrawWithFloorHighlight();
  console.log("App modules loaded:", { CONFIG, state });

  // Sync UI on resize or layout changes
  const canvasEl = document.getElementById("mainCanvas");
  if (canvasEl && window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        // Re-sync overlay to canvas bounding rect on every layout change
        drawAutoLabels();
        updateTogglePreviewVisibility();
      });
    });
    ro.observe(canvasEl);
  } else {
    window.addEventListener("resize", updateTogglePreviewVisibility);
  }

  // ── Wall/ceiling paint feature gate ─────────────────────────────────────
  // When disabled, hide the paint tab, its panel, and the quick-select buttons
  // that target walls/ceiling. Floor tiling still works normally.
  // Flip CONFIG.wallPaintEnabled = true to restore once quality is ready.
  if (!CONFIG.wallPaintEnabled) {
    const hide = (...ids) =>
      ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.style.display = "none";
      });
    hide("tabPaintBtn", "tabPaintPanel", "qsWalls", "qsWallsCeiling");
  }

  // Initialize onboarding module (keeps feature wiring in events.js)
  initOnboarding({
    welcomeSelector: "#welcomeOverlay",
    fileInputSelector: "#fileInput",
  });
});
