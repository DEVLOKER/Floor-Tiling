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


def refine_mask(
    mask: np.ndarray,
    image: np.ndarray,
    single_region: bool = False,
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
    return (soft > 0.5).astype(np.uint8)


__all__ = ["refine_mask"]
