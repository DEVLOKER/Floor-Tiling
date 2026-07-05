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


def color_coherence_expand(
    wall_mask: np.ndarray,
    image: np.ndarray,
    forbidden: np.ndarray,
    soft_forbidden: np.ndarray = None,
    hue_tol: float = 22.0,
    sat_tol: float = 0.35,
    val_tol: float = 0.45,
    grout_bridge_px: int = 9,
) -> np.ndarray:
    """Grow the wall mask over all connected same-colored area (grout-robust).

    Semantic segmentation leaves gaps on uniformly-tiled walls (kitchen,
    bathroom): whole tiles above cabinets, around window frames and in corners
    are missed even though they share the wall's dominant color.

    A naive per-pixel flood dies at the grey/white grout lines between tiles —
    those pixels fail the color match, so the frontier can't reach the next
    tile.  We fix that in three steps:

      1. Build a color-match map (HSV within tolerance of the wall's median).
      2. Morphologically CLOSE it by ``grout_bridge_px`` so adjacent tiles merge
         across their grout lines into one region.
      3. Keep only the closed regions that TOUCH the existing wall mask (via
         connected components), minus the forbidden set.

    Args:
        wall_mask:       Binary wall mask before expansion.
        image:           BGR image (color guide).
        forbidden:       HARD block — never becomes wall (objects, and on neutral
                         walls also floor+ceiling).
        soft_forbidden:  SOFT block — floor/ceiling that MAY be reclaimed as wall
                         if the pixel STRONGLY matches the wall colour.  This
                         recovers green tile rows that the ceiling/floor
                         segmentation wrongly claimed (the junction halo), while
                         the tighter threshold rejects desaturated colour-bounce
                         (e.g. green light tint on a white ceiling).
        hue_tol:         Hue tolerance in degrees (OpenCV H is 0-180).
        sat_tol:         Saturation tolerance [0, 1].
        val_tol:         Value tolerance [0, 1].
        grout_bridge_px: Morphological-close radius to bridge grout lines.
    """
    m = (wall_mask > 0).astype(np.uint8)
    forb = (forbidden > 0)
    if not m.any():
        return m

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    Hc = hsv[:, :, 0]
    Sc = hsv[:, :, 1] / 255.0
    Vc = hsv[:, :, 2] / 255.0

    wall_px = m > 0
    med_h = float(np.median(Hc[wall_px]))
    med_s = float(np.median(Sc[wall_px]))
    med_v = float(np.median(Vc[wall_px]))

    # Skip near-achromatic walls (grey/white/beige): color matching is
    # unreliable and would bleed into ceiling/floor.
    if med_s < 0.15:
        return m

    # 1. Color-match map (circular hue distance)
    dh = np.abs(Hc - med_h)
    dh = np.minimum(dh, 180.0 - dh)
    color_match = (
        (dh <= hue_tol) & (np.abs(Sc - med_s) <= sat_tol) & (np.abs(Vc - med_v) <= val_tol)
    ).astype(np.uint8)

    # Strong match (tighter) — used to reclaim soft-forbidden pixels only.
    strong_match = (
        (dh <= hue_tol * 0.7)
        & (np.abs(Sc - med_s) <= sat_tol * 0.55)
        & (np.abs(Vc - med_v) <= val_tol * 0.7)
    )

    # Always include what was already detected (grout inside a tile run counts)
    color_match = np.maximum(color_match, m)
    color_match[forb] = 0  # hard-forbidden never becomes wall

    # Soft-forbidden (floor/ceiling): block UNLESS strongly wall-coloured.
    soft = (soft_forbidden > 0) if soft_forbidden is not None else np.zeros_like(forb)
    block_soft = soft & (~strong_match)
    color_match[block_soft] = 0

    # 2. Close across grout lines so neighbouring tiles merge into one region
    kb = 2 * grout_bridge_px + 1
    closed = cv2.morphologyEx(
        color_match, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kb, kb)),
    )
    closed[forb] = 0
    closed[block_soft] = 0

    # 3. Keep only closed regions that touch the existing wall mask
    n, lab = cv2.connectedComponents(closed, connectivity=8)
    if n <= 1:
        return m
    touch = set(np.unique(lab[wall_px]).tolist()) - {0}
    result = np.isin(lab, list(touch)).astype(np.uint8)

    # Guarantee we never lose originally-detected wall, never keep hard/soft-blocked
    result = np.maximum(result, m)
    result[forb] = 0
    result[block_soft] = 0
    return result.astype(np.uint8)


