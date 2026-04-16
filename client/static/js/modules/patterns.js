// Optionally re-export drawChevronPreview from ui.js for pattern-related logic
export { drawChevronPreview } from "./ui.js";

export function isCheckerPattern(pattern) {
  return ["checkerboard"].includes(pattern);
}

export function isDualColorPattern(pattern) {
  return [
    "checkerboard",
    "chevron",
    "basketweave",
    "straightweave",
    "versailles",
  ].includes(pattern);
}
