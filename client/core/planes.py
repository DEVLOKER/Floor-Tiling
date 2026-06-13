"""Split a single semantic 'wall' mask into individual wall planes.

Semantic segmentation labels every wall pixel the same, so a corner where two
walls meet becomes one connected blob — you can't select "the left wall" alone.
By recovering per-pixel surface normals from a depth map and clustering the wall
pixels by normal direction, perpendicular walls (which face very different
directions) separate cleanly, while a single flat wall stays whole.
"""
import numpy as np
import cv2


def depth_to_normals(depth: np.ndarray, focal: float | None = None) -> np.ndarray:
    """Per-pixel surface normals from a (metric) depth map.

    Back-projects to a 3D point cloud with a pinhole camera (focal guessed from
    image size if not given) and takes the normalised cross product of the
    local surface tangents.

    Returns:
        normals: float32 [H, W, 3], unit vectors in camera space.
    """
    h, w = depth.shape
    if focal is None:
        focal = float(max(h, w))  # ~55° FOV — fine; focal error only tilts
        # all normals consistently, which does not affect clustering.
    cx, cy = w / 2.0, h / 2.0

    # Edge-preserving smooth so joints/clutter don't create spurious normals.
    d = cv2.bilateralFilter(depth, d=7, sigmaColor=0.1, sigmaSpace=7)

    xs = (np.arange(w, dtype=np.float32)[None, :] - cx) / focal
    ys = (np.arange(h, dtype=np.float32)[:, None] - cy) / focal
    X = xs * d
    Y = ys * d
    Z = d
    P = np.stack([X, Y, Z], axis=-1)

    Px = np.gradient(P, axis=1)
    Py = np.gradient(P, axis=0)
    n = np.cross(Px, Py)
    norm = np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
    n = (n / norm).astype(np.float32)

    # Smooth the normal field a touch to suppress per-pixel noise.
    n = cv2.GaussianBlur(n, (5, 5), 0)
    norm = np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
    return (n / norm).astype(np.float32)


def split_wall_planes(
    wall_mask: np.ndarray,
    depth: np.ndarray,
    min_area: int = 500,
    max_planes: int = 5,
    merge_cos: float = 0.90,   # ~25°: clusters closer than this are merged
) -> tuple[np.ndarray, int]:
    """Label individual wall planes within ``wall_mask`` using normals.

    Args:
        wall_mask: binary uint8 [H, W] of all wall pixels.
        depth:     float32 [H, W] depth map (same size).
        min_area:  drop planes smaller than this many pixels.
        max_planes: k for the initial normal clustering.
        merge_cos: cosine threshold to merge near-parallel clusters.

    Returns:
        (labeled, n) where ``labeled`` is uint8 [H, W] with each plane a
        distinct id 1..n (0 = background), and ``n`` the plane count.
    """
    wall_mask = (wall_mask > 0).astype(np.uint8)
    h, w = wall_mask.shape
    coords = np.argwhere(wall_mask > 0)
    if len(coords) < min_area:
        # Too little wall — fall back to connected components.
        n, labeled = cv2.connectedComponents(wall_mask, connectivity=8)
        return labeled.astype(np.uint8), max(n - 1, 0)

    wall_area = int(wall_mask.sum())
    normals = depth_to_normals(depth)
    feats = normals[wall_mask > 0]  # (N, 3)

    # ── Cluster wall normals (KMeans on the unit sphere) ────────────────────
    # A room rarely shows more than ~4 wall planes at once; over-clustering is
    # cleaned up by the parallel-merge + spatial smoothing below.
    k = int(min(max_planes, max(2, len(feats) // 8000)))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, lbl, centers = cv2.kmeans(
        feats.astype(np.float32), k, None, crit, 5, cv2.KMEANS_PP_CENTERS
    )
    lbl = lbl.ravel()
    centers = centers / (np.linalg.norm(centers, axis=1, keepdims=True) + 1e-8)

    # ── Merge clusters facing the SAME direction (same wall). ───────────────
    # NOTE: use the signed dot, not |dot| — opposite-facing walls (e.g. left
    # vs right, normals +x vs -x) must stay separate.
    parent = list(range(k))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(k):
        for j in range(i + 1, k):
            if float(np.dot(centers[i], centers[j])) >= merge_cos:
                parent[find(i)] = find(j)
    remap = {c: find(c) for c in range(k)}

    # ── Paint merged cluster ids back into the image ────────────────────────
    cluster_img = np.zeros((h, w), np.uint8)
    cl = np.array([remap[c] + 1 for c in lbl], dtype=np.uint8)  # 0 = background
    cluster_img[wall_mask > 0] = cl

    # ── Spatial regularisation: median-vote the labels a few times so a wall
    #    becomes one coherent region instead of salt-and-pepper clusters. ────
    for _ in range(3):
        cluster_img = cv2.medianBlur(cluster_img, 7)
    cluster_img[wall_mask == 0] = 0

    # ── Each direction may still contain spatially separate walls → split by
    #    connected components; keep only sizeable pieces. ────────────────────
    min_keep = max(min_area, int(0.03 * wall_area))
    pieces = []  # (area, bool_mask)
    for cid in np.unique(cluster_img):
        if cid == 0:
            continue
        comp_mask = (cluster_img == cid).astype(np.uint8)
        comp_mask = cv2.morphologyEx(
            comp_mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)
        )
        ncomp, comp = cv2.connectedComponents(comp_mask, connectivity=8)
        for c in range(1, ncomp):
            piece = (comp == c) & (wall_mask > 0)
            area = int(piece.sum())
            if area >= min_keep:
                pieces.append((area, piece))

    # Largest planes first, capped, relabelled 1..n. These are the "seeds".
    pieces.sort(key=lambda p: p[0], reverse=True)
    seeds = np.zeros((h, w), np.uint8)
    next_id = 1
    for _, piece in pieces[:max_planes]:
        seeds[piece] = next_id
        next_id += 1

    n_planes = next_id - 1
    if n_planes == 0:
        return wall_mask.copy(), 1

    # ── Complete coverage: assign EVERY wall pixel to its nearest plane ──────
    # (fills the gaps left by smoothing/filtering so no wall slivers go
    # unpainted, and gives clean Voronoi boundaries between adjacent planes).
    labeled = np.zeros((h, w), np.uint8)
    best = np.full((h, w), np.inf, np.float32)
    for pid in range(1, n_planes + 1):
        dist = cv2.distanceTransform((seeds != pid).astype(np.uint8), cv2.DIST_L2, 3)
        upd = dist < best
        labeled[upd] = pid
        best[upd] = dist[upd]
    labeled[wall_mask == 0] = 0
    return labeled, n_planes


__all__ = ["depth_to_normals", "split_wall_planes"]
