// Optionally re-export drawChevronPreview from ui.js for pattern-related logic
export { drawChevronPreview } from "./ui.js";

export function isCheckerPattern(pattern) {
  return ["checkerboard", "diagonal_checkerboard"].includes(pattern);
}

export function isDualColorPattern(pattern) {
  return [
    "checkerboard",
    "diagonal_checkerboard",
    "chevron",
    "basketweave",
    "versailles",
  ].includes(pattern);
}
