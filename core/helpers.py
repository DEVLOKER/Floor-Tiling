"""Core helper functions"""
import numpy as np
import cv2
from typing import Tuple
from config.settings import DEPTH_MIN_CM, DEPTH_MAX_CM


def hex_to_bgr(h: str) -> tuple:
    """Convert hex color string to BGR tuple for OpenCV.
    
    Args:
        h: Hex color string (e.g., '#E8D1B5')
    
    Returns:
        BGR tuple for OpenCV
    """
    h = h.lstrip('#')
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except Exception:
        return (128, 128, 128)



def _hough_vanishing_point(image: np.ndarray, y_floor_top: int):
    """Detect VP from diagonal lines in the WALL region only (above floor).

    By restricting to the wall region we avoid contamination from tile grout
    lines in the floor area, which would give a completely wrong VP.
    """
    h, w = image.shape[:2]

    # Use wall region: everything above the floor, with a small margin
    wall_h = max(1, y_floor_top - 10)
    if wall_h < 30:
        # Floor starts very high — use full image but weight upper half
        wall_img = image
    else:
        wall_img = image[:wall_h]

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
    return float(np.median(vpa[:, 0])), float(np.median(vpa[:, 1]))


def _mask_boundary_vp(left_pts, right_pts, y_floor_top):
    """Compute VP by fitting lines to mask boundary and intersecting them.
    Only trusted if VP is above the floor (vp_y < y_floor_top)."""
    if len(left_pts) < 4 or len(right_pts) < 4:
        return None

    lv = cv2.fitLine(np.array(left_pts,  dtype=np.float32),
                     cv2.DIST_L1, 0, 0.01, 0.01).flatten()
    rv = cv2.fitLine(np.array(right_pts, dtype=np.float32),
                     cv2.DIST_L1, 0, 0.01, 0.01).flatten()

    lvx, lvy, lx0, ly0 = float(lv[0]), float(lv[1]), float(lv[2]), float(lv[3])
    rvx, rvy, rx0, ry0 = float(rv[0]), float(rv[1]), float(rv[2]), float(rv[3])
    denom = lvx * rvy - lvy * rvx
    if abs(denom) < 1e-6:
        return None

    t    = ((rx0 - lx0) * rvy - (ry0 - ly0) * rvx) / denom
    vp_x = lx0 + t * lvx
    vp_y = ly0 + t * lvy

    # Only trust if VP is above the floor
    if vp_y >= y_floor_top:
        print(f"  Mask VP ({vp_x:.0f},{vp_y:.0f}) is inside/below floor — rejected")
        return None

    return float(vp_x), float(vp_y)


