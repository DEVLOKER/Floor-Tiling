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
  resultUrl: null, // object URL of the accumulated composite (floor tiles + wall paint)
  editedImage: null, // <img> of the accumulated composite, kept in sync with resultUrl
  showingTiledResult: false, // tracks which image is shown on canvas in toggle preview
  autoMasks: { floor: null, wall: null },
  activeMode: "tile", // "tile" (floor) | "paint" (walls) — drives selection rules
  selectedSurfaces: new Set(), // Set of "floor" | "wall"
  currentLabels: [], // Cache for active detection labels
  onLabelToggle: null, // Cache for the label click handler
};

export function setState(newState) {
  Object.assign(state, newState);
}