def infer_wall_behind_furniture(
    wall_mask: np.ndarray,
    floor_mask: np.ndarray,
    ceiling_mask: np.ndarray,
    image_h: int,
    min_wall_strip_h: float = 0.04,
) -> np.ndarray:
    """Recover wall pixels in the horizontal band occluded by counters / cabinets.

    Kitchen and bathroom photos almost always have a horizontal zone where
    furniture (counters, cabinets) sits against the wall.  The segmentation model
    sees only the furniture top and labels nothing between it and the detected
    wall above — leaving a gap.  This function fills that gap column-by-column:

    For each image column that has wall pixels both above AND below (or floor below
    and wall above), it fills the unclassified band between them as wall, capped
    to ``min_wall_strip_h × image_h`` pixels so it never crosses a real opening.
    """
    m   = (wall_mask   > 0).astype(np.uint8)
    flo = (floor_mask  > 0)
    cei = (ceiling_mask > 0)
    h, w = m.shape
    max_gap = int(min_wall_strip_h * image_h) * 4  # generous — a tall cabinet is ~40% h

    result = m.copy()

    for x in range(w):
        col_wall = np.where(m[:, x] > 0)[0]
        if len(col_wall) < 2:
            continue
        top_wall = int(col_wall.min())
        bot_wall = int(col_wall.max())
        span = slice(top_wall, bot_wall + 1)

        # Only fill the internal gap (unclassified pixels between wall pixels).
        gap_col = m[span, x] == 0
        gap_size = int(gap_col.sum())
        if gap_size == 0 or gap_size > max_gap:
            continue
        # Never bridge across a real floor or ceiling pixel — that would paint
        # over the floor / ceiling. Furniture (unclassified) is the only thing
        # we're allowed to fill behind.
        if flo[span, x].any() or cei[span, x].any():
            continue
        result[span, x] = 1

    return result.astype(np.uint8)


def derive_wall_by_complement(
    floor: np.ndarray,
    ceiling: np.ndarray,
    exclude: np.ndarray,
    shape_hw: tuple,
    min_area_frac: float = 0.004,
    open_frac: float = 1 / 300,
) -> np.ndarray:
    """Define walls as the COMPLEMENT of everything else.

        wall = image − floor − ceiling − objects − openings

    This is fundamentally more robust than detecting walls directly: whatever
    the segmenter can't confidently name (tiled walls, textured walls, unusual
    colours) simply falls through to "wall" instead of being dropped.  Coverage
    is complete BY CONSTRUCTION — the wall reaches exactly to the floor / ceiling
    / object boundaries, so there are no gaps or colour halos to patch.

    The trade-off shifts entirely to floor / ceiling / object recall: a MISSED
    floor/ceiling/object becomes wall (and would be painted), so those masks
    should be biased toward over-detection upstream.

    Args:
        floor:         Binary floor mask.
        ceiling:       Binary ceiling mask.
        exclude:       Union of everything else not to paint (objects+openings).
        shape_hw:      (H, W) of the image.
        min_area_frac: Drop wall components smaller than this fraction of the image
                       (removes isolated speckle left between excluded regions).
        open_frac:     Morphological-open radius as a fraction of the short side
                       (cleans thin slivers along object edges).

    Returns:
        Binary uint8 wall mask [H, W].
    """
    h, w = shape_hw
    not_wall = (floor > 0) | (ceiling > 0) | (exclude > 0)
    wall = (~not_wall).astype(np.uint8)

    # Clean thin slivers (e.g. 1-px gaps between two excluded regions)
    k = max(3, int(min(h, w) * open_frac)) | 1
    wall = cv2.morphologyEx(
        wall, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    )
    if not wall.any():
        return wall

    # Keep only significant components (drop noise pockets)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(wall, connectivity=8)
    thr = min_area_frac * h * w
    keep = np.zeros_like(wall)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= thr:
            keep[lab == i] = 1
    return keep.astype(np.uint8)


