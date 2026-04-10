import numpy as np
import cv2
from typing import Tuple, Optional
from config.settings import DEPTH_MIN_CM, DEPTH_MAX_CM

def hex_to_bgr(h: str) -> tuple:
    h = h.lstrip('#')
    try:
        r, g, b = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        return (b, g, r)
    except Exception:
        return (128, 128, 128)

def _fit_line_robust(pts: list) -> Optional[tuple]:
    if len(pts) < 4:
        return None
    arr = np.array(pts, dtype=np.float32)
    line = cv2.fitLine(arr, cv2.DIST_L1, 0, 0.01, 0.01).flatten()
    return (float(line[0]), float(line[1]), float(line[2]), float(line[3]))

def _intersect_lines(l1: tuple, l2: tuple) -> Optional[tuple]:
    vx1, vy1, x01, y01 = l1
    vx2, vy2, x02, y02 = l2
    denom = vx1 * vy2 - vy1 * vx2
    if abs(denom) < 1e-06:
        return None
    t = ((x02 - x01) * vy2 - (y02 - y01) * vx2) / denom
    return (float(x01 + t * vx1), float(y01 + t * vy1))

def _collect_boundary_points(clean_mask: np.ndarray, edge_margin: int=4):
    h, w = clean_mask.shape
    left_pts, right_pts = ([], [])
    for row in range(h):
        cols = np.where(clean_mask[row] > 0)[0]
        if len(cols) < 2:
            continue
        if cols[0] > edge_margin:
            left_pts.append([float(cols[0]), float(row)])
        if cols[-1] < w - 1 - edge_margin:
            right_pts.append([float(cols[-1]), float(row)])
    return (left_pts, right_pts)

def _near_edge_from_mask(clean_mask: np.ndarray, y_near: float, band: int=20):
    h, w = clean_mask.shape
    lefts, rights = ([], [])
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
    return (float(np.median(lefts)), float(np.median(rights)))

def _far_edge_from_mask(clean_mask: np.ndarray, y_far: float, band: int=20):
    return _near_edge_from_mask(clean_mask, y_far, band)

def _compute_vp_from_boundaries(left_pts, right_pts, y_top: float, h: int, w: int) -> Optional[tuple]:
    l_line = _fit_line_robust(left_pts)
    r_line = _fit_line_robust(right_pts)
    if l_line is None or r_line is None:
        return None
    vp = _intersect_lines(l_line, r_line)
    if vp is None:
        return None
    vp_x, vp_y = vp
    if vp_y >= y_top:
        return None
    if not (-5 * w < vp_x < 6 * w and -6 * h < vp_y < y_top):
        return None
    return (float(vp_x), float(vp_y))

