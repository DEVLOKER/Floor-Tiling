import numpy as np
import cv2
from typing import Tuple, Optional
from config.settings import DEPTH_MIN_CM, DEPTH_MAX_CM


def hex_to_bgr(h: str) -> tuple:
    h = h.lstrip('#')
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except Exception:
        return (128, 128, 128)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fit_line_robust(pts: list) -> Optional[tuple]:
    """Fit a line to a list of [x,y] points. Returns (vx,vy,x0,y0) or None."""
    if len(pts) < 4:
        return None
    arr = np.array(pts, dtype=np.float32)
    line = cv2.fitLine(arr, cv2.DIST_L1, 0, 0.01, 0.01).flatten()
    return float(line[0]), float(line[1]), float(line[2]), float(line[3])


def _intersect_lines(l1: tuple, l2: tuple) -> Optional[tuple]:
    """Intersect two lines given as (vx,vy,x0,y0). Returns (x,y) or None."""
    vx1, vy1, x01, y01 = l1
    vx2, vy2, x02, y02 = l2
    denom = vx1 * vy2 - vy1 * vx2
    if abs(denom) < 1e-6:
        return None
    t = ((x02 - x01) * vy2 - (y02 - y01) * vx2) / denom
    return float(x01 + t * vx1), float(y01 + t * vy1)


def _collect_boundary_points(clean_mask: np.ndarray, edge_margin: int = 4):
    """
    Scan each row and collect left/right boundary pixels of the mask.
    Excludes pixels too close to image border (likely clipped by crop).
    Returns (left_pts, right_pts) as lists of [x,y].
    """
    h, w = clean_mask.shape
    left_pts, right_pts = [], []
    for row in range(h):
        cols = np.where(clean_mask[row] > 0)[0]
        if len(cols) < 2:
            continue
        if cols[0] > edge_margin:
            left_pts.append([float(cols[0]), float(row)])
        if cols[-1] < w - 1 - edge_margin:
            right_pts.append([float(cols[-1]), float(row)])
    return left_pts, right_pts


def _near_edge_from_mask(clean_mask: np.ndarray, y_near: float, band: int = 20):
    """
    Find the left and right x-positions of the floor mask at the near (bottom) edge.
    Uses a band of rows around y_near for robustness.
    Returns (x_left, x_right) or None.
    """
    h, w = clean_mask.shape
    lefts, rights = [], []
    y_center = int(round(y_near))
    for dy in range(-band, band + 1):
        y = y_center + dy
        if 0 <= y < h:
            cols = np.where(clean_mask[y] > 0)[0]
            if len(cols) >= 2:
                lefts.append(int(cols[0]))
                rights.append(int(cols[-1]))
    if not lefts:
        return None
    return float(np.median(lefts)), float(np.median(rights))


def _far_edge_from_mask(clean_mask: np.ndarray, y_far: float, band: int = 20):
    """Same as _near_edge_from_mask but for the far (top) edge."""
    return _near_edge_from_mask(clean_mask, y_far, band)


# ─────────────────────────────────────────────────────────────────────────────
# Vanishing point — used ONLY for far-edge width scaling, not for rotation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_vp_from_boundaries(left_pts, right_pts,
                                 y_top: float, h: int, w: int
                                 ) -> Optional[tuple]:
    """
    Compute vanishing point by intersecting left and right boundary lines.
    The VP must be above the floor (y < y_top) and within a generous image region.
    Returns (vp_x, vp_y) or None.
    """
    l_line = _fit_line_robust(left_pts)
    r_line = _fit_line_robust(right_pts)
    if l_line is None or r_line is None:
        return None

    vp = _intersect_lines(l_line, r_line)
    if vp is None:
        return None

    vp_x, vp_y = vp
    # Accept VP if it's above the floor top and within 3x image width
    if vp_y >= y_top:
        print(f"  VP ({vp_x:.0f},{vp_y:.0f}) below floor top — rejected")
        return None
    if not (-2 * w < vp_x < 3 * w and -3 * h < vp_y < y_top):
        print(f"  VP ({vp_x:.0f},{vp_y:.0f}) out of plausible range — rejected")
        return None

    print(f"  VP (boundary lines): ({vp_x:.1f}, {vp_y:.1f})")
    return float(vp_x), float(vp_y)


