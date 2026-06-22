"""Edge-aware refinement of segmentation masks.

Mask2Former outputs are low-resolution and upsampled, so their boundaries are
blocky/jagged and rarely follow the real architectural lines (wall↔ceiling,
window frames, curtain edges).  Painting/tiling those masks directly shows
ragged edges.  We clean each mask up (morphology + hole fill) and then snap its
boundary to the photo's real edges with a guided filter, so the painted region
ends exactly where the eye expects it.
"""
import cv2
import numpy as np


def _fill_holes(m: np.ndarray) -> np.ndarray:
    """Fill interior holes of a binary mask (e.g. a switch plate on a wall).

    The mask is padded with a 0 border first so the flood always starts on real
    background — important because a surface (e.g. the ceiling) can touch the
    image corner, which would otherwise make the flood seed land on foreground.
    """
    h, w = m.shape
    big = np.zeros((h + 2, w + 2), np.uint8)
    big[1:-1, 1:-1] = m
    ff = big.copy()
    pad = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(ff, pad, (0, 0), 1)  # flood the (guaranteed bg) outside border
    holes = ff == 0  # zeros not reached from the border = interior holes
    out = big.copy()
    out[holes] = 1
    return out[1:-1, 1:-1]


def _straighten(
    mask: np.ndarray,
    eps_frac: float = 0.01,
    min_area: int = 200,
    max_grow: int = 5,
) -> np.ndarray:
    """Straighten region boundaries WITHOUT bridging real openings.

    Polygon-approximates each region (and its holes) so wall↔ceiling, wall↔floor
    and window/door edges become straight segments — but the result is then
    clamped to within ``max_grow`` px of the original mask, so the straightening
    can only tidy small jaggies. It can never draw a straight line across a
    doorway, window, or the gap between cabinets (those are far wider than a few
    px), which would otherwise paint non-wall pixels.
    """
    m = (mask > 0).astype(np.uint8)
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts or hier is None:
        return m
    out = np.zeros_like(m)
    hier = hier[0]
    # Fill external contours (straightened), then carve straightened holes.
    for is_hole in (False, True):
        for i, c in enumerate(cnts):
            hole = hier[i][3] != -1
            if hole != is_hole or cv2.contourArea(c) < min_area:
                continue
            approx = cv2.approxPolyDP(c, eps_frac * cv2.arcLength(c, True), True)
            cv2.drawContours(out, [approx], -1, 0 if is_hole else 1, thickness=cv2.FILLED)
    # Clamp the change to a few px of the original boundary: this still smooths
    # jaggies (and lets a wall meet its neighbour to close hairline gaps), but
    # forbids bridging genuine openings/objects.
    grow = max(1, max_grow)
    allow = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    return cv2.bitwise_and(out, allow)