def _compute_horizontal_vp(image: np.ndarray, y_floor_top: float) -> Optional[float]:
    if image is None:
        return None
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(gray, 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=w // 6, maxLineGap=20)
    if lines is None:
        return None
    horiz_lines = []
    for ln in lines:
        x1, y1, x2, y2 = map(int, ln[0])
        dx, dy = (x2 - x1, y2 - y1)
        if dx == 0:
            continue
        ang = np.degrees(np.arctan2(dy, dx))
        if ang > 90:
            ang -= 180
        if ang <= -90:
            ang += 180
        if abs(ang) < 15:
            m = dy / dx
            c = y1 - m * x1
            horiz_lines.append((m, c, np.hypot(dx, dy)))
    if len(horiz_lines) < 2:
        return None
    vps_x = []
    for i in range(len(horiz_lines)):
        for j in range(i + 1, len(horiz_lines)):
            m1, c1, l1 = horiz_lines[i]
            m2, c2, l2 = horiz_lines[j]
            if abs(m1 - m2) < 0.0001:
                continue
            ix = (c2 - c1) / (m1 - m2)
            if abs(ix) < 10 * w:
                vps_x.append(ix)
    if not vps_x:
        return None
    return float(np.median(vps_x))

def _hough_vanishing_point(image: np.ndarray, y_floor_top: int) -> Optional[tuple]:
    h, w = image.shape[:2]
    wall_h = max(1, int(y_floor_top))
    roi = image[:wall_h] if wall_h >= 50 else image
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    edges = cv2.Canny(gray, 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50, minLineLength=60, maxLineGap=15)
    if lines is None:
        return None
    diag = []
    for ln in lines:
        x1, y1, x2, y2 = map(int, ln[0])
        dx, dy = (x2 - x1, y2 - y1)
        if dx == 0:
            continue
        ang = abs(np.degrees(np.arctan2(dy, dx)))
        if 12 < ang < 78:
            mid_x = (x1 + x2) / 2.0
            dist_from_center = abs(mid_x - w / 2.0)
            weight = 1 + int(dist_from_center / (w / 4.0))
            diag.extend([(x1, y1, x2, y2)] * weight)
    if len(diag) < 2:
        return None
    vps = []
    stride = max(1, len(diag) // 15)
    for i in range(0, len(diag), stride):
        for j in range(i + stride, len(diag), stride):
            x1, y1, x2, y2 = diag[i]
            x3, y3, x4, y4 = diag[j]
            d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(d) < 0.0001:
                continue
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
            ix = x1 + t * (x2 - x1)
            iy = y1 + t * (y2 - y1)
            if -w < ix < 2 * w and -2 * h < iy < y_floor_top:
                vps.append([float(ix), float(iy)])
    if len(vps) < 3:
        return None
    vpa = np.array(vps)
    med_x, med_y = (np.median(vpa[:, 0]), np.median(vpa[:, 1]))
    dist_sq = (vpa[:, 0] - med_x) ** 2 + (vpa[:, 1] - med_y) ** 2
    thresh = np.percentile(dist_sq, 60)
    best_vps = vpa[dist_sq <= thresh]
    vp = (float(np.mean(best_vps[:, 0])), float(np.mean(best_vps[:, 1])))
    return vp

def extract_floor_quad(mask: np.ndarray, image: np.ndarray=None) -> Optional[tuple]:
    h, w = mask.shape
    mask_u8 = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8)
    if num_labels <= 1:
        return None
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    clean_mask = (labels == largest).astype(np.uint8)
    ys, xs = np.where(clean_mask > 0)
    if len(ys) == 0:
        return None
    y_near = float(np.percentile(ys, 97))
    y_far = float(np.percentile(ys, 3))
    if y_near - y_far < 10:
        return _extract_floor_quad_fallback(clean_mask)
    near_edge = _near_edge_from_mask(clean_mask, y_near, band=20)
    if near_edge is None:
        return _extract_floor_quad_fallback(clean_mask)
    nl_x, nr_x = near_edge
    near_w = nr_x - nl_x
    if near_w <= 10:
        return _extract_floor_quad_fallback(clean_mask)
    
    far_edge = _far_edge_from_mask(clean_mask, y_far, band=15)
    far_cx = (far_edge[0] + far_edge[1]) / 2.0 if far_edge else (nl_x + nr_x) / 2.0

    # 1. Vanishing point for Depth (side walls)
    vp_v = None
    if image is not None:
        vp_v = _hough_vanishing_point(image, int(y_far))
    
    # Optional mask-boundary fallback for VP_v
    if vp_v is None:
        left_pts, right_pts = _collect_boundary_points(clean_mask)
        vp_v = _compute_vp_from_boundaries(left_pts, right_pts, y_far, h, w)

    if vp_v is None:
        # Absolute fallback straight ahead
        vp_v = (w / 2.0, y_far - (y_near - y_far) * 2.0)
    
    vp_vx, vp_vy = vp_v
    
    # 2. Vanishing point for Width (front wall)
    vp_u = None
    angle_deg, master_line = (0.0, None)
    if image is not None:
        angle_deg, master_line = _detect_wall_dominant_angle(image, y_far)
        
    if master_line is not None:
        m, c = master_line
        if abs(m) > 1e-4:
            horizon_y = vp_vy
            vp_ux = (horizon_y - c) / m
            vp_u = (vp_ux, horizon_y)
        else:
            vp_u = (float('inf'), vp_vy)
    else:
        vp_u = (float('inf'), vp_vy)

    # 3. Construct 4 enclosing lines that intersect at VPs
    def line_from_pts(x1, y1, x2, y2):
        if abs(x1 - x2) < 1e-5: return (1.0, 0.0, -x1)
        m = (y2 - y1) / (x2 - x1)
        c = y1 - m * x1
        return (m, -1.0, c)

    L_left = line_from_pts(vp_vx, vp_vy, nl_x, y_near)
    L_right = line_from_pts(vp_vx, vp_vy, nr_x, y_near)
    
    near_cx = (nl_x + nr_x) / 2.0
    if vp_u[0] == float('inf'):
        L_far  = (0.0, -1.0, y_far)
        L_near = (0.0, -1.0, y_near)
    else:
        L_far  = line_from_pts(vp_u[0], vp_u[1], far_cx, y_far)
        L_near = line_from_pts(vp_u[0], vp_u[1], near_cx, y_near)
        
    # 4. Intersect the 4 projective boundaries
    def intersect(L1, L2):
        a1, b1, c1 = L1
        a2, b2, c2 = L2
        det = a1*b2 - a2*b1
        if abs(det) < 1e-6: return None
        x = (b1*c2 - b2*c1) / det
        y = (a2*c1 - a1*c2) / det
        return (float(x), float(y))

    fl = intersect(L_left, L_far)
    fr = intersect(L_right, L_far)
    nl = intersect(L_left, L_near)
    nr = intersect(L_right, L_near)

    if None in (fl, fr, nl, nr):
        return _extract_floor_quad_fallback(clean_mask)

    # 5. Sanity check proportions
    top_w = np.linalg.norm(np.array(fr) - np.array(fl))
    bot_w = np.linalg.norm(np.array(nr) - np.array(nl))
    if bot_w < 10.0 or top_w / bot_w < 0.05 or top_w / bot_w > 1.2:
        return _extract_floor_quad_fallback(clean_mask)

    near_left = np.array(nl, dtype=np.float32)
    near_right = np.array(nr, dtype=np.float32)
    far_left = np.array(fl, dtype=np.float32)
    far_right = np.array(fr, dtype=np.float32)

    return (near_left, near_right, far_left, far_right)

def _extract_floor_quad_fallback(mask: np.ndarray) -> Optional[tuple]:
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None
    y_near = int(np.percentile(ys, 97))
    y_far = int(np.percentile(ys, 3))
    near_edge = _near_edge_from_mask(mask, y_near, band=15)
    if near_edge is None:
        return None
    nl, nr = near_edge
    near_w = nr - nl
    y_top20 = float(np.percentile(ys, 20))
    top_xs = xs[ys <= y_top20]
    far_cx = float(np.mean(top_xs)) if len(top_xs) else (nl + nr) / 2.0
    far_edge = _far_edge_from_mask(mask, y_far, band=15)
    far_w = far_edge[1] - far_edge[0] if far_edge else near_w * 0.4
    ratio = far_w / max(near_w, 1.0)
    MIN_R, MAX_R = (0.12, 0.88)
    if ratio < MIN_R:
        far_w = near_w * MIN_R
    elif ratio > MAX_R:
        far_w = near_w * MAX_R
    half_far = far_w / 2.0
    fl = far_cx - half_far
    fr = far_cx + half_far
    near_left = np.array([nl, float(y_near)], dtype=np.float32)
    near_right = np.array([nr, float(y_near)], dtype=np.float32)
    far_left = np.array([fl, float(y_far)], dtype=np.float32)
    far_right = np.array([fr, float(y_far)], dtype=np.float32)
    return (near_left, near_right, far_left, far_right)

def rectify_quad(near_left: np.ndarray, near_right: np.ndarray, far_left: np.ndarray, far_right: np.ndarray, mask: np.ndarray) -> tuple:
    # DEPRECATED: 1-point hack
    return (near_left, near_right, far_left, far_right)

def _detect_wall_dominant_angle(image: np.ndarray, y_floor_top: float) -> tuple:
    if image is None:
        return (0.0, None)
    h, w = image.shape[:2]
    h_floor_base = int(y_floor_top)
    img_floor = image[max(0, h_floor_base - 40):min(h, h_floor_base + 20)]
    img_ceiling = image[:max(40, h // 4)]
    angle_samples = []

    def _collect_angles(roi, weight_multiplier=1.0):
        if roi.size == 0:
            return
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        edges = cv2.Canny(gray, 25, 80)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 270, threshold=20, minLineLength=w // 20, maxLineGap=12)
        if lines is not None:
            for ln in lines:
                x1, y1, x2, y2 = map(int, ln[0])
                dx, dy = (x2 - x1, y2 - y1)
                if dx == 0:
                    continue
                ang = np.degrees(np.arctan2(dy, dx))
                if ang > 90:
                    ang -= 180
                if ang <= -90:
                    ang += 180
                if abs(ang) < 18:
                    weight = int(weight_multiplier * (np.hypot(dx, dy) / 10) ** 1.5)
                    angle_samples.extend([ang] * max(1, weight))
    _collect_angles(img_floor, weight_multiplier=2.5)
    _collect_angles(img_ceiling, weight_multiplier=1.0)
    if len(angle_samples) < 5:
        return (0.0, None)
    med = float(np.median(angle_samples))
    h_floor_base = int(y_floor_top)
    search_h = 40
    img_m = image[max(0, h_floor_base - search_h):min(h, h_floor_base + 10)]
    gray_m = cv2.cvtColor(img_m, cv2.COLOR_BGR2GRAY) if img_m.ndim == 3 else img_m
    edges_m = cv2.Canny(gray_m, 40, 150)
    lines_m = cv2.HoughLinesP(edges_m, 1, np.pi / 270, threshold=30, minLineLength=w // 8, maxLineGap=12)
    best_line = None
    if lines_m is not None:
        best_score = -1
        target_roi_y = search_h
        for ln in lines_m:
            x1, y1, x2, y2 = map(int, ln[0])
            dx, dy = (x2 - x1, y2 - y1)
            if dx == 0:
                continue
            ang = np.degrees(np.arctan2(dy, dx))
            if ang > 90:
                ang -= 180
            if ang <= -90:
                ang += 180
            length = np.hypot(dx, dy)
            consensus_match = abs(ang - med) < 3.0
            if consensus_match or length > w * 0.2:
                dist_to_floor = abs(y1 - target_roi_y)
                height_bonus = 1.6 / (1.0 + (dist_to_floor / 10.0) ** 2)
                score = length * height_bonus
                if score > best_score:
                    best_score = score
                    med = ang
                    m = dy / dx
                    c = y1 + max(0, h_floor_base - search_h) - m * x1
                    best_line = (m, c)
    return (med, best_line)

def align_quad_to_walls(near_left: np.ndarray, near_right: np.ndarray, far_left: np.ndarray, far_right: np.ndarray, image: np.ndarray, y_floor_top: float) -> tuple:
    # DEPRECATED: replaced by 2-point perspective extractor 
    return (near_left, near_right, far_left, far_right)

def estimate_floor_geometry(near_left: np.ndarray, near_right: np.ndarray, far_left: np.ndarray, far_right: np.ndarray, real_width_cm: float) -> tuple:
    x1, y1 = (float(far_left[0]), float(far_left[1]))
    x2, y2 = (float(near_left[0]), float(near_left[1]))
    x3, y3 = (float(far_right[0]), float(far_right[1]))
    x4, y4 = (float(near_right[0]), float(near_right[1]))
    near_y = (y2 + y4) / 2.0
    far_y = (y1 + y3) / 2.0
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) > 1e-06:
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        vp_y = float(y1 + t * (y2 - y1))
        denom_y = far_y - vp_y
        if abs(denom_y) > 0.001:
            depth_ratio = (near_y - far_y) / denom_y
            depth_ratio = float(np.clip(abs(depth_ratio), 0.45, 1.8))
            real_depth_cm = float(real_width_cm * depth_ratio)
            real_depth_cm = float(np.clip(real_depth_cm, DEPTH_MIN_CM, DEPTH_MAX_CM))
            return (vp_y, real_depth_cm, depth_ratio)
    vp_y = far_y - (near_y - far_y)
    depth_ratio = 1.0
    real_depth_cm = real_width_cm
    return (vp_y, real_depth_cm, depth_ratio)
