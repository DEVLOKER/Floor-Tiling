// Helper functions
export function val(id) {
  return document.getElementById(id).value;
}

export function badge(id, txt) {
  document.getElementById(id).textContent = txt;
}

export function applyDefaults(CONFIG) {
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.value = v;
  };
  // Tile dimensions
  set("tileWidth", CONFIG.defaultTileWidth);
  set("tileHeight", CONFIG.defaultTileHeight);
  badge("tileWidthValue", CONFIG.defaultTileWidth + " cm");
  badge("tileHeightValue", CONFIG.defaultTileHeight + " cm");
  // Grout thickness
  set("groutHThickness", CONFIG.defaultGroutH);
  set("groutVThickness", CONFIG.defaultGroutV);
  badge("groutHValue", CONFIG.defaultGroutH + " px");
  badge("groutVValue", CONFIG.defaultGroutV + " px");
  document
    .getElementById("hintH")
    ?.style.setProperty("--th", CONFIG.defaultGroutH + "px");
  document
    .getElementById("hintV")
    ?.style.setProperty("--tv", CONFIG.defaultGroutV + "px");
  // Pattern
  set("tilePattern", CONFIG.defaultPattern);
  // Colours
  set("tileColor", CONFIG.defaultTileColor);
  set("groutColor", CONFIG.defaultGroutColor);
  set("tileColorLight", CONFIG.defaultTileColorLight);
  set("tileColorDark", CONFIG.defaultTileColorDark);
  set("groutColorChecker", CONFIG.defaultGroutColorChecker);
  set("groutColorTexture", CONFIG.defaultGroutColorTexture);
}

// Ensure only val and badge are exported from here
