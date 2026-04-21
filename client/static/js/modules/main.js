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
  updateTogglePreviewVisibility,
  drawAutoLabels,
} from "./ui.js";
import {
  applyTilesToFloor,
  initEventListeners,
  downloadResultImage,
} from "./events.js";
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
    "tileWidth",
    "tileHeight",
    "groutThickness",
    "translateX",
    "translateY",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      const eventType = el.tagName === "SELECT" ? "change" : "input";
      el.addEventListener(eventType, saveTilePreferences);
    }
  });
  // Buttons are handled explicitly at the bottom to ensure state is updated first
  // Save textures after upload
  ["textureFileInput", "textureDarkFileInput"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", saveTilePreferences);
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
  document.getElementById("btnModeColor")?.addEventListener("click", () => {
    setTileMode("color");
    saveTilePreferences();
  });
  document.getElementById("btnModeTexture")?.addEventListener("click", () => {
    setTileMode("texture");
    saveTilePreferences();
  });
  // Canvas click for floor selection
  // Clear/apply floor selection
  document
    .getElementById("applyTilesBtn")
    ?.addEventListener("click", applyTilesToFloor);
  document
    .getElementById("applyTilesPanelBtn")
    ?.addEventListener("click", applyTilesToFloor);

  document
    .getElementById("downloadBtn")
    ?.addEventListener("click", downloadResultImage);

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

  // Initialize onboarding module (keeps feature wiring in events.js)
  initOnboarding({
    welcomeSelector: "#welcomeOverlay",
    fileInputSelector: "#fileInput",
  });
});
