// Configuration & Defaults
export const APP_NAME = "Ceramission";
// export const APP_NAME = "Visualiseur de Carrelage";

// Logo image path — change this once to update the logo everywhere.
export const APP_LOGO_SRC = "/static/logo.svg";

// Server-injected config (set by backend/settings.py, injected into HTML at
// page load as window.__APP_CONFIG__). Falls back to safe defaults so the
// frontend works even when served without the backend (e.g. static preview).
const _s = window.__APP_CONFIG__ || {};

export const CONFIG = {
  // ── Feature flags (from settings.py) ──────────────────────────────────────
  wallPaintEnabled: _s.wallPaintEnabled ?? false,

  // ── Tile defaults (mirrors settings.py section 7) ─────────────────────────
  defaultTileWidth: _s.defaultTileWidth ?? 30,
  defaultTileHeight: _s.defaultTileHeight ?? 30,
  defaultGrout: _s.defaultGrout ?? 1,
  defaultTranslateX: _s.defaultTranslateX ?? 0,
  defaultTranslateY: _s.defaultTranslateY ?? 0,
  defaultPerspectiveCompression: _s.defaultPerspectiveCompression ?? 50,
  defaultPattern: _s.defaultPattern ?? "grid",

  // ── Tile constraints (mirrors settings.py section 7) ──────────────────────
  tileWidthMin: _s.tileWidthMin ?? 5,
  tileWidthMax: _s.tileWidthMax ?? 200,
  tileHeightMin: _s.tileHeightMin ?? 5,
  tileHeightMax: _s.tileHeightMax ?? 200,
  groutThicknessMin: _s.groutThicknessMin ?? 0,
  groutThicknessMax: _s.groutThicknessMax ?? 20,

  // ── Paint defaults (mirrors settings.py section 6) ────────────────────────
  defaultPaintColor: _s.defaultPaintColor ?? "#C8D6E5",
  defaultPaintFinish: _s.defaultPaintFinish ?? "matte",
  paintFinishes: _s.paintFinishes ?? ["matte", "satin", "gloss"],

  // ── Purely frontend constants (no backend equivalent) ─────────────────────
  apiUrl: "/api",
  imageMaxWidth: 1000,
  imageJpegQuality: 0.95,
  defaultTileColor: "#E8D1B5",
  defaultGroutColor: "#A9A9A9",
  defaultTileColorLight: "#F5F5F0",
  defaultTileColorDark: "#2C2C2C",
  defaultGroutColorChecker: "#888888",
  defaultGroutColorTexture: "#A9A9A9",
  defaultPaintTextureScale: 130,
  defaultPaintOpacity: 80,
  defaultPaintLight: 100,
  defaultPaintSat: 86,
  previewColorFallback: "#cccccc",
  textureFallbackDark: "#666666",
  textureFallbackLight: "#d4b896",
  floorHighlightColor: "#667eea",
  textureDragBorderColor: "#667eea",
  toastDurationError: 6000,
  toastDurationDefault: 3500,
};
