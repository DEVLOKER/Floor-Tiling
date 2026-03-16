// Main entry point for the app
import { CONFIG } from "./config.js";
import { state, setState } from "./state.js";
window.state = state;
import { val, badge, applyDefaults } from "./helpers.js";
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
import { handleCanvasClick } from "./image.js";
import {
  clearFloorSelection,
  applyTilesToFloor,
  initEventListeners,
} from "./events.js";
import { initTextureUpload } from "./texture.js";

// ── Bootstrap ─────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  applyDefaults(CONFIG);
  loadTilePreferences();
  // Restore texture previews if textures are in state
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
    // Restore the filename if present
    if (state.tileTextureDarkName) {
      const name = document.getElementById("textureDarkName");
      if (name) name.textContent = state.tileTextureDarkName;
    }
  }
  // Always show the dark group if a dark texture is present
  if (state.tileTextureDarkDataUrl && darkGroup) {
    darkGroup.style.display = "";
  }
  initEventListeners();
  initTextureUpload();
  syncPatternUI();
  updateTilePreview();
  initFullscreenDetection();
  // Save preferences on color/texture/mode change
  [
    "tileColor",
    "groutColor",
    "tileColorLight",
    "tileColorDark",
    "groutColorChecker",
    "groutColorTexture",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", saveTilePreferences);
  });
  ["btnModeColor", "btnModeTexture"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", saveTilePreferences);
  });
  // Save textures after upload (handled in texture.js, but add here for robustness)
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
    ?.addEventListener("click", () => setTileMode("color"));
  document
    .getElementById("btnModeTexture")
    ?.addEventListener("click", () => setTileMode("texture"));
  // Canvas click for floor selection
  document
    .getElementById("mainCanvas")
    ?.addEventListener("click", handleCanvasClick);
  // Clear/apply floor selection
  document
    .getElementById("clearFloorBtn")
    ?.addEventListener("click", clearFloorSelection);
  document
    .getElementById("applyTilesBtn")
    ?.addEventListener("click", applyTilesToFloor);
  document
    .getElementById("applyTilesPanelBtn")
    ?.addEventListener("click", applyTilesToFloor);
  // Redraw highlight if needed (optional)
  // redrawWithFloorHighlight();
  console.log("App modules loaded:", { CONFIG, state });
});
