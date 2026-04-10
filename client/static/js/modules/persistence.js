import { state } from "./state.js";

// Save current color and texture selections to localStorage
export function saveTilePreferences() {
  const keys = [
    "tileColor",
    "groutColor",
    "tileColorLight",
    "tileColorDark",
    "groutColorChecker",
    "groutColorTexture",
    "tileMode",
    "tileTextureDataUrl",
    "tileTextureDarkDataUrl",
  ];
  const data = {};
  keys.forEach((k) => {
    const el = document.getElementById(k);
    if (el && el.type === "color") {
      data[k] = el.value;
    } else if (k === "tileMode") {
      data[k] = document.body.classList.contains("texture-mode")
        ? "texture"
        : "color";
    } else if (k === "tileTextureDataUrl" || k === "tileTextureDarkDataUrl") {
      // These are stored in state
      try {
        data[k] = state && state[k] ? state[k] : null;
      } catch (e) {
        data[k] = null;
      }
    }
  });
  localStorage.setItem("tilePreferences", JSON.stringify(data));
}

// Restore color and texture selections from localStorage
export function loadTilePreferences() {
  const raw = localStorage.getItem("tilePreferences");
  if (!raw) {
    // If not found, save current preferences as defaults
    saveTilePreferences();
    return;
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }
  Object.entries(data).forEach(([k, v]) => {
    const el = document.getElementById(k);
    if (el && el.type === "color" && v) {
      el.value = v;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (k === "tileMode" && v) {
      document.body.classList.toggle("texture-mode", v === "texture");
    }
    if (
      (k === "tileTextureDataUrl" ||
        k === "tileTextureDarkDataUrl") &&
      v
    ) {
      if (state) state[k] = v;
    }
  });
}