def wall_is_chromatic(wall_mask: np.ndarray, image: np.ndarray, sat_thresh: float = 0.25) -> bool:
    """True if the detected wall is a saturated color (tiled/painted), not neutral.

    On chromatic walls, color is a stronger separator than the object masks, so
    the pipeline can trust color-coherence expansion and use TIGHT (undilated)
    object exclusion — avoiding the green halo a dilated exclusion leaves around
    windows and cabinets.
    """
    m = wall_mask > 0
    if not m.any():
        return False
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return float(np.median(hsv[:, :, 1][m]) / 255.0) >= sat_thresh


def strip_wall_color_from_objects(
    obj_mask: np.ndarray,
    wall_mask: np.ndarray,
    image: np.ndarray,
    hue_tol: float = 16.0,
    sat_tol: float = 0.22,
    val_tol: float = 0.32,
) -> np.ndarray:
    """Remove wall-coloured pixels from the object exclusion mask (chromatic walls).

    Open-vocab detectors + SAM often over-segment thin fixtures (a pipe, its cast
    shadow, and a band of surrounding tile) into one blob.  On a chromatic wall
    that band is really wall, so excluding it leaves an unpainted colour strip
    around the fixture.  Since the wall has a distinctive colour, we keep only the
    object pixels that DON'T match it — the genuine fixture (black pipe, white
    frame, wood cabinet) stays excluded while the tile it grabbed is released
    back to the wall.

    Uses a TIGHT colour tolerance so only clearly-wall-coloured pixels are freed.
    """
    obj = (obj_mask > 0).astype(np.uint8)
    wall = wall_mask > 0
    if not obj.any() or not wall.any():
        return obj

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    Hc, Sc, Vc = hsv[:, :, 0], hsv[:, :, 1] / 255.0, hsv[:, :, 2] / 255.0
    med_h = float(np.median(Hc[wall]))
    med_s = float(np.median(Sc[wall]))
    med_v = float(np.median(Vc[wall]))
    if med_s < 0.15:
        return obj  # neutral wall — don't touch objects

    dh = np.abs(Hc - med_h)
    dh = np.minimum(dh, 180.0 - dh)
    wall_colored = (
        (dh <= hue_tol) & (np.abs(Sc - med_s) <= sat_tol) & (np.abs(Vc - med_v) <= val_tol)
    )
    return (obj & ~wall_colored).astype(np.uint8)


def close_wall_halos(
    wall_labeled: np.ndarray,
    floor: np.ndarray,
    ceiling: np.ndarray,
    objects: np.ndarray,
    grow_px: int = 12,
    junction_px: int = 7,
) -> np.ndarray:
    """Eliminate thin unpainted strips at wall boundaries (junction halos).

    Even a well-detected wall usually stops a few px short of the real
    architectural line (wall↔ceiling, wall↔floor, corners), leaving a thin strip
    of the ORIGINAL wall visible after painting — a coloured "halo" around the
    repaint.  We close it by growing each wall plane:

      • up to ``grow_px`` into any UNCLASSIFIED neighbour, and
      • up to ``junction_px`` PAST the floor / ceiling boundary (their masks are
        eroded first) so the paint reaches right into the junction,

    while never crossing the TIGHT object mask.  New pixels take their nearest
    wall plane's id.  A few px of paint onto the ceiling/floor edge is invisible;
    a green halo is not.
    """
    wl = wall_labeled.copy()
    walls = (wl > 0).astype(np.uint8)
    if not walls.any():
        return wl

    # Erode floor/ceiling so walls may reach into the junction band.
    je = 2 * junction_px + 1
    ker_j = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (je, je))
    fe = cv2.erode((floor   > 0).astype(np.uint8), ker_j)
    ce = cv2.erode((ceiling > 0).astype(np.uint8), ker_j)
    forbidden = (fe > 0) | (ce > 0) | (objects > 0)

    region = (~forbidden) & (wl == 0)
    gk = 2 * grow_px + 1
    grown = cv2.dilate(walls, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gk, gk)))
    newpix = (grown > 0) & region
    if not newpix.any():
        return wl

    best   = np.full(wl.shape, np.inf, np.float32)
    choice = np.full(wl.shape, -1, np.int32)
    for wid in [int(i) for i in np.unique(wl) if i != 0]:
        dist = cv2.distanceTransform((wl != wid).astype(np.uint8), cv2.DIST_L2, 3)
        upd = newpix & (dist < best)
        best[upd]   = dist[upd]
        choice[upd] = wid
    for wid in [int(i) for i in np.unique(wl) if i != 0]:
        wl[newpix & (choice == wid)] = wid
    return wl


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