def extract_floor_quad(mask: np.ndarray,
                       image: np.ndarray = None) -> tuple:
    """Extract four perspective-correct corners from the floor mask.

    VP detection priority:
      1. Mask boundary line intersection (fast, exact when both walls visible)
         — but only trusted when VP is above the floor mask
      2. Hough lines on the WALL region of the image (above floor mask)
         — robust for any room geometry
      3. Fallback to extreme-row sampling

    All four corners are derived via VP rays to guarantee they converge
    at exactly the same vanishing point.
    """
    h, w = mask.shape

    # ── Step 0: largest connected component ───────────────────────────────
    mask_u8 = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8)
    if num_labels <= 1:
        return None
    largest    = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    clean_mask = (labels == largest).astype(np.uint8)

    ys, xs = np.where(clean_mask > 0)
    if len(ys) == 0:
        return None
    y_top  = int(ys.min())
    y_bot  = int(ys.max())
    n_rows = y_bot - y_top
    if n_rows < 10:
        return _extract_floor_quad_fallback(clean_mask)

    # ── Step 1: collect unclipped boundary pixels ──────────────────────────
    EDGE = 4
    left_pts, right_pts = [], []
    for row in range(y_top, y_bot + 1):
        cols = np.where(clean_mask[row] > 0)[0]
        if len(cols) < 2:
            continue
        if cols[0]  > EDGE:
            left_pts.append([float(cols[0]),  float(row)])
        if cols[-1] < w - 1 - EDGE:
            right_pts.append([float(cols[-1]), float(row)])

    has_left  = len(left_pts)  >= 4
    has_right = len(right_pts) >= 4

    if not has_left and not has_right:
        print("  ⚠️  No unclipped wall rows — fallback")
        return _extract_floor_quad_fallback(clean_mask)

    # ── Step 2: get vanishing point ────────────────────────────────────────
    vp = None

    # Try mask boundary VP first (most precise when valid)
    if has_left and has_right:
        vp = _mask_boundary_vp(left_pts, right_pts, y_top)
        if vp:
            print(f"  VP (mask boundary): ({vp[0]:.1f}, {vp[1]:.1f})")

    # Fallback to Hough on wall region of image
    if vp is None and image is not None:
        vp = _hough_vanishing_point(image, y_top)
        if vp:
            print(f"  VP (Hough/wall):    ({vp[0]:.1f}, {vp[1]:.1f})")

    if vp is None:
        print("  ⚠️  No reliable VP — fallback")
        return _extract_floor_quad_fallback(clean_mask)

    vp_x, vp_y = vp

    # ── Step 3: far_y and near_y from unclipped wall rows ─────────────────
    all_wall_rows = sorted(set(
        [int(p[1]) for p in left_pts] + [int(p[1]) for p in right_pts]
    ))
    far_y  = float(all_wall_rows[0])
    near_y = float(all_wall_rows[-1])

    # ── Step 4: anchor x-positions at far_y ───────────────────────────────
    def boundary_x_at_y(pts_list, y_target):
        pts  = np.array(pts_list)
        dists = np.abs(pts[:, 1] - y_target)
        idx   = np.argsort(dists)[:5]
        return float(np.median(pts[idx, 0]))

    def x_via_vp_ray(x_anchor, y_anchor, y_target):
        if abs(y_anchor - vp_y) < 1e-6:
            return x_anchor
        t = (y_target - vp_y) / (y_anchor - vp_y)
        return vp_x + t * (x_anchor - vp_x)

    fl_x_anchor = boundary_x_at_y(left_pts,  far_y) if has_left  else None
    fr_x_anchor = boundary_x_at_y(right_pts, far_y) if has_right else None

    if fl_x_anchor is None:
        fl_x_anchor = 2 * vp_x - fr_x_anchor
        print(f"  Left wall not visible — mirrored from right")
    if fr_x_anchor is None:
        fr_x_anchor = 2 * vp_x - fl_x_anchor
        print(f"  Right wall not visible — mirrored from left")

    # Project all four corners along VP rays
    fl_x = float(fl_x_anchor)
    fr_x = float(fr_x_anchor)
    nl_x = x_via_vp_ray(fl_x_anchor, far_y, near_y)
    nr_x = x_via_vp_ray(fr_x_anchor, far_y, near_y)

    near_left  = np.array([nl_x, near_y], dtype=np.float32)
    near_right = np.array([nr_x, near_y], dtype=np.float32)
    far_left   = np.array([fl_x, far_y],  dtype=np.float32)
    far_right  = np.array([fr_x, far_y],  dtype=np.float32)

    # ── Step 5: sanity check ───────────────────────────────────────────────
    near_w = nr_x - nl_x
    far_w  = fr_x - fl_x
    if near_w <= 0 or far_w <= 0 or near_w <= far_w:
        print(f"  ⚠️  Quad sanity failed (nw={near_w:.0f} fw={far_w:.0f}) — fallback")
        return _extract_floor_quad_fallback(clean_mask)

    print(f"  Quad OK  FL=({fl_x:.0f},{far_y:.0f}) FR=({fr_x:.0f},{far_y:.0f})"
          f"  NL=({nl_x:.0f},{near_y:.0f}) NR=({nr_x:.0f},{near_y:.0f})"
          f"  nw={near_w:.0f} fw={far_w:.0f}")
    return near_left, near_right, far_left, far_right


# ── Fallback ───────────────────────────────────────────────────────────────

def _extract_floor_quad_fallback(mask: np.ndarray) -> tuple:
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None

    y_near = int(ys.max())
    y_far  = int(ys.min())

    def get_edges(y_center, band=8):
        lefts, rights = [], []
        for dy in range(-band, band + 1):
            y = y_center + dy
            if 0 <= y < h:
                cols = np.where(mask[y] > 0)[0]
                if len(cols) >= 2:
                    lefts.append(int(cols[0]))
                    rights.append(int(cols[-1]))
        if not lefts:
            cols = np.where(mask[y_center] > 0)[0]
            if len(cols) < 2:
                return None, None
            return float(cols[0]), float(cols[-1])
        return float(np.median(lefts)), float(np.median(rights))

    nl, nr = get_edges(y_near, band=8)
    fl, fr = get_edges(y_far,  band=8)
    if nl is None or fl is None:
        return None

    near_left  = np.array([nl, float(y_near)], dtype=np.float32)
    near_right = np.array([nr, float(y_near)], dtype=np.float32)
    far_left   = np.array([fl, float(y_far)],  dtype=np.float32)
    far_right  = np.array([fr, float(y_far)],  dtype=np.float32)

    print(f"  Quad (fallback) NL={near_left} NR={near_right} FL={far_left} FR={far_right}")
    return near_left, near_right, far_left, far_right




def estimate_floor_geometry(near_left: np.ndarray, near_right: np.ndarray,
                             far_left: np.ndarray, far_right: np.ndarray,
                             real_width_cm: float) -> tuple:
    """Estimate VP, depth, and depth_ratio from floor quad corners.

    Returns:
        (vp_y, real_depth_cm, depth_ratio)
        where depth_ratio = real_depth_cm / real_width_cm
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
            real_depth_cm = float(np.clip(real_width_cm * abs(depth_ratio), 50.0, 600.0))
            print(f"  [geometry] vp_y={vp_y:.1f}  depth_ratio={depth_ratio:.3f}  "
                  f"depth={real_depth_cm:.1f}cm")
            return vp_y, real_depth_cm, depth_ratio

    # Fallback
    vp_y        = far_y - (near_y - far_y)
    depth_ratio = 1.0
    real_depth_cm = real_width_cm
    print(f"  [geometry fallback] depth={real_depth_cm:.1f}cm")
    return vp_y, real_depth_cm, depth_ratio