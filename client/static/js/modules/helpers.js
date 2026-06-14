// Helper functions

/**
 * Sync the CSS --sl-pct variable on a range input so the track fill
 * always matches the current thumb position.
 */
export function syncSliderTrack(el) {
  const min = parseFloat(el.min) || 0;
  const max = parseFloat(el.max) || 100;
  const pct = ((parseFloat(el.value) - min) / (max - min)) * 100;
  el.style.setProperty("--sl-pct", pct.toFixed(1) + "%");
}

export function val(id) {
  const el = document.getElementById(id);
  return el ? el.value : "";
}

export function badge(id, txt) {
  const el = document.getElementById(id);
  if (el) el.textContent = txt;
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
  set("groutThickness", CONFIG.defaultGrout);
  badge("groutValue", CONFIG.defaultGrout + " px");
  document
    .getElementById("hintGrout")
    ?.style.setProperty("--th", CONFIG.defaultGrout + "px");
  // Translation
  set("translateX", CONFIG.defaultTranslateX);
  set("translateY", CONFIG.defaultTranslateY);
  badge("translateXValue", CONFIG.defaultTranslateX);
  badge("translateYValue", CONFIG.defaultTranslateY);
  // Perspective
  set("perspectiveCompression", CONFIG.defaultPerspectiveCompression);
  badge(
    "perspectiveCompressionValue",
    CONFIG.defaultPerspectiveCompression + "%",
  );
  // Pattern
  set("tilePattern", CONFIG.defaultPattern);
  // Sync slider tracks after values are set
  [
    "tileWidth",
    "tileHeight",
    "groutThickness",
    "translateX",
    "translateY",
    "gridRotation",
    "perspectiveCompression",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) syncSliderTrack(el);
  });

  // Colours
  set("tileColor", CONFIG.defaultTileColor);
  set("groutColor", CONFIG.defaultGroutColor);
  set("tileColorLight", CONFIG.defaultTileColorLight);
  set("tileColorDark", CONFIG.defaultTileColorDark);
  set("groutColorChecker", CONFIG.defaultGroutColorChecker);
  set("groutColorTexture", CONFIG.defaultGroutColorTexture);
  set("wallPaintColor", CONFIG.defaultPaintColor);
  set("paintTextureScale", CONFIG.defaultPaintTextureScale);
  badge("paintTextureScaleValue", CONFIG.defaultPaintTextureScale + " cm");
  // Paint realism sliders
  const paintSliders = [
    ["paintTextureScale", null, null],
    ["wallPaintOpacity", "wallPaintOpacityValue", CONFIG.defaultPaintOpacity],
    ["wallPaintLight", "wallPaintLightValue", CONFIG.defaultPaintLight],
    ["wallPaintSat", "wallPaintSatValue", CONFIG.defaultPaintSat],
  ];
  paintSliders.forEach(([id, badgeId, def]) => {
    if (def != null) {
      set(id, def);
      badge(badgeId, def + " %");
    }
    const el = document.getElementById(id);
    if (el) syncSliderTrack(el);
  });
}

// Ensure only val and badge are exported from here
