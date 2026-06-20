// Manual 2-click tile alignment: the user drags a line along a real edge
// (wall base, grout, floor seam) and the grid snaps parallel to it. Works for
// both algorithms (the backend samples the grid field at the two points).
import { state } from "./state.js";

function toImageCoords(e) {
  const r = state.canvas.getBoundingClientRect();
  const x = (e.clientX - r.left) * (state.canvas.width / r.width);
  const y = (e.clientY - r.top) * (state.canvas.height / r.height);
  return [
    Math.round(Math.max(0, Math.min(state.canvas.width - 1, x))),
    Math.round(Math.max(0, Math.min(state.canvas.height - 1, y))),
  ];
}

// Enter draw mode; calls onDone() once the user has drawn a line.
export function startAlignMode(onDone) {
  const c = state.canvas;
  if (!c || !state.ctx || state.aligning) return;
  state.aligning = true;
  c.style.cursor = "crosshair";
  const overlay = document.getElementById("markersOverlay");
  if (overlay) overlay.style.display = "none"; // don't let markers eat pointers

  let start = null;
  let snapshot = null;

  const down = (e) => {
    e.preventDefault();
    c.setPointerCapture?.(e.pointerId);
    start = toImageCoords(e);
    snapshot = state.ctx.getImageData(0, 0, c.width, c.height);
  };
  const move = (e) => {
    if (!start) return;
    const p = toImageCoords(e);
    state.ctx.putImageData(snapshot, 0, 0);
    state.ctx.strokeStyle = "#8b5cf6"; // violet
    state.ctx.lineWidth = Math.max(2, c.width / 350);
    state.ctx.lineCap = "round";
    state.ctx.beginPath();
    state.ctx.moveTo(start[0], start[1]);
    state.ctx.lineTo(p[0], p[1]);
    state.ctx.stroke();
  };
  const up = (e) => {
    if (!start) return;
    const p = toImageCoords(e);
    if (Math.hypot(p[0] - start[0], p[1] - start[1]) > 10) {
      // Append as a new line; a 3rd draw starts a fresh pair.
      if (state.tileAlignLines.length >= 2) state.tileAlignLines = [];
      state.tileAlignLines.push([start, p]);
    }
    if (snapshot) state.ctx.putImageData(snapshot, 0, 0);
    cleanup();
    if (onDone) onDone();
  };
  const cleanup = () => {
    state.aligning = false;
    start = snapshot = null;
    c.style.cursor = "";
    c.removeEventListener("pointerdown", down);
    c.removeEventListener("pointermove", move);
    c.removeEventListener("pointerup", up);
    if (overlay) overlay.style.display = "";
  };

  c.addEventListener("pointerdown", down);
  c.addEventListener("pointermove", move);
  c.addEventListener("pointerup", up);
}

export function resetAlign(onDone) {
  state.tileAlignLines = [];
  if (onDone) onDone();
}