def _hough_vanishing_point(image: np.ndarray, y_floor_top: int
                            ) -> Optional[tuple]:
    """Detect VP from diagonal lines in the wall region (above floor)."""
    h, w = image.shape[:2]
    wall_h = max(1, y_floor_top - 10)
    wall_img = image[:wall_h] if wall_h >= 30 else image

    gray  = cv2.cvtColor(wall_img, cv2.COLOR_BGR2GRAY) if wall_img.ndim == 3 else wall_img
    edges = cv2.Canny(gray, 30, 100)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40,
                             minLineLength=50, maxLineGap=15)
    if lines is None:
        return None

    diag = []
    for l in lines:
        x1, y1, x2, y2 = int(l[0][0]), int(l[0][1]), int(l[0][2]), int(l[0][3])
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if 10 < ang < 80:
            diag.append((x1, y1, x2, y2))

    if len(diag) < 2:
        return None

    vps = []
    for i in range(len(diag)):
        for j in range(i + 1, len(diag)):
            x1, y1, x2, y2 = diag[i]
            x3, y3, x4, y4 = diag[j]
            d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(d) < 1e-6:
                continue
            t  = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
            ix = x1 + t * (x2 - x1)
            iy = y1 + t * (y2 - y1)
            if -w < ix < 2 * w and -2 * h < iy < 2 * h:
                vps.append([float(ix), float(iy)])

    if len(vps) < 3:
        return None

    vpa = np.array(vps)
    vp = float(np.median(vpa[:, 0])), float(np.median(vpa[:, 1]))
    print(f"  VP (Hough/wall): ({vp[0]:.1f}, {vp[1]:.1f})")
    return vp


