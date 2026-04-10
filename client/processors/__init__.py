import numpy as np
import cv2
from config.settings import DEFAULT_REAL_WIDTH_CM
from core import hex_to_bgr, extract_floor_quad, rectify_quad, estimate_floor_geometry, align_quad_to_walls
from patterns import get_pattern

def apply_perspective_tiles(image: np.ndarray, mask: np.ndarray, tile_color: str, tile_color2: str, grout_color: str, tile_width_cm: float, tile_height_cm: float, grout_h_thickness: int, grout_v_thickness: int, rotation_deg: float=0.0, pattern: str="grid", tile_texture: np.ndarray=None, tile_texture2: np.ndarray=None, visual_square_compensation: bool=True) -> np.ndarray:
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

    du_dy, du_dx = np.gradient(u_all)
    dv_dy, dv_dx = np.gradient(v_all)
    for arr in (du_dx, du_dy, dv_dx, dv_dy):
        arr[mask == 0] = 0.0
    uv_step_u = np.clip(np.sqrt(du_dx ** 2 + du_dy ** 2), 1e-06, 10.0)
    uv_step_v = np.clip(np.sqrt(dv_dx ** 2 + dv_dy ** 2), 1e-06, 10.0)
    grout_v_frac_map = np.clip(uv_step_u * grout_v_thickness, 0.0005, 0.45)
    grout_h_frac_map = np.clip(uv_step_v * grout_h_thickness, 0.0005, 0.45)
    is_second, on_grout = get_pattern(pattern)(u_all, v_all, grout_h_frac=grout_h_frac_map, grout_v_frac=grout_v_frac_map, aspect_ratio=tile_width_cm / tile_height_cm if tile_height_cm > 0 else 1.0, du_dx=du_dx, du_dy=du_dy, dv_dx=dv_dx, dv_dy=dv_dy, grout_thickness_v=grout_v_thickness, grout_thickness_h=grout_h_thickness, uv_step_u=uv_step_u, uv_step_v=uv_step_v)
    orig_f = image.astype(np.float32)
    orig_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    blur_k = max(3, min(h_img, w_img) // 20 | 1)
    light_smooth = cv2.GaussianBlur(orig_gray, (blur_k, blur_k), 0)
    mb = max(float(np.mean(light_smooth[mask > 0])) if mask.any() else 0.5, 0.01)
    light = np.clip(light_smooth / mb, 0.2, 2.0)
    step_max = np.maximum(uv_step_u, uv_step_v)
    fade_raw = 1.0 - np.clip((step_max - 0.25) / (0.5 - 0.25), 0.0, 1.0)
    grout_fade = fade_raw * fade_raw * (3.0 - 2.0 * fade_raw)
    grout_alpha = np.clip(on_grout * grout_fade, 0.0, 1.0)[:, :, None]
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
    grout_f = grout_bgr[None, None, :].astype(np.float32)
    colour_img = grout_alpha * grout_f + (1.0 - grout_alpha) * tile_fill
    sat_factor = 0.85
    gray_img = cv2.cvtColor(colour_img.astype(np.uint8), cv2.COLOR_BGR2GRAY)[:, :, None]
    colour_img = colour_img * sat_factor + gray_img * (1.0 - sat_factor)
    colour_img = np.clip(colour_img * light[:, :, None], 0, 255)
    colour_img = np.power(colour_img / 255.0, 1.1) * 255.0
    colour_img = colour_img.astype(np.uint8)
    result = image.copy()
    result[mask > 0] = colour_img[mask > 0]
    return result
__all__ = ['apply_perspective_tiles']
