"""Perspective-correct tile rendering pipeline.

This module houses the full tile-rendering implementation:
  - Mask feathering and blending helpers
  - Shadow and ambient-tint recovery from the original floor
  - Laplacian pyramid blending utilities
  - ``apply_perspective_tiles()`` — the main public entry point

Import via the package: ``from processors import apply_perspective_tiles``
"""
import numpy as np
import cv2
from config.settings import DEFAULT_REAL_WIDTH_CM
from core import hex_to_bgr, extract_floor_quad, estimate_floor_geometry
from patterns import get_pattern


# â”€â”€â”€ Blending helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _feather_mask(mask: np.ndarray, radius: int = 6) -> np.ndarray:
    """Create a soft-edged alpha mask using distance transform.

    The interior stays 1.0, edges taper smoothly to 0.0 over `radius` pixels.
    This eliminates hard cut-and-paste edges.
    """
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    alpha = np.clip(dist / max(radius, 1), 0.0, 1.0).astype(np.float32)
    # Slight Gaussian to smooth any aliasing
    k = radius | 1  # ensure odd
    alpha = cv2.GaussianBlur(alpha, (k, k), 0)
    return alpha


def _soft_light_blend(base: np.ndarray, blend: np.ndarray) -> np.ndarray:
    """Photoshop-style Soft Light blending (Pegtop formula).

    Both inputs are float32 in [0, 1]. Result is [0, 1].
    Preserves original shadows/highlights while tinting with the tile color.
    """
    return (1.0 - 2.0 * blend) * base * base + 2.0 * blend * base


