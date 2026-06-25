"""Split a single semantic 'wall' mask into individual wall planes.

Semantic segmentation labels every wall pixel the same, so a corner where two
walls meet becomes one connected blob — you can't select "the left wall" alone.

We separate the planes from a depth map.  Rather than clustering per-pixel
*normals* (which are noisy on monocular depth and fragment a flat wall into
several pieces), we fit real 3D **planes** with RANSAC and assign every wall
pixel to its nearest plane by point-to-plane distance.  Because the points of a
flat wall genuinely lie on one plane, the wall stays whole even when its normals
wander; parallel walls separate by their plane offset; perpendicular walls
separate by orientation.  Result: one physical wall → one plane id.
"""
import numpy as np
import cv2

# Camera focal as a fraction of the image's long edge, used to back-project the
# floor depth. max(h,w) alone implies ~53° FOV; phone main cameras are wider
# (~65-70°), so a smaller factor increases foreshortening and keeps metric tiles
# square instead of stretched into depth.
_FLOOR_FOCAL_FACTOR = 0.65


def depth_to_normals(depth: np.ndarray, focal: float | None = None) -> np.ndarray:
    """Per-pixel surface normals from a (metric) depth map (kept as a utility)."""
    h, w = depth.shape
    if focal is None:
        focal = float(max(h, w))
    cx, cy = w / 2.0, h / 2.0
    d = cv2.bilateralFilter(depth, d=7, sigmaColor=0.1, sigmaSpace=7)
    xs = (np.arange(w, dtype=np.float32)[None, :] - cx) / focal
    ys = (np.arange(h, dtype=np.float32)[:, None] - cy) / focal
    P = np.stack([xs * d, ys * d, d], axis=-1)
    n = np.cross(np.gradient(P, axis=1), np.gradient(P, axis=0))
    n = n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8)
    n = cv2.GaussianBlur(n.astype(np.float32), (5, 5), 0)
    return n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8)


def _backproject(xs, ys, depth, focal, cx, cy):
    """Pixel coords + depth → 3D camera-space points (N, 3)."""
    z = depth[ys, xs].astype(np.float64)
    x = (xs - cx) / focal * z
    y = (ys - cy) / focal * z
    return np.stack([x, y, z], axis=1)


