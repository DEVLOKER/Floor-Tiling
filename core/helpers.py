"""Core helper functions"""
import numpy as np


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


def extract_floor_quad(mask: np.ndarray) -> tuple:
    """Extract the four corners of the floor region from mask.
    
    Finds near/far top edges and extracts quadrilateral points
    representing the floor perspective.
    
    Args:
        mask: Binary floor mask
    
    Returns:
        Tuple of (near_left, near_right, far_left, far_right) or None
    """
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None

    y_near = int(ys.max())
    y_far = int(ys.min())

    def get_edges(y_center: int, band: int = 8):
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
    fl, fr = get_edges(y_far, band=8)
    if nl is None or fl is None:
        return None

    near_left = np.array([nl, float(y_near)], dtype=np.float32)
    near_right = np.array([nr, float(y_near)], dtype=np.float32)
    far_left = np.array([fl, float(y_far)], dtype=np.float32)
    far_right = np.array([fr, float(y_far)], dtype=np.float32)

    print(f"  Quad NL={near_left} NR={near_right} FL={far_left} FR={far_right}")
    return near_left, near_right, far_left, far_right


def estimate_real_depth_cm(near_left: np.ndarray,
                           near_right: np.ndarray,
                           far_left: np.ndarray,
                           far_right: np.ndarray,
                           real_width_cm: float = 400.0) -> float:
    """Estimate real-world depth from perspective width ratio.
    
    Uses the perspective ratio (far_width / near_width) to estimate depth.
    
    Args:
        near_left, near_right: Points at near edge
        far_left, far_right: Points at far edge
        real_width_cm: Real-world floor width in cm
    
    Returns:
        Estimated depth in cm
    """
    near_w = float(np.linalg.norm(near_right - near_left))
    far_w = float(np.linalg.norm(far_right - far_left))
    if near_w <= 0:
        return real_width_cm
    
    from config.settings import (
        DEPTH_FAR_RATIO_MIN,
        DEPTH_FAR_RATIO_MAX,
        DEPTH_MIN_CM,
        DEPTH_MAX_CM,
    )
    
    ratio = float(np.clip(far_w / near_w, DEPTH_FAR_RATIO_MIN, DEPTH_FAR_RATIO_MAX))
    real_depth = real_width_cm * (1.0 / ratio - 1.0)
    real_depth = float(np.clip(real_depth, DEPTH_MIN_CM, DEPTH_MAX_CM))
    print(f"  near_w={near_w:.1f} far_w={far_w:.1f} ratio={ratio:.3f} depth={real_depth:.1f}cm")
    return real_depth
