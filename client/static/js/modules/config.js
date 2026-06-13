// Configuration & Defaults
export const APP_NAME = "Ceramission";
// export const APP_NAME = "Visualiseur de Carrelage";

// Logo image path — change this once to update the logo everywhere.
export const APP_LOGO_SRC = "/static/logo.svg";

export const CONFIG = {
  apiUrl: "/api",
  imageMaxWidth: 1000,
  imageJpegQuality: 0.95,
  defaultTileWidth: 30,
  defaultTileHeight: 30,
  defaultGrout: 1,
  defaultTranslateX: 0,
  defaultTranslateY: 0,
  defaultPerspectiveCompression: 0,
  defaultPattern: "grid",
  defaultTileColor: "#E8D1B5",
  defaultGroutColor: "#A9A9A9",
  defaultTileColorLight: "#F5F5F0",
  defaultTileColorDark: "#2C2C2C",
  defaultGroutColorChecker: "#888888",
  defaultGroutColorTexture: "#A9A9A9",
  previewColorFallback: "#cccccc",
  textureFallbackDark: "#666666",
  textureFallbackLight: "#d4b896",
  floorHighlightColor: "#667eea", // "#00FF00",
  textureDragBorderColor: "#667eea",
  toastDurationError: 6000,
  toastDurationDefault: 3500,
};
