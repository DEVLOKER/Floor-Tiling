import { state } from "./state.js";

// Guard: prevent saveTilePreferences from running while loadTilePreferences is
// dispatching events, which would otherwise overwrite localStorage with
// partially-restored state (e.g. wiping texture data URLs before they are applied).
let _restoring = false;

// Preferences schema version. Bump when a stored default becomes invalid so
// loadTilePreferences() can migrate old saves. v2: drop the legacy
// perspectiveCompression (old default 65 made tiles huge/flat) so the new 0
// default takes effect for returning users without wiping their other prefs.
const PREFS_VERSION = 2;

// ── Element-backed keys (restored via el.value + event dispatch) ──────────
const ELEMENT_KEYS = [
  "tileColor",
  "groutColor",
  "tileColorLight",
  "tileColorDark",
  "groutColorChecker",
  "groutColorTexture",
  "wallPaintColor",
  "wallPaintFinish",
  "paintTextureScale",
  "wallPaintOpacity",
  "wallPaintLight",
  "wallPaintSat",
  "tilePattern",
  "gridRotation",
  "perspectiveCompression",
  "tileWidth",
  "tileHeight",
  "groutThickness",
  "translateX",
  "translateY",
];

// ── Save current config to localStorage ──────────────────────────────────
export function saveTilePreferences() {
  if (_restoring) return; // skip intermediate saves during load
  const data = {};

  // State-only fields (not backed by a DOM element)
  data.tileMode = state?.tileMode ?? "color";
  data.tileTextureDataUrl = state?.tileTextureDataUrl ?? null;
  data.tileTextureDarkDataUrl = state?.tileTextureDarkDataUrl ?? null;
  data.textureName = document.getElementById("textureName")?.textContent ?? "";
  data.textureDarkName =
    document.getElementById("textureDarkName")?.textContent ?? "";

  data.liveApply = state?.liveApply ?? true;

  // Wall paint fill style (mirrors the tile texture persistence)
  data.paintMode = state?.paintMode ?? "color";
  data.paintTextureDataUrl = state?.paintTextureDataUrl ?? null;
  data.paintTextureName =
    document.getElementById("paintTextureName")?.textContent ?? "";

  // Element-backed fields
  ELEMENT_KEYS.forEach((k) => {
    const el = document.getElementById(k);
    if (el) data[k] = el.value;
  });

  data.__v = PREFS_VERSION;
  localStorage.setItem("tilePreferences", JSON.stringify(data));
}

