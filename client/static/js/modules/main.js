// Main entry point for the app
import { CONFIG } from "./config.js";
import { state } from "./state.js";
import { val, applyDefaults } from "./helpers.js";
import { saveTilePreferences, loadTilePreferences } from "./persistence.js";
import {
  showStatus,
  updateTilePreview,
  syncPatternUI,
  initFullscreenDetection,
  openPanel,
  closePanel,
  setTileMode,
  redrawWithFloorHighlight,
} from "./ui.js";
import {
  applyTilesToFloor,
  initEventListeners,
  downloadResultImage,
} from "./events.js";
import { initTextureUpload } from "./texture.js";

// ── Bootstrap ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  applyDefaults(CONFIG);
  
  // 1. Initialize listeners and basic modules first
  initEventListeners();
  initTextureUpload();
  initFullscreenDetection();

  // 2. Load saved state (this triggers the listeners above to update UI)
  loadTilePreferences();

  // 3. Restore any UI components that rely on the loaded state
  if (state.tileTextureDataUrl) {
    const thumb = document.getElementById("textureThumb");
    if (thumb) thumb.src = state.tileTextureDataUrl;
    const preview = document.getElementById("texturePreview");
    if (preview) preview.style.display = "block";
    const empty = document.getElementById("textureEmpty");
    if (empty) empty.style.display = "none";
    const area = document.getElementById("textureUploadArea");
    if (area) area.classList.add("has-texture");
  }

  const darkGroup = document.getElementById("textureDarkGroup");
  if (state.tileTextureDarkDataUrl) {
    const thumb = document.getElementById("textureDarkThumb");
    if (thumb) thumb.src = state.tileTextureDarkDataUrl;
    const preview = document.getElementById("textureDarkPreview");
    if (preview) preview.style.display = "block";
    const empty = document.getElementById("textureDarkEmpty");
    if (empty) empty.style.display = "none";
    const area = document.getElementById("textureDarkUploadArea");
    if (area) area.classList.add("has-texture");
  }

  // Always show the dark group if a dark texture is present
  if (state.tileTextureDarkDataUrl && darkGroup) {
    darkGroup.style.display = "";
  }

  // 4. Initial sync and first preview render
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
    "groutHThickness",
    "groutVThickness",
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
  document
    .getElementById("btnModeColor")
    ?.addEventListener("click", () => {
      setTileMode("color");
      saveTilePreferences();
    });
  document
    .getElementById("btnModeTexture")
    ?.addEventListener("click", () => {
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
        // Note: drawAutoLabels() is no longer needed here as markers are Percentage-Locked via CSS
        updateTogglePreviewVisibility();
      });
    });
    ro.observe(canvasEl);
  } else {
    window.addEventListener("resize", updateTogglePreviewVisibility);
  }
});
