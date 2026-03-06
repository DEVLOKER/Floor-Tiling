"""Tile rendering processor using homography projection"""
import numpy as np
import cv2

from config.settings import DEFAULT_REAL_WIDTH_CM
from core import hex_to_bgr, extract_floor_quad, estimate_real_depth_cm
from patterns import get_pattern


def apply_perspective_tiles(image: np.ndarray,
                            mask: np.ndarray,
                            tile_color: str,
                            tile_color2: str,
                            grout_color: str,
                            tile_width_cm: float,
                            tile_height_cm: float,
                            grout_h_thickness: int,
                            grout_v_thickness: int,
                            pattern: str) -> np.ndarray:
    """Apply tiles to floor using homography-based perspective rendering.
    
    Projects floor pixels to tile-plane coordinates using inverse homography,
    applies selected pattern with independent H/V grout lines.
    
    Args:
        image: BGR image array
        mask: Binary floor mask
        tile_color: Hex color for primary tiles
        tile_color2: Hex color for secondary tiles (checkerboard)
        grout_color: Hex color for grout lines
        tile_width_cm: Real-world tile width in cm
        tile_height_cm: Real-world tile height in cm
        grout_h_thickness: Horizontal grout line thickness in pixels
        grout_v_thickness: Vertical grout line thickness in pixels
        pattern: Pattern name (grid, brick, diagonal, herringbone, checkerboard, diagonal_checkerboard)
    
    Returns:
        Image with applied tiles
    """
    mask = (mask > 0).astype(np.uint8)

    tile_bgr = np.array(hex_to_bgr(tile_color), dtype=np.float32)
    tile2_bgr = np.array(hex_to_bgr(tile_color2), dtype=np.float32)
    grout_bgr = np.array(hex_to_bgr(grout_color), dtype=np.float32)

    h_img, w_img = image.shape[:2]

    # Extract floor quadrilateral
    quad = extract_floor_quad(mask)
    if quad is None:
        print("⚠️ No quad")
        return image

    near_left, near_right, far_left, far_right = quad
    near_width_px = float(np.linalg.norm(near_right - near_left))
    if near_width_px <= 0:
        return image

    # Estimate real-world depth
    real_width_cm = DEFAULT_REAL_WIDTH_CM
    real_depth_cm = estimate_real_depth_cm(
        near_left, near_right, far_left, far_right, real_width_cm)

    n_tiles_x = max(2, int(round(real_width_cm / tile_width_cm)))
    n_tiles_y = max(2, int(round(real_depth_cm / tile_height_cm)))

    # Compute homography: plane → image
    plane_pts = np.array([
        [0, 0],
        [n_tiles_x, 0],
        [n_tiles_x, n_tiles_y],
        [0, n_tiles_y],
    ], dtype=np.float32)

    image_pts = np.array([far_left, far_right, near_right, near_left],
                         dtype=np.float32)

    H_fwd, _ = cv2.findHomography(plane_pts, image_pts)
    if H_fwd is None:
        print("⚠️ Homography failed")
        return image
    H_inv = np.linalg.inv(H_fwd)

    print(f"🟡 Pattern={pattern}  tiles={n_tiles_x}×{n_tiles_y}  "
          f"tile={tile_width_cm}×{tile_height_cm}cm  "
          f"grout px=({grout_v_thickness},{grout_h_thickness})")

    # Project all pixels to tile-plane coordinates
    ys_all, xs_all = np.mgrid[0:h_img, 0:w_img]
    ones = np.ones(h_img * w_img, dtype=np.float64)
    img_coords = np.stack([
        xs_all.ravel().astype(np.float64),
        ys_all.ravel().astype(np.float64),
        ones
    ], axis=1)

    plane_coords = img_coords @ H_inv.T
    w_div = plane_coords[:, 2]
    w_div = np.where(np.abs(w_div) < 1e-9, 1e-9, w_div)

    u_all = (plane_coords[:, 0] / w_div).reshape(h_img, w_img)
    v_all = (plane_coords[:, 1] / w_div).reshape(h_img, w_img)

    # ── Adaptive per-pixel grout fractions ──────────────────────────────────
    # Use np.gradient instead of np.roll to avoid edge-wrap artifacts.
    # Zero out derivatives outside mask to prevent UV boundary spikes
    # from bleeding into the floor region.

    du_dy, du_dx = np.gradient(u_all)
    dv_dy, dv_dx = np.gradient(v_all)

    du_dx[mask == 0] = 0.0
    du_dy[mask == 0] = 0.0
    dv_dx[mask == 0] = 0.0
    dv_dy[mask == 0] = 0.0

    uv_step_u = np.sqrt(du_dx ** 2 + du_dy ** 2)
    uv_step_v = np.sqrt(dv_dx ** 2 + dv_dy ** 2)

    uv_step_u = np.clip(uv_step_u, 1e-6, 10.0)
    uv_step_v = np.clip(uv_step_v, 1e-6, 10.0)

    grout_v_frac_map = np.clip(uv_step_u * grout_v_thickness, 0.0005, 0.45)
    grout_h_frac_map = np.clip(uv_step_v * grout_h_thickness, 0.0005, 0.45)
    # ────────────────────────────────────────────────────────────────────────

    # Apply selected pattern
    pattern_fn = get_pattern(pattern)
    is_second, on_grout = pattern_fn(
        u_all, v_all,
        grout_h_frac=grout_h_frac_map,
        grout_v_frac=grout_v_frac_map,
        aspect_ratio=tile_width_cm / tile_height_cm if tile_height_cm > 0 else 2.0
    )

    # Apply lighting from original image
    orig_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    mb = float(np.mean(orig_gray[mask > 0])) if mask.any() else 0.5
    mb = max(mb, 0.01)
    light = np.clip(orig_gray / mb, 0.3, 2.0)

    # Generate color map: grout > secondary > primary
    colour_img = np.where(
        on_grout[:, :, np.newaxis],
        grout_bgr[np.newaxis, np.newaxis, :],
        np.where(
            is_second[:, :, np.newaxis],
            tile2_bgr[np.newaxis, np.newaxis, :],
            tile_bgr[np.newaxis, np.newaxis, :]
        )
    ).astype(np.float32)

    colour_img *= light[:, :, np.newaxis]
    colour_img = np.clip(colour_img, 0, 255).astype(np.uint8)

    # Composite result
    result = image.copy()
    result[mask > 0] = colour_img[mask > 0]
    return result

    
__all__ = ["apply_perspective_tiles"]