def _fit_plane_lsq(pts):
    """Least-squares plane through points → (unit normal, offset d) with n·x = d."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[2]
    return n, float(n @ c)


def _fit_planes_ransac(P, max_planes, dist_thresh, min_frac, iters, rng):
    """Sequentially extract dominant planes from a point cloud with RANSAC.

    Returns a list of (unit_normal, offset) tuples.
    """
    total = len(P)
    remaining = np.ones(total, bool)
    idx_all = np.arange(total)
    planes = []
    min_inliers = max(50, int(total * min_frac))

    for _ in range(max_planes):
        rem_idx = idx_all[remaining]
        if len(rem_idx) < min_inliers:
            break
        Pr = P[rem_idx]
        best_count, best_plane = 0, None
        for _ in range(iters):
            s = rng.choice(len(Pr), 3, replace=False)
            p0, p1, p2 = Pr[s]
            nrm = np.cross(p1 - p0, p2 - p0)
            ln = np.linalg.norm(nrm)
            if ln < 1e-9:
                continue
            nrm = nrm / ln
            d = nrm @ p0
            count = int((np.abs(Pr @ nrm - d) < dist_thresh).sum())
            if count > best_count:
                best_count, best_plane = count, (nrm, d)
        if best_plane is None or best_count < min_inliers:
            break
        # Refit on the inliers for an accurate plane, then consume them.
        nrm, d = best_plane
        inl = np.abs(Pr @ nrm - d) < dist_thresh
        nrm, d = _fit_plane_lsq(Pr[inl])
        planes.append((nrm, d))
        consumed = rem_idx[np.abs(Pr @ nrm - d) < dist_thresh]
        remaining[consumed] = False
    return planes


def _merge_coplanar(planes, ang_cos=0.985, doff=0.06):
    """Fuse planes that are effectively the same surface (same normal + offset)."""
    merged = []
    for n, d in planes:
        placed = False
        for i, (n2, d2) in enumerate(merged):
            dot = float(n @ n2)
            # A plane and its sign-flipped version describe the same surface.
            n2s, d2s = (n2, d2) if dot >= 0 else (-n2, -d2)
            if abs(dot) >= ang_cos and abs(d - d2s) <= doff:
                nm = n + n2s
                nm = nm / (np.linalg.norm(nm) + 1e-9)
                merged[i] = (nm, (d + d2s) * 0.5)
                placed = True
                break
        if not placed:
            merged.append((n, d))
    return merged


def split_wall_planes(
    wall_mask: np.ndarray,
    depth: np.ndarray,
    min_area: int = 500,
    max_planes: int = 6,
    dist_frac: float = 0.03,
    ransac_iters: int = 200,
) -> tuple[np.ndarray, int]:
    """Label individual wall planes within ``wall_mask`` using depth.

    Args:
        wall_mask:  binary uint8 [H, W] of all wall pixels.
        depth:      float32 [H, W] depth map (same size).
        min_area:   drop planes smaller than this many pixels.
        max_planes: maximum number of planes to extract.
        dist_frac:  RANSAC inlier band as a fraction of the median depth
                    (scale-invariant, so it works whatever the depth units are).
        ransac_iters: RANSAC iterations per plane.

    Returns:
        (labeled, n) where ``labeled`` is uint8 [H, W] with each plane a
        distinct id 1..n (0 = background), and ``n`` the plane count.
    """
    wall_mask = (wall_mask > 0).astype(np.uint8)
    h, w = wall_mask.shape

    def _fallback():
        n, lab = cv2.connectedComponents(wall_mask, connectivity=8)
        return lab.astype(np.uint8), max(n - 1, 0)

    ys, xs = np.where(wall_mask > 0)
    if len(xs) < min_area:
        return _fallback()

    focal = float(max(h, w))
    cx, cy = w / 2.0, h / 2.0
    P = _backproject(xs, ys, depth, focal, cx, cy)

    median_z = float(np.median(P[:, 2]))
    dist_thresh = max(1e-3, dist_frac * abs(median_z))

    # ── Fit planes on a subsample (fast), then assign ALL pixels ────────────
    rng = np.random.default_rng(12345)  # deterministic → stable across runs
    sub = P if len(P) <= 6000 else P[rng.choice(len(P), 6000, replace=False)]
    planes = _fit_planes_ransac(sub, max_planes, dist_thresh, 0.06, ransac_iters, rng)
    planes = _merge_coplanar(planes, doff=dist_thresh * 1.5)
    if not planes:
        return _fallback()

    n_stack = np.array([n for n, _ in planes])          # (K, 3)
    d_stack = np.array([d for _, d in planes])          # (K,)

    # ── Assign by RAY-CASTING (not per-pixel depth distance) ────────────────
    # For each wall pixel, shoot the camera ray and pick the nearest plane it
    # hits *in front* of the camera.  Because this depends only on the fitted
    # plane equations (not the noisy per-pixel depth), the boundary between two
    # planes is their projected 3D intersection — a genuine STRAIGHT line.
    R = np.stack([(xs - cx) / focal, (ys - cy) / focal, np.ones_like(xs, dtype=np.float64)], axis=1)
    den = R @ n_stack.T                                  # (N, K)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = d_stack[None, :] / den                      # ray depth to each plane
    t[~np.isfinite(t)] = np.inf
    t[t <= 1e-6] = np.inf                                # plane behind camera
    # Fallback for pixels whose ray misses every plane: nearest by distance,
    # but always preferred *after* any genuine hit.
    D = np.abs(P @ n_stack.T - d_stack[None, :])
    finite = np.isfinite(t)
    big = float(t[finite].max()) if finite.any() else 1.0
    cost = np.where(finite, t, big * 10.0 + D)          # (N, K)

    # Drop planes that end up too small, reassigning their pixels to the next plane.
    keep = list(range(len(planes)))
    while True:
        li = np.argmin(cost[:, keep], axis=1)
        counts = np.bincount(li, minlength=len(keep))
        smallest = int(np.argmin(counts))
        if counts[smallest] >= min_area or len(keep) <= 1:
            final = np.asarray(keep)[li]
            break
        keep.pop(smallest)

    labeled = np.zeros((h, w), np.uint8)
    labeled[ys, xs] = (final + 1).astype(np.uint8)
    labeled[wall_mask == 0] = 0

    # Relabel to a contiguous 1..n.
    ids = [i for i in np.unique(labeled) if i != 0]
    if not ids:
        return wall_mask.copy(), 1
    remap = {old: new for new, old in enumerate(ids, start=1)}
    out = np.zeros_like(labeled)
    for old, new in remap.items():
        out[labeled == old] = new
    return out, len(ids)


def floor_plane_uv(mask, depth, tile_w_m, tile_h_m, manhattan_angle=None):
    """Per-pixel tile coordinates (u, v) for the floor — depth plane + homography.

    Depth gives a ROBUST floor plane (fit to thousands of points, no fragile
    vanishing-point/line detection). From that plane + the camera intrinsics we
    build the exact plane->image **homography** and invert it, so the tile grid is
    a true projective map -> grout lines are mathematically straight, with
    perspective from the real plane and tile size in real metres (depth is metric).

    The in-plane axes are oriented so one runs "into the room" (camera forward
    projected onto the floor), which tends to align the grid with the walls.

    Returns (u_all, v_all) float64 [H, W] in tile units, or ``None`` if the plane
    can't be fit.
    """
    h, w = depth.shape
    focal = float(_FLOOR_FOCAL_FACTOR * max(h, w))
    cx, cy = w / 2.0, h / 2.0

    ys, xs = np.mgrid[0:h, 0:w]
    Z = depth.astype(np.float64)
    m = mask > 0
    if int(m.sum()) < 100:
        return None
    zf = Z[m]
    xf = (xs[m] - cx) / focal * zf
    yf = (ys[m] - cy) / focal * zf
    fp = np.stack([xf, yf, zf], axis=1)
    c = fp.mean(axis=0)
    try:
        _, _, vt = np.linalg.svd(fp - c, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    normal = vt[2]

    # In-plane axes: one ~ "into the room" (camera forward projected on the floor).
    fwd = np.array([0.0, 0.0, 1.0])
    v_axis = fwd - (fwd @ normal) * normal
    nv = np.linalg.norm(v_axis)
    v_axis = vt[0] if nv < 1e-6 else v_axis / nv
    u_axis = np.cross(normal, v_axis)
    u_axis = u_axis / (np.linalg.norm(u_axis) + 1e-8)

    # Plane->image homography from intrinsics: pixel ~ K * (c + s*u + t*v).
    K = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]])
    H_fwd = np.column_stack([K @ u_axis, K @ v_axis, K @ c])
    try:
        H_inv = np.linalg.inv(H_fwd)
    except np.linalg.LinAlgError:
        return None

    img = np.stack(
        [xs.ravel().astype(np.float64), ys.ravel().astype(np.float64), np.ones(h * w)],
        axis=1,
    )
    st = img @ H_inv.T
    wdiv = np.where(np.abs(st[:, 2]) < 1e-9, 1e-9, st[:, 2])
    s = (st[:, 0] / wdiv).reshape(h, w)
    t = (st[:, 1] / wdiv).reshape(h, w)

    # Rotate the grid to the room's dominant axis (radians, in this camera-forward
    # plane basis) — e.g. from M-LSD line-segment fusion. None → camera-forward.
    if manhattan_angle is not None:
        ca, sa = np.cos(manhattan_angle), np.sin(manhattan_angle)
        s, t = s * ca + t * sa, -s * sa + t * ca

    return s / max(tile_w_m, 1e-4), t / max(tile_h_m, 1e-4)


def _fold90(theta):
    """Fold an angle into (-45°, 45°] — grid lines are 90°-symmetric."""
    return np.arctan2(np.sin(4.0 * theta), np.cos(4.0 * theta)) / 4.0


def _near90(a, b):
    """Angular distance between two directions, accounting for 90° symmetry."""
    d = abs(a - b) % (np.pi / 2.0)
    return min(d, np.pi / 2.0 - d)


def _camera_forward_frame(mask, depth):
    """Floor plane + camera-forward in-plane basis + plane->image H_inv, or None."""
    h, w = depth.shape
    focal = float(_FLOOR_FOCAL_FACTOR * max(h, w))
    cx, cy = w / 2.0, h / 2.0
    ys, xs = np.mgrid[0:h, 0:w]
    Z = depth.astype(np.float64)
    m = mask > 0
    if int(m.sum()) < 100:
        return None
    zf = Z[m]
    xf = (xs[m] - cx) / focal * zf
    yf = (ys[m] - cy) / focal * zf
    fp = np.stack([xf, yf, zf], axis=1)
    c = fp.mean(axis=0)
    try:
        _, _, vt = np.linalg.svd(fp - c, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    normal = vt[2]
    fwd = np.array([0.0, 0.0, 1.0])
    v_axis = fwd - (fwd @ normal) * normal
    nv = np.linalg.norm(v_axis)
    v_axis = vt[0] if nv < 1e-6 else v_axis / nv
    u_axis = np.cross(normal, v_axis)
    u_axis = u_axis / (np.linalg.norm(u_axis) + 1e-8)
    K = np.array([[focal, 0.0, cx], [0.0, focal, cy], [0.0, 0.0, 1.0]])
    try:
        H_inv = np.linalg.inv(np.column_stack([K @ u_axis, K @ v_axis, K @ c]))
    except np.linalg.LinAlgError:
        return None
    return {"h": h, "w": w, "H_inv": H_inv}


def _segments_angle(segments, mask, H_inv):
    """Dominant grid angle from M-LSD segments → (angle, confidence) or (None, 0)."""
    if segments is None or len(segments) == 0:
        return None, 0.0
    h, w = mask.shape
    md = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8))
    C = S = tot = 0.0
    for x1, y1, x2, y2 in np.asarray(segments, dtype=np.float64).reshape(-1, 4):
        mx, my = int((x1 + x2) / 2), int((y1 + y2) / 2)
        if not (0 <= my < h and 0 <= mx < w and md[my, mx]):
            continue  # keep only segments on/near the floor
        p1 = H_inv @ np.array([x1, y1, 1.0])
        p2 = H_inv @ np.array([x2, y2, 1.0])
        if abs(p1[2]) < 1e-9 or abs(p2[2]) < 1e-9:
            continue
        d = p2[:2] / p2[2] - p1[:2] / p1[2]
        if np.hypot(d[0], d[1]) < 1e-6:
            continue
        th = np.arctan2(d[1], d[0])
        wt = float(np.hypot(x2 - x1, y2 - y1))  # weight by on-screen length
        C += wt * np.cos(4.0 * th)
        S += wt * np.sin(4.0 * th)
        tot += wt
    if tot < 1e-6:
        return None, 0.0
    return np.arctan2(S, C) / 4.0, float(np.hypot(C, S) / tot)


def _quad_angle(quad, H_inv):
    """Grid angle from the floor quad's near edge (∥ front wall) → angle or None."""
    if quad is None:
        return None
    nl, nr = np.asarray(quad[0], dtype=np.float64), np.asarray(quad[1], dtype=np.float64)
    p1 = H_inv @ np.array([nl[0], nl[1], 1.0])
    p2 = H_inv @ np.array([nr[0], nr[1], 1.0])
    if abs(p1[2]) < 1e-9 or abs(p2[2]) < 1e-9:
        return None
    d = p2[:2] / p2[2] - p1[:2] / p1[2]
    if np.hypot(d[0], d[1]) < 1e-6:
        return None
    return _fold90(np.arctan2(d[1], d[0]))