def sharpen_wall_boundary(
    mask: np.ndarray,
    image: np.ndarray,
    band_px: int = 10,
) -> np.ndarray:
    """Pull wall mask boundaries onto real image edges using Laplacian response.

    The guided filter already snaps soft boundaries to color edges, but smooth
    painted walls have very little color gradient — the filter gets little
    guidance and the boundary stays blurry.  Adding the Laplacian (which fires
    on luminance *changes*, not just color differences) gives an independent
    edge signal that sharpens the boundary even on monochrome plaster.

    Strategy:
      1. Compute the Laplacian of a bilateral-smoothed luminance channel.
         Bilateral preserves architectural edges while suppressing texture noise.
      2. Run a second guided-filter pass using the edge map as guide.
         This collapses the remaining soft zone to a crisp step.
      3. Merge: inside the boundary band use the sharpened result; outside keep
         the original to avoid disturbing the stable interior.
    """
    m = (mask > 0).astype(np.uint8)
    if not m.any():
        return m

    # ── Edge map: bilateral-smooth → Laplacian ──────────────────────────────
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    smooth = cv2.bilateralFilter(gray, d=9, sigmaColor=40, sigmaSpace=40)
    lap = cv2.Laplacian(smooth.astype(np.float32), cv2.CV_32F)
    edge = np.abs(lap)
    # Normalise to [0, 1] with a mild percentile clip (ignores highlight spikes)
    p95 = float(np.percentile(edge, 95)) + 1e-6
    edge = np.clip(edge / p95, 0.0, 1.0)

    # ── Boundary band: thin shell around the mask edge ───────────────────────
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band_px + 1, 2 * band_px + 1))
    dilated = cv2.dilate(m, k)
    eroded = cv2.erode(m, k)
    band = (dilated - eroded).astype(bool)

    # ── Sharpened pass via edge-guided filter ────────────────────────────────
    # Use the edge map as a single-channel guide: eps is low so the filter
    # tracks the edge signal tightly.
    radius = max(4, min(image.shape[:2]) // 120)
    edge_u8 = (edge * 255).astype(np.uint8)
    soft2 = cv2.ximgproc.guidedFilter(
        edge_u8, m.astype(np.float32), radius, (0.03 * 255) ** 2
    )

    # ── Sigmoid sharpening: amplify contrast around 0.5 ─────────────────────
    # In high-edge areas push the soft value further toward 0 or 1.
    sharpness = edge  # (H, W) in [0, 1]
    centered = soft2 - 0.5
    sharpened = 0.5 + centered * (1.0 + 3.0 * sharpness)
    sharpened = np.clip(sharpened, 0.0, 1.0)

    # ── Apply sharpened result only inside the boundary band ─────────────────
    result = m.copy().astype(np.float32)
    result[band] = sharpened[band]
    return (result > 0.5).astype(np.uint8)


__all__ = [
    "refine_mask",
    "fill_surface_gaps",
    "snap_mask_to_lines",
    "grow_walls_to_objects",
    "sharpen_wall_boundary",
    "color_coherence_expand",
    "infer_wall_behind_furniture",
    "wall_is_chromatic",
    "close_wall_halos",
    "strip_wall_color_from_objects",
    "derive_wall_by_complement",
]