def _extract_shadow_map(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Extract a normalised luminance shadow map from the original floor.

    Uses LAB color space (perceptually uniform) instead of simple grayscale.
    Returns a float32 map where 1.0 = average brightness, <1.0 = shadow, >1.0 = highlight.
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]  # 0-255 range in LAB
    h, w = L.shape

    # â”€â”€ Prevent edge contamination â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Replace non-floor pixels with the floor's mean luminance BEFORE
    # blurring.  Without this, dark walls / furniture bleed across the
    # mask boundary during the large-kernel Gaussian blur, producing
    # fake shadows along every floor edge.
    floor_mean_L = float(np.mean(L[mask > 0])) if mask.any() else 128.0
    L_clean = np.where(mask > 0, L, floor_mean_L)

    # Heavy blur to capture ONLY broad lighting (shadows from furniture,
    # light gradients), NOT the original floor's texture or pattern.
    blur_k = max(5, min(h, w) // 6 | 1)
    L_smooth = cv2.GaussianBlur(L_clean, (blur_k, blur_k), 0)

    # Normalise: mean of floor area = 1.0
    floor_mean = max(floor_mean_L, 1.0)
    shadow_map = L_smooth / floor_mean

    # â”€â”€ Neutralise shadow near mask edges â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # The blur kernel is very large (min(h,w)//6 â‰ˆ 600+ px on hi-res).
    # Near walls/furniture the original floor is naturally darker (base-
    # boards, corners) â€” transferring that darkening to new tiles looks
    # fake.  Use the FULL blur kernel as the margin so shadow effects
    # only appear deep inside the floor where they represent real room
    # lighting (e.g. a window highlight, a table shadow).
    edge_margin = max(30, blur_k)
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    t = np.clip(dist / max(edge_margin, 1), 0.0, 1.0).astype(np.float32)
    # Smooth-step (cubic Hermite) for perceptually invisible transition
    edge_blend = t * t * (3.0 - 2.0 * t)
    shadow_map = edge_blend * shadow_map + (1.0 - edge_blend) * 1.0

    return np.clip(shadow_map, 0.70, 1.30).astype(np.float32)


def _extract_ambient_tint(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Extract the color temperature of the original floor lighting.

    Returns a per-channel multiplier [B, G, R] so tiles inherit the room's
    warm/cool cast (e.g. yellow tungsten, blue daylight).
    """
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]

    # Get floor pixels mean color in BGR
    if not mask.any():
        return np.array([1.0, 1.0, 1.0], dtype=np.float32)

    floor_bgr = image_bgr[mask > 0].astype(np.float32)
    mean_bgr = np.mean(floor_bgr, axis=0)
    gray_val = np.mean(mean_bgr)

    if gray_val < 1.0:
        return np.array([1.0, 1.0, 1.0], dtype=np.float32)

    # Tint is the ratio of each channel to the gray mean
    # Clamped to avoid extreme tints
    tint = np.clip(mean_bgr / gray_val, 0.8, 1.2).astype(np.float32)
    return tint


def _laplacian_pyramid_blend(
    fg: np.ndarray,
    bg: np.ndarray,
    alpha: np.ndarray,
    levels: int = 5,
) -> np.ndarray:
    """Multi-scale Laplacian pyramid blending.

    Blends high-frequency details (tile edges, grout) and low-frequency
    information (overall color, brightness) at separate scales so there
    are no visible seams at the mask boundary.

    Args:
        fg:    Foreground (tiled floor), float32 [H, W, 3], 0-255
        bg:    Background (original image), float32 [H, W, 3], 0-255
        alpha: Soft mask, float32 [H, W], 0-1
    """
    # Ensure dimensions are compatible with pyramid (divisible by 2^levels)
    h, w = fg.shape[:2]
    factor = 2 ** levels
    pad_h = (factor - h % factor) % factor
    pad_w = (factor - w % factor) % factor

    if pad_h or pad_w:
        fg = np.pad(fg, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')
        bg = np.pad(bg, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')
        alpha = np.pad(alpha, ((0, pad_h), (0, pad_w)), mode='reflect')

    # Build Gaussian pyramids for alpha mask
    alpha3 = alpha[:, :, None]  # [H, W, 1]
    gp_alpha = [alpha3]
    for _ in range(levels):
        alpha3 = cv2.pyrDown(alpha3)
        if alpha3.ndim == 2:
            alpha3 = alpha3[:, :, None]
        gp_alpha.append(alpha3)

    # Build Laplacian pyramids for fg and bg
    def _laplacian_pyramid(img):
        gp = [img]
        for _ in range(levels):
            gp.append(cv2.pyrDown(gp[-1]))
        lp = []
        for i in range(levels):
            up = cv2.pyrUp(gp[i + 1], dstsize=(gp[i].shape[1], gp[i].shape[0]))
            lp.append(gp[i] - up)
        lp.append(gp[levels])
        return lp

    lp_fg = _laplacian_pyramid(fg)
    lp_bg = _laplacian_pyramid(bg)

    # Blend each pyramid level
    lp_blend = []
    for lf, lb, ga in zip(lp_fg, lp_bg, gp_alpha):
        # Resize alpha to match level if needed
        if ga.shape[:2] != lf.shape[:2]:
            ga = cv2.resize(ga, (lf.shape[1], lf.shape[0]))
            if ga.ndim == 2:
                ga = ga[:, :, None]
        lp_blend.append(ga * lf + (1.0 - ga) * lb)

    # Reconstruct
    result = lp_blend[-1]
    for i in range(levels - 1, -1, -1):
        result = cv2.pyrUp(result, dstsize=(lp_blend[i].shape[1], lp_blend[i].shape[0]))
        result += lp_blend[i]

    # Remove padding
    result = result[:h, :w]
    return np.clip(result, 0, 255)


# â”€â”€â”€ Main tile rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def apply_perspective_tiles(image: np.ndarray, mask: np.ndarray, tile_color: str, tile_color2: str, grout_color: str, tile_width_cm: float, tile_height_cm: float, grout_h_thickness: int, grout_v_thickness: int, rotation_deg: float=0.0, pattern: str="grid", tile_texture: np.ndarray=None, tile_texture2: np.ndarray=None, visual_square_compensation: bool=True, translate_x: float=0.0, translate_y: float=0.0) -> np.ndarray:
    mask = (mask > 0).astype(np.uint8)
    tile_bgr = np.array(hex_to_bgr(tile_color), dtype=np.float32)
    tile2_bgr = np.array(hex_to_bgr(tile_color2), dtype=np.float32)
    grout_bgr = np.array(hex_to_bgr(grout_color), dtype=np.float32)
    h_img, w_img = image.shape[:2]
    quad = extract_floor_quad(mask, image=image)
    if quad is None:
        return image
    near_left, near_right, far_left, far_right = quad
    if np.linalg.norm(near_right - near_left) <= 0:
        return image
    vp_y, real_depth_cm, depth_ratio = estimate_floor_geometry(near_left, near_right, far_left, far_right, DEFAULT_REAL_WIDTH_CM)
    n_tiles_x = max(2, int(round(DEFAULT_REAL_WIDTH_CM / tile_width_cm)))
    n_tiles_y = max(2, int(round(real_depth_cm / tile_height_cm)))
    plane_w = float(n_tiles_x)
    plane_h = float(n_tiles_y)
    plane_pts = np.array([[0, 0], [plane_w, 0], [plane_w, plane_h], [0, plane_h]], dtype=np.float32)
    image_pts = np.array([far_left, far_right, near_right, near_left], dtype=np.float32)
    H_fwd, _ = cv2.findHomography(plane_pts, image_pts)
    if H_fwd is None:
        return image
    H_inv = np.linalg.inv(H_fwd)
    ys_all, xs_all = np.mgrid[0:h_img, 0:w_img]
    img_coords = np.stack([xs_all.ravel().astype(np.float64), ys_all.ravel().astype(np.float64), np.ones(h_img * w_img)], axis=1)
    pc = img_coords @ H_inv.T
    wdiv = np.where(np.abs(pc[:, 2]) < 1e-09, 1e-09, pc[:, 2])
    u_all = (pc[:, 0] / wdiv).reshape(h_img, w_img)
    v_all = (pc[:, 1] / wdiv).reshape(h_img, w_img)
    v_all = v_all * (n_tiles_y / plane_h)
    
    if abs(rotation_deg) > 0.001:
        theta = np.radians(rotation_deg)
        cx, cy = float(n_tiles_x) / 2.0, float(n_tiles_y) / 2.0
        u_shifted = u_all - cx
        v_shifted = v_all - cy
        u_rot = u_shifted * np.cos(theta) - v_shifted * np.sin(theta) + cx
        v_rot = u_shifted * np.sin(theta) + v_shifted * np.cos(theta) + cy
        u_all, v_all = u_rot, v_rot

    # â”€â”€ Translation (direct tile-unit offset) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if abs(translate_x) > 0.001 or abs(translate_y) > 0.001:
        u_all = u_all + translate_x
        v_all = v_all + translate_y

    # Erode mask by a few pixels so gradient computation at the boundary
    # doesn't mix inside/outside UV values (which produces wrong step
    # sizes and therefore thick grout lines or visual artifacts at edges).
    grad_kern = max(3, min(h_img, w_img) // 600) | 1
    mask_interior = cv2.erode(mask, np.ones((grad_kern, grad_kern), np.uint8))
    du_dy, du_dx = np.gradient(u_all)
    dv_dy, dv_dx = np.gradient(v_all)
    for arr in (du_dx, du_dy, dv_dx, dv_dy):
        arr[mask_interior == 0] = 0.0
    uv_step_u = np.clip(np.sqrt(du_dx ** 2 + du_dy ** 2), 1e-06, 10.0)
    uv_step_v = np.clip(np.sqrt(dv_dx ** 2 + dv_dy ** 2), 1e-06, 10.0)
    grout_v_frac_map = np.clip(uv_step_u * grout_v_thickness, 0.0, 0.45)
    grout_h_frac_map = np.clip(uv_step_v * grout_h_thickness, 0.0, 0.45)
    is_second, on_grout = get_pattern(pattern)(u_all, v_all, grout_h_frac=grout_h_frac_map, grout_v_frac=grout_v_frac_map, aspect_ratio=tile_width_cm / tile_height_cm if tile_height_cm > 0 else 1.0, du_dx=du_dx, du_dy=du_dy, dv_dx=dv_dx, dv_dy=dv_dy, grout_thickness_v=grout_v_thickness, grout_thickness_h=grout_h_thickness, uv_step_u=uv_step_u, uv_step_v=uv_step_v)

    # â”€â”€ Texture / color fill â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    u_frac = u_all - np.floor(u_all)
    v_frac = v_all - np.floor(v_all)
    if tile_texture is not None:
        th, tw = tile_texture.shape[:2]
        tx = np.clip((u_frac * tw).astype(np.int32), 0, tw - 1)
        ty = np.clip((v_frac * th).astype(np.int32), 0, th - 1)
        tex1 = tile_texture[ty, tx].astype(np.float32)
        if tile_texture2 is not None:
            th2, tw2 = tile_texture2.shape[:2]
            tx2 = np.clip((u_frac * tw2).astype(np.int32), 0, tw2 - 1)
            ty2 = np.clip((v_frac * th2).astype(np.int32), 0, th2 - 1)
            tex2 = tile_texture2[ty2, tx2].astype(np.float32)
            tile_fill = np.where(is_second[:, :, None], tex2, tex1)
        else:
            tile_fill = tex1
    else:
        tile_fill = np.where(is_second[:, :, None], tile2_bgr[None, None, :], tile_bgr[None, None, :]).astype(np.float32)

    # â”€â”€ Grout compositing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    step_max = np.maximum(uv_step_u, uv_step_v)
    fade_raw = 1.0 - np.clip((step_max - 0.25) / (0.5 - 0.25), 0.0, 1.0)
    grout_fade = fade_raw * fade_raw * (3.0 - 2.0 * fade_raw)
    grout_alpha = np.clip(on_grout * grout_fade, 0.0, 1.0)[:, :, None]
    grout_f = grout_bgr[None, None, :].astype(np.float32)
    colour_img = grout_alpha * grout_f + (1.0 - grout_alpha) * tile_fill

    # â”€â”€ Shadow & lighting recovery (LAB-based) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    shadow_map = _extract_shadow_map(image, mask)
    ambient_tint = _extract_ambient_tint(image, mask)

    # Apply shadow map (preserves original room shadows on new tiles)
    colour_img = colour_img * shadow_map[:, :, None]

    # Apply ambient color temperature tint
    colour_img = colour_img * ambient_tint[None, None, :]

    # Clamp to valid range (shadow + tint can push values beyond 255)
    colour_img = np.clip(colour_img, 0, 255)

    # Mild desaturation to match real-world appearance
    sat_factor = 0.90
    gray_ch = cv2.cvtColor(colour_img.astype(np.uint8), cv2.COLOR_BGR2GRAY)[:, :, None].astype(np.float32)
    colour_img = colour_img * sat_factor + gray_ch * (1.0 - sat_factor)
    colour_img = np.clip(colour_img, 0, 255).astype(np.uint8)

    # â”€â”€ Seamless compositing (direct alpha blend) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Simple alpha compositing with a small feathered mask for anti-aliased
    # edges.  Laplacian pyramid blending was removed because it spreads
    # the mask boundary across coarse scales, leaking the original floor's
    # colour/brightness ~100+ px inward from every edge â€” the "fake shadow
    # halo" effect.  Direct blend avoids this entirely.
    alpha = _feather_mask(mask, radius=3)
    alpha3 = alpha[:, :, None]  # [H,W,1]

    fg = colour_img.astype(np.float32)
    bg = image.astype(np.float32)
    result = alpha3 * fg + (1.0 - alpha3) * bg

    return np.clip(result, 0, 255).astype(np.uint8)


__all__ = ['apply_perspective_tiles']