def floor_orientation_angle(mask, depth, segments=None, quad=None,
                            min_confidence=0.45, agree_deg=12.0):
    """Fuse cues into the floor-grid orientation (rad, camera-forward basis).

    Multi-cue vote so no single estimator's failure skews the grid:
      - M-LSD line segments → precise vanishing angle (+ confidence).
      - Floor quad near edge → reliable geometric anchor (∥ the front wall).

    Rule: trust M-LSD when it's confident AND agrees with the quad; otherwise
    fall back to the quad; then to M-LSD-if-confident; else None (camera-forward).
    """
    fr = _camera_forward_frame(mask, depth)
    if fr is None:
        return None
    H_inv = fr["H_inv"]
    phi_mlsd, conf = _segments_angle(segments, mask, H_inv)
    phi_quad = _quad_angle(quad, H_inv)

    if phi_mlsd is not None and conf >= min_confidence and (
        phi_quad is None or _near90(phi_mlsd, phi_quad) < np.radians(agree_deg)
    ):
        return _fold90(phi_mlsd)
    if phi_quad is not None:
        return phi_quad
    if phi_mlsd is not None and conf >= min_confidence:
        return _fold90(phi_mlsd)
    return None


__all__ = [
    "depth_to_normals",
    "split_wall_planes",
    "floor_plane_uv",
    "floor_orientation_angle",
]