# ─────────────────────────────────────────────────────────────────────────────
# KEY FIX: Near-edge-first quad extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_floor_quad(mask: np.ndarray,
                       image: np.ndarray = None) -> Optional[tuple]:
    """
    Extract four perspective-correct corners from the floor mask.

    KEY INSIGHT — "Near edge first":
      The bottom edge of the floor mask is ALWAYS the most reliable geometric
      reference. It defines the true horizontal axis (U direction = parallel to
      front wall). We extract it first, then compute the far edge and VP
      separately, and NEVER allow the VP to tilt the near edge.

    Algorithm:
      1. Find near_y (97th percentile of mask rows) → near left/right x
      2. Find far_y  ( 3rd percentile of mask rows) → far centroid x
      3. Compute VP from left/right boundary lines (or Hough on walls)
      4. Scale far-edge width using VP geometry (perspective ratio guard)
      5. Center far edge at far centroid x
      6. Return a clean horizontal trapezoid

    This guarantees:
      - U-axis is horizontal (parallel to physical front wall)
      - V-axis converges to VP (perpendicular to front wall = depth direction)
      - Works for 3-wall, corner, side/oblique views, cluttered real photos
    """
    h, w = mask.shape
    mask_u8 = (mask > 0).astype(np.uint8)

    # ── Largest connected component ──────────────────────────────────────
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8)
    if num_labels <= 1:
        return None
    largest    = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    clean_mask = (labels == largest).astype(np.uint8)

    ys, xs = np.where(clean_mask > 0)
    if len(ys) == 0:
        return None

    # ── Near / far Y positions ───────────────────────────────────────────
    y_near = float(np.percentile(ys, 97))
    y_far  = float(np.percentile(ys, 3))
    if (y_near - y_far) < 10:
        return _extract_floor_quad_fallback(clean_mask)

    # ── Near edge: left/right x at bottom of floor ───────────────────────
    near_edge = _near_edge_from_mask(clean_mask, y_near, band=20)
    if near_edge is None:
        return _extract_floor_quad_fallback(clean_mask)
    nl_x, nr_x = near_edge
    near_w = nr_x - nl_x
    if near_w <= 10:
        return _extract_floor_quad_fallback(clean_mask)

    # ── Far centroid x: horizontal center of the far part of the mask ────
    y_p20  = float(np.percentile(ys, 20))
    top_xs = xs[ys <= y_p20]
    far_cx = float(np.mean(top_xs)) if len(top_xs) else (nl_x + nr_x) / 2.0

    # ── Far edge: actual left/right x at top of floor ────────────────────
    far_edge = _far_edge_from_mask(clean_mask, y_far, band=15)
    raw_far_w = (far_edge[1] - far_edge[0]) if far_edge else near_w * 0.5

    # ── VP detection ─────────────────────────────────────────────────────
    left_pts, right_pts = _collect_boundary_points(clean_mask)
    vp = None
    if len(left_pts) >= 4 and len(right_pts) >= 4:
        vp = _compute_vp_from_boundaries(left_pts, right_pts, y_far, h, w)
    if vp is None and image is not None:
        vp = _hough_vanishing_point(image, int(y_far))

    # ── Compute far-edge width from VP geometry ───────────────────────────
    # If VP is known: use the perspective projection formula.
    #   far_w / near_w = (far_y - vp_y) / (near_y - vp_y)
    # This is the CORRECT perspective scaling — independent of room shape.
    if vp is not None:
        vp_x, vp_y = vp
        denom = (y_near - vp_y)
        if abs(denom) > 1e-3:
            vp_scale = (y_far - vp_y) / denom
            vp_scale = float(np.clip(vp_scale, 0.10, 0.90))
            vp_far_w = near_w * vp_scale
            # Blend with raw mask far width (trust VP more when mask is clean)
            far_w = 0.7 * vp_far_w + 0.3 * raw_far_w
            print(f"  VP scale={vp_scale:.3f}  vp_far_w={vp_far_w:.0f}  "
                  f"raw_far_w={raw_far_w:.0f}  blend_far_w={far_w:.0f}")
        else:
            far_w = raw_far_w
    else:
        # No VP: use raw mask width with perspective ratio guard
        far_w = raw_far_w
        print("  No VP — using raw mask far width")

    # ── Perspective ratio guard ───────────────────────────────────────────
    # far_w / near_w must be in [0.12, 0.88]
    ratio  = far_w / max(near_w, 1.0)
    MIN_R, MAX_R = 0.12, 0.88
    if ratio < MIN_R:
        print(f"  Ratio {ratio:.2f} too small → clamping to {MIN_R}")
        far_w = near_w * MIN_R
    elif ratio > MAX_R:
        print(f"  Ratio {ratio:.2f} too large → clamping to {MAX_R}")
        far_w = near_w * MAX_R

    # ── Build final quad — centered at far_cx, near edge strictly horizontal
    half_far  = far_w / 2.0
    fl_x = far_cx - half_far
    fr_x = far_cx + half_far

    near_left  = np.array([nl_x, y_near], dtype=np.float32)
    near_right = np.array([nr_x, y_near], dtype=np.float32)
    far_left   = np.array([fl_x, y_far],  dtype=np.float32)
    far_right  = np.array([fr_x, y_far],  dtype=np.float32)

    print(f"  Quad OK  "
          f"NL=({nl_x:.0f},{y_near:.0f}) NR=({nr_x:.0f},{y_near:.0f})  "
          f"FL=({fl_x:.0f},{y_far:.0f})  FR=({fr_x:.0f},{y_far:.0f})  "
          f"near_w={near_w:.0f} far_w={far_w:.0f} ratio={far_w/near_w:.3f}")

    return near_left, near_right, far_left, far_right


