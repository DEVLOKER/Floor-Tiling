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
    "tilePattern",
    "gridRotation",
    "tileWidth",
    "tileHeight",
    "groutThickness",
    "translateX",
    "translateY",
    "tileTextureDataUrl",
    "tileTextureDarkDataUrl",
  ];
  const data = {};
  keys.forEach((k) => {
    const el = document.getElementById(k);
    if (k === "tileMode") {
      data[k] = state && state.tileMode ? state.tileMode : "color";
    } else if (k === "tileTextureDataUrl" || k === "tileTextureDarkDataUrl") {
      try {
        data[k] = state && state[k] ? state[k] : null;
      } catch (e) {
        data[k] = null;
      }
    } else if (el) {
      data[k] = el.value;
    }
  });
  localStorage.setItem("tilePreferences", JSON.stringify(data));
}

// Restore color and texture selections from localStorage
export function loadTilePreferences() {
  const raw = localStorage.getItem("tilePreferences");
  if (!raw) return;

  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }
  Object.entries(data).forEach(([k, v]) => {
    const el = document.getElementById(k);
    if (k === "tileMode" && v) {
      // We manually update the mode to avoid circular imports,
      // mirroring setTileMode logic for robustness
      if (state) state.tileMode = v;
      document.body.classList.toggle("texture-mode", v === "texture");
      document
        .getElementById("btnModeColor")
        ?.classList.toggle("active", v === "color");
      document
        .getElementById("btnModeTexture")
        ?.classList.toggle("active", v === "texture");
      document
        .getElementById("colorModePanel")
        ?.classList.toggle("active", v === "color");
      document
        .getElementById("textureModePanel")
        ?.classList.toggle("active", v === "texture");
      return;
    }
    if ((k === "tileTextureDataUrl" || k === "tileTextureDarkDataUrl") && v) {
      if (state) state[k] = v;
      return;
    }

    if (el && v !== undefined && v !== null) {
      el.value = v;
      // Trigger appropriate events to update badges and previews
      if (el.tagName === "SELECT") {
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  });
}