// ── Restore config from localStorage ─────────────────────────────────────
export function loadTilePreferences() {
  const raw = localStorage.getItem("tilePreferences");
  if (!raw) return;

  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }

  // ── Migrate old saves ──────────────────────────────────────────────────
  // Pre-v2 saves carry the legacy perspectiveCompression (default 65) which
  // makes tiles look huge & flat.  Drop it so the new 0 default from
  // applyDefaults() stands; everything else (colours, textures, sizes) is kept.
  if ((data.__v ?? 0) < 2) {
    delete data.perspectiveCompression;
  }

  _restoring = true;
  try {
    // ── Phase 1: Apply state-only fields BEFORE any events fire ────────────
    // tileMode
    const savedMode = data.tileMode;
    if (savedMode) {
      if (state) state.tileMode = savedMode;
      document.body.classList.toggle("texture-mode", savedMode === "texture");
      document
        .getElementById("btnModeColor")
        ?.classList.toggle("active", savedMode === "color");
      document
        .getElementById("btnModeTexture")
        ?.classList.toggle("active", savedMode === "texture");
      document
        .getElementById("colorModePanel")
        ?.classList.toggle("active", savedMode === "color");
      document
        .getElementById("textureModePanel")
        ?.classList.toggle("active", savedMode === "texture");
    }

    if (typeof data.liveApply === "boolean" && state) {
      state.liveApply = data.liveApply;
      const lt = document.getElementById("liveApplyToggle");
      if (lt) lt.checked = data.liveApply;
    }

    // ── Wall paint fill style ──────────────────────────────────────────────
    const savedPaintMode = data.paintMode;
    if (savedPaintMode) {
      if (state) state.paintMode = savedPaintMode;
      document
        .getElementById("btnPaintModeColor")
        ?.classList.toggle("active", savedPaintMode === "color");
      document
        .getElementById("btnPaintModeTexture")
        ?.classList.toggle("active", savedPaintMode === "texture");
      document
        .getElementById("paintColorPanel")
        ?.classList.toggle("active", savedPaintMode === "color");
      document
        .getElementById("paintTexturePanel")
        ?.classList.toggle("active", savedPaintMode === "texture");
    }

    // Texture data URLs (must be in state before listeners read them)
    if (data.tileTextureDataUrl && state)
      state.tileTextureDataUrl = data.tileTextureDataUrl;
    if (data.tileTextureDarkDataUrl && state)
      state.tileTextureDarkDataUrl = data.tileTextureDarkDataUrl;
    if (data.paintTextureDataUrl && state)
      state.paintTextureDataUrl = data.paintTextureDataUrl;

    // Texture display names (cosmetic)
    if (data.textureName) {
      const el = document.getElementById("textureName");
      if (el) el.textContent = data.textureName;
    }
    if (data.textureDarkName) {
      const el = document.getElementById("textureDarkName");
      if (el) el.textContent = data.textureDarkName;
    }

    // Restore texture thumbnails and slot visibility
    if (data.tileTextureDataUrl) {
      const thumb = document.getElementById("textureThumb");
      if (thumb) thumb.src = data.tileTextureDataUrl;
      const preview = document.getElementById("texturePreview");
      if (preview) preview.style.display = "block";
      const empty = document.getElementById("textureEmpty");
      if (empty) empty.style.display = "none";
      document
        .getElementById("textureUploadArea")
        ?.classList.add("has-texture");
    }
    if (data.tileTextureDarkDataUrl) {
      const thumb = document.getElementById("textureDarkThumb");
      if (thumb) thumb.src = data.tileTextureDarkDataUrl;
      const preview = document.getElementById("textureDarkPreview");
      if (preview) preview.style.display = "block";
      const empty = document.getElementById("textureDarkEmpty");
      if (empty) empty.style.display = "none";
      document
        .getElementById("textureDarkUploadArea")
        ?.classList.add("has-texture");
      const darkGroup = document.getElementById("textureDarkGroup");
      if (darkGroup) darkGroup.style.display = "";
    }
    if (data.paintTextureName) {
      const el = document.getElementById("paintTextureName");
      if (el) el.textContent = data.paintTextureName;
    }
    if (data.paintTextureDataUrl) {
      const thumb = document.getElementById("paintTextureThumb");
      if (thumb) thumb.src = data.paintTextureDataUrl;
      const preview = document.getElementById("paintTexturePreview");
      if (preview) preview.style.display = "block";
      const empty = document.getElementById("paintTextureEmpty");
      if (empty) empty.style.display = "none";
      document
        .getElementById("paintTextureUploadArea")
        ?.classList.add("has-texture");
    }

    // ── Phase 2: Restore element values and fire events ────────────────────
    // Restore tilePattern LAST among element keys so that auto-size handlers
    // (e.g. windmill height = width / 2) run after tileWidth is already set.
    const patternValue = data.tilePattern;
    const elementKeysOrdered = ELEMENT_KEYS.filter((k) => k !== "tilePattern");

    elementKeysOrdered.forEach((k) => {
      const v = data[k];
      const el = document.getElementById(k);
      if (el && v !== undefined && v !== null) {
        el.value = v;
        el.dispatchEvent(
          new Event(el.tagName === "SELECT" ? "change" : "input", {
            bubbles: true,
          }),
        );
      }
    });

    // Restore pattern after dimensions so auto-size logic has correct width
    if (patternValue) {
      const patternEl = document.getElementById("tilePattern");
      if (patternEl) {
        patternEl.value = patternValue;
        patternEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  } finally {
    _restoring = false;
  }

  // One definitive save so localStorage reflects the fully-restored state
  // (including texture data URLs which don't dispatch events).
  saveTilePreferences();
}