def _extract_floor_quad_fallback(mask: np.ndarray) -> Optional[tuple]:
    """
    Robust fallback quad extraction using percentile rows + ratio guard.
    Near edge is always strictly horizontal.
    """
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None

    y_near = int(np.percentile(ys, 97))
    y_far  = int(np.percentile(ys, 3))

    near_edge = _near_edge_from_mask(mask, y_near, band=15)
    if near_edge is None:
        return None
    nl, nr = near_edge
    near_w = nr - nl

    # Far centroid x
    y_top20 = float(np.percentile(ys, 20))
    top_xs  = xs[ys <= y_top20]
    far_cx  = float(np.mean(top_xs)) if len(top_xs) else (nl + nr) / 2.0

    far_edge = _far_edge_from_mask(mask, y_far, band=15)
    far_w    = (far_edge[1] - far_edge[0]) if far_edge else near_w * 0.4

    ratio  = far_w / max(near_w, 1.0)
    MIN_R, MAX_R = 0.12, 0.88
    if ratio < MIN_R:
        far_w = near_w * MIN_R
    elif ratio > MAX_R:
        far_w = near_w * MAX_R

    half_far = far_w / 2.0
    fl = far_cx - half_far
    fr = far_cx + half_far

    near_left  = np.array([nl, float(y_near)], dtype=np.float32)
    near_right = np.array([nr, float(y_near)], dtype=np.float32)
    far_left   = np.array([fl, float(y_far)],  dtype=np.float32)
    far_right  = np.array([fr, float(y_far)],  dtype=np.float32)

    print(f"  [fallback] NL=({nl:.0f},{y_near}) NR=({nr:.0f},{y_near})  "
          f"FL=({fl:.0f},{y_far}) FR=({fr:.0f},{y_far})  ratio={far_w/max(near_w,1):.3f}")
    return near_left, near_right, far_left, far_right


# ─────────────────────────────────────────────────────────────────────────────
# rectify_quad — enforce strict horizontal trapezoid
# ─────────────────────────────────────────────────────────────────────────────

def rectify_quad(near_left: np.ndarray, near_right: np.ndarray,
                 far_left: np.ndarray, far_right: np.ndarray,
                 mask: np.ndarray) -> tuple:
    """
    Enforce a clean horizontal trapezoid.

    CRITICAL: Both near and far edges must be EXACTLY horizontal (same Y for
    left and right corners). Any Y-difference between the left and right
    corners of the same edge causes the grid to appear rotated/skewed.

    We simply average the Y of each edge pair. The X positions are already
    correct from extract_floor_quad (near-edge-first approach).
    """
    near_y = float((near_left[1] + near_right[1]) / 2.0)
    far_y  = float((far_left[1]  + far_right[1])  / 2.0)
    return (
        np.array([float(near_left[0]),  near_y], dtype=np.float32),
        np.array([float(near_right[0]), near_y], dtype=np.float32),
        np.array([float(far_left[0]),   far_y],  dtype=np.float32),
        np.array([float(far_right[0]),  far_y],  dtype=np.float32),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Geometry estimation — unchanged
# ─────────────────────────────────────────────────────────────────────────────

def estimate_floor_geometry(near_left: np.ndarray, near_right: np.ndarray,
                             far_left: np.ndarray, far_right: np.ndarray,
                             real_width_cm: float) -> tuple:
    """Estimate VP, depth, and depth_ratio from floor quad corners.

    Returns:
        (vp_y, real_depth_cm, depth_ratio)
    """
    x1,y1 = float(far_left[0]),   float(far_left[1])
    x2,y2 = float(near_left[0]),  float(near_left[1])
    x3,y3 = float(far_right[0]),  float(far_right[1])
    x4,y4 = float(near_right[0]), float(near_right[1])
    near_y = (y2 + y4) / 2.0
    far_y  = (y1 + y3) / 2.0

    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) > 1e-6:
        t    = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
        vp_y = float(y1 + t*(y2-y1))
        denom_y = far_y - vp_y
        if abs(denom_y) > 1e-3:
            depth_ratio   = (near_y - far_y) / denom_y
            real_depth_cm = float(np.clip(real_width_cm * abs(depth_ratio),
                                          DEPTH_MIN_CM, DEPTH_MAX_CM))
            print(f"  [geometry] vp_y={vp_y:.1f}  depth_ratio={depth_ratio:.3f}  "
                  f"depth={real_depth_cm:.1f}cm")
            return vp_y, real_depth_cm, depth_ratio

    vp_y          = far_y - (near_y - far_y)
    depth_ratio   = 1.0
    real_depth_cm = real_width_cm
    print(f"  [geometry fallback] depth={real_depth_cm:.1f}cm")
    return vp_y, real_depth_cm, depth_ratio