def refine_mask(
    mask: np.ndarray,
    image: np.ndarray,
    single_region: bool = False,
    straighten: bool = False,
) -> np.ndarray:
    """Return a cleaned, edge-aligned binary version of ``mask``.

    Args:
        mask:          Binary-ish mask [H, W] (any non-zero = foreground).
        image:         BGR image used as the edge guide.
        single_region: If True, keep only the largest blob and fill holes
                       (use for floor / ceiling — one contiguous surface).
    """
    h, w = mask.shape[:2]
    m = (mask > 0).astype(np.uint8)
    if not m.any():
        return m

    # ── Morphological cleanup: drop specks, close small gaps ────────────────
    k = max(3, min(h, w) // 200) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
    if not m.any():
        return m

    if single_region:
        # Drop only tiny speckle components (keep every sizeable patch — a
        # floor/ceiling is often split into pieces by furniture/fittings) and
        # fill interior holes.
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n > 2:
            total = int(m.sum())
            keep = np.zeros_like(m)
            for i in range(1, n):
                if stats[i, cv2.CC_STAT_AREA] >= 0.03 * total:
                    keep[lab == i] = 1
            m = keep if keep.any() else m
        m = _fill_holes(m)

    # ── Edge-aware boundary snap (guided filter) ────────────────────────────
    # The guide is the photo, so the soft boundary follows real image edges;
    # re-thresholding gives a smooth mask aligned to the architecture.
    radius = max(4, min(h, w) // 100)
    eps = (0.06 * 255) ** 2  # edge-preserving strength for an 8-bit guide
    soft = cv2.ximgproc.guidedFilter(
        image, m.astype(np.float32), radius, eps
    )
    m = (soft > 0.5).astype(np.uint8)

    # ── Straighten boundaries to match real architectural lines ─────────────
    if straighten:
        m = _straighten(m)
    return m


def snap_mask_to_lines(
    mask: np.ndarray,
    segments,
    angle_tol: float = 10.0,
    dist_frac: float = 0.02,
    min_line_frac: float = 0.08,
    max_move_frac: float = 0.03,
) -> np.ndarray:
    """Straighten a mask's boundary onto detected straight lines (e.g. M-LSD).

    The boundary is polygon-approximated; each edge that runs close and parallel
    to a long detected line adopts that line as its support, and every vertex is
    recomputed as the intersection of its two adjacent support lines. Moves are
    clamped (``max_move_frac``) so a bad match can't distort the shape — edges
    with no nearby line keep their original direction. This removes the wavy
    boundaries on textureless walls without bridging real openings.
    """
    h, w = mask.shape
    m = (mask > 0).astype(np.uint8)
    if segments is None or len(segments) == 0 or not m.any():
        return m
    diag = float(max(h, w))
    Tdist, minlen, max_move = dist_frac * diag, min_line_frac * diag, max_move_frac * diag

    lines = []  # (point, unit_dir, angle_deg)
    for seg in np.asarray(segments, dtype=np.float64).reshape(-1, 4):
        d = seg[2:] - seg[:2]
        L = np.hypot(d[0], d[1])
        if L < minlen:
            continue
        lines.append((seg[:2], d / L, np.degrees(np.arctan2(d[1], d[0])) % 180.0))
    if not lines:
        return m

    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(m)
    used_lines = []  # architectural lines an edge actually snapped to
    for c in cnts:
        if cv2.contourArea(c) < 0.004 * h * w:
            continue
        poly = cv2.approxPolyDP(c, 0.008 * cv2.arcLength(c, True), True).reshape(-1, 2).astype(np.float64)
        n = len(poly)
        if n < 3:
            cv2.drawContours(out, [c], -1, 1, cv2.FILLED)
            continue
        # Support line per edge (snapped to a matching detected line if close).
        supports = []
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            d = b - a
            L = np.hypot(d[0], d[1])
            u = d / L if L > 1e-6 else np.array([1.0, 0.0])
            eang = np.degrees(np.arctan2(d[1], d[0])) % 180.0
            mid = (a + b) / 2.0
            best, bestd, matched = (a, u), Tdist, False
            for (p0, lu, lang) in lines:
                da = abs(eang - lang) % 180.0
                da = min(da, 180.0 - da)
                if da > angle_tol:
                    continue
                dist = abs(float(np.cross(lu, mid - p0)))
                if dist < bestd:
                    bestd, best, matched = dist, (p0, lu), True
            supports.append(best)
            if matched:
                used_lines.append(best)
        # Each vertex = intersection of its two adjacent support lines (clamped).
        new = poly.copy()
        for i in range(n):
            p_prev, u_prev = supports[(i - 1) % n]
            p_cur, u_cur = supports[i]
            denom = u_prev[0] * (-u_cur[1]) - u_prev[1] * (-u_cur[0])
            if abs(denom) < 1e-6:
                continue
            rhs = p_cur - p_prev
            t = (rhs[0] * (-u_cur[1]) - rhs[1] * (-u_cur[0])) / denom
            pt = p_prev + t * u_prev
            if np.hypot(pt[0] - poly[i][0], pt[1] - poly[i][1]) <= max_move:
                new[i] = pt
        cv2.drawContours(out, [np.round(new).astype(np.int32)], -1, 1, cv2.FILLED)

    # ── Apply the straightening ONLY near real architectural lines ──────────
    # The polygon rebuild above coarsens the *whole* boundary, which mangles
    # intricate silhouettes (plants, decor) and leaves unpainted slivers around
    # them. So keep the snapped result only inside a thin band around the lines
    # that were actually matched (wall↔ceiling/floor, corners) and fall back to
    # the original mask everywhere else.
    if not used_lines:
        return m
    band = np.zeros_like(m)
    tline = max(2, int(round(max_move)))
    for (p0, lu) in used_lines:
        p1 = (p0 - lu * diag * 2.0).astype(np.int32)
        p2 = (p0 + lu * diag * 2.0).astype(np.int32)
        cv2.line(band, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 1, thickness=2 * tline)
    return np.where(band > 0, out, m).astype(np.uint8)


def fill_surface_gaps(
    floor: np.ndarray,
    wall_labeled: np.ndarray,
    ceiling: np.ndarray,
    max_gap: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Close the thin unpainted bands BETWEEN adjacent surfaces.

    The wall/floor/ceiling masks are detected independently, so their shared
    edges often leave a hairline strip belonging to none of them — which shows
    as an unpainted sliver after painting.  We morphologically close the *union*
    of the three surfaces (which fills only narrow gaps, never an opening as wide
    as a door/window) and assign each newly-filled pixel to its nearest surface.

    Returns refined (floor, wall_labeled, ceiling).
    """
    floor = (floor > 0).astype(np.uint8)
    ceiling = (ceiling > 0).astype(np.uint8)
    wl = wall_labeled.copy()

    occ = ((floor > 0) | (wl > 0) | (ceiling > 0)).astype(np.uint8)
    k = 2 * max_gap + 1
    closed = cv2.morphologyEx(
        occ, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    )
    newpix = (closed > 0) & (occ == 0)
    if not newpix.any():
        return floor, wl, ceiling

    surfaces = [("floor", floor), ("ceiling", ceiling)]
    for wid in [int(i) for i in np.unique(wl) if i != 0]:
        surfaces.append((("wall", wid), (wl == wid).astype(np.uint8)))

    best = np.full(floor.shape, np.inf, np.float32)
    choice = np.full(floor.shape, -1, np.int32)
    for idx, (_key, m) in enumerate(surfaces):
        dist = cv2.distanceTransform(1 - m, cv2.DIST_L2, 3)
        upd = newpix & (dist < best)
        best[upd] = dist[upd]
        choice[upd] = idx

    for idx, (key, _m) in enumerate(surfaces):
        sel = newpix & (choice == idx)
        if not sel.any():
            continue
        if key == "floor":
            floor[sel] = 1
        elif key == "ceiling":
            ceiling[sel] = 1
        else:
            wl[sel] = key[1]
    return floor, wl, ceiling


def grow_walls_to_objects(
    wall_labeled: np.ndarray,
    floor: np.ndarray,
    ceiling: np.ndarray,
    objects: np.ndarray,
    grow_px: int = 18,
) -> np.ndarray:
    """Extend wall planes into the unpainted gaps around objects.

    Segmentation leaves a "no-man's-land" of wall pixels belonging to nothing —
    the tile between the wall mask and an object, or wall the model simply
    missed — which paints as an unpainted band/halo.  We grow the wall labels
    into any unclassified pixel within ``grow_px``, bounded by floor, ceiling and
    the (TIGHT) object mask, so paint reaches right up to objects without
    covering them.  Newly-filled pixels take their nearest wall plane's id.

    Args:
        objects: TIGHT object mask (no exclusion dilation) — the grow stops here,
                 so a dilated mask would re-introduce the halo it's meant to fix.
    """
    wl = wall_labeled.copy()
    walls = (wl > 0).astype(np.uint8)
    if not walls.any():
        return wl

    forbidden = (floor > 0) | (ceiling > 0) | (objects > 0)
    region = (~forbidden) & (wl == 0)  # paintable but currently unassigned
    grown = cv2.dilate(walls, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1)))
    newpix = (grown > 0) & region
    if not newpix.any():
        return wl

    best = np.full(wl.shape, np.inf, np.float32)
    choice = np.full(wl.shape, -1, np.int32)
    for wid in [int(i) for i in np.unique(wl) if i != 0]:
        dist = cv2.distanceTransform((wl != wid).astype(np.uint8), cv2.DIST_L2, 3)
        upd = newpix & (dist < best)
        best[upd] = dist[upd]
        choice[upd] = wid
    for wid in [int(i) for i in np.unique(wl) if i != 0]:
        wl[newpix & (choice == wid)] = wid
    return wl


__all__ = ["refine_mask", "fill_surface_gaps", "snap_mask_to_lines", "grow_walls_to_objects"]
