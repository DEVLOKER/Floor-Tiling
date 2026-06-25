// App state
export let state = {
  originalImage: null,
  canvas: null,
  ctx: null,
  floorMask: null,
  floorConfidence: 0,
  isLoading: false,
  imageDimensions: { width: 0, height: 0 },
  tileMode: "color", // "color" | "texture"
  tileTextureDataUrl: null, // base64 data URL of primary (light) texture
  tileTextureDarkDataUrl: null, // base64 data URL of secondary (dark) texture
  paintMode: "color", // "color" | "texture" — wall/ceiling paint fill style
  paintTextureDataUrl: null, // base64 data URL of the wall paint texture
  resultUrl: null, // object URL of the accumulated composite (floor tiles + wall paint)
  editedImage: null, // <img> of the accumulated composite, kept in sync with resultUrl
  showingTiledResult: false, // tracks which image is shown on canvas in toggle preview
  // Wall paint must be re-derivable so recolours / mask changes (e.g. toggling
  // wall objects) REPLACE the paint instead of stacking. So paint always
  // composites onto this paint-free base (the floor-tiled result, or original),
  // never the previous painted result. Updated only by tiling, not painting.
  paintBaseBlob: null,
  hasPaint: false, // whether wall paint is currently applied (for re-chaining)
  autoMasks: { floor: null, wall: null, ceiling: null, objects: null, openings: null },
  showDetectedObjects: true, // overlay detected wall objects/openings after detection
  activeMode: "tile", // "tile" (floor) | "paint" (walls) — drives selection rules
  liveApply: true, // auto re-render on control change; off = apply only via button
  selectedSurfaces: new Set(), // Set of "floor" | "wall"
  // Per-tab selection memory so switching tabs doesn't lose the other tab's
  // picks. null = "not visited yet" → apply that tab's default.
  surfaceSelections: { tile: null, paint: null },
  currentLabels: [], // Cache for active detection labels
  onLabelToggle: null, // Cache for the label click handler
  aligning: false, // true while the user is drawing the manual alignment line
  // Up to 2 alignment lines (image coords); each is [[x1,y1],[x2,y2]].
  // 1 line → fixes rotation; 2 perpendicular lines → fixes rotation + shear.
  tileAlignLines: [],
};

export function setState(newState) {
  Object.assign(state, newState);
}
