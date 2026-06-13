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


# These functions operate on the original image and the tile-rendered floor to create a seamless composite.
# They are not used by the pattern generation or tile rendering logic, 
# which only produce the "ideal" tiled floor without any lighting/shadow effects or blending.
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

    # Asymmetric clamp.  Shadows (darker-than-average) are genuine room
    # lighting and may be deep, so allow them down to 0.80.  Bright spots,
    # however, are usually *specular* glare bouncing off a glossy original
    # floor (e.g. a window reflection) — not diffuse room light — and baking
    # them onto new matte tiles produces a fake washed-out patch.  Cap the
    # highlight side tightly so reflections don't transfer.
    return np.clip(shadow_map, 0.80, 1.12).astype(np.float32)


# How much of the original floor's colour cast to transfer to the new tiles.
# The old floor's mean colour is dominated by its *material* (e.g. brown wood),
# not the room lighting, so applying it at full strength recolours neutral tiles
# (grey → orange).  Keep this small: just a hint of the room's warmth/coolness.
AMBIENT_TINT_STRENGTH = 0.25


def _extract_ambient_tint(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Extract a *subtle* warm/cool cast from the original floor lighting.

    Returns a per-channel multiplier [B, G, R].  We can't truly separate light
    colour from the floor's material colour in a single photo, so we only apply
    a fraction (``AMBIENT_TINT_STRENGTH``) of the detected cast — enough to sit
    the tiles in the room's ambiance without repainting them the old floor's
    colour.
    """
    if not mask.any():
        return np.array([1.0, 1.0, 1.0], dtype=np.float32)

    floor_bgr = image_bgr[mask > 0].astype(np.float32)
    mean_bgr = np.mean(floor_bgr, axis=0)
    gray_val = np.mean(mean_bgr)

    if gray_val < 1.0:
        return np.array([1.0, 1.0, 1.0], dtype=np.float32)

    # Raw cast = per-channel deviation from neutral grey, then pulled mostly
    # back toward 1.0 and clamped tight so it can never recolour the tiles.
    raw = mean_bgr / gray_val
    tint = 1.0 + (raw - 1.0) * AMBIENT_TINT_STRENGTH
    return np.clip(tint, 0.95, 1.05).astype(np.float32)


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


# ─────────────────────────────────────────────────────────────────────────────
# Photorealism helpers
#
# These take the "ideal" flat tiled floor and add the subtle imperfections that
# make a real photographed floor read as real instead of computer-generated:
#   - mip-mapped / bilinear texture sampling      → kills shimmer & moiré in depth
#   - per-tile tonal variation                    → breaks obvious CG repetition
#   - grout ambient-occlusion / recessed bevel    → tiles sit *in* the floor
#   - clear-coat gloss sheen                       → glazed/polished reflection
#   - micro surface grain                          → no dead-flat banding
# ─────────────────────────────────────────────────────────────────────────────

# Strength knobs (all tuned conservative — realism, not a filter look)
# Per-tile variation is intentionally subtle: enough to avoid a dead-flat CG
# look, but not so much that a single-colour grid reads as "different colours".
# The hue (warm/cool) jitter is kept very small because a hue shift between
# neighbouring tiles is far more noticeable than a brightness shift.
TILE_BRIGHT_VARIATION = 0.022  # ± fraction of per-tile brightness jitter
TILE_COLOR_VARIATION = 0.005   # ± fraction of per-tile warm/cool jitter
GROUT_AO_STRENGTH = 0.28       # how dark the recessed joint shadow gets
GROUT_BEVEL_HIGHLIGHT = 0.10   # bright catch-light on the tile-edge bevel
GLOSS_SHEEN = 18.0             # additive specular boost in lit areas (0-255)
MICRO_GRAIN_STD = 1.8          # std-dev of surface grain for solid colours


def _hash01(a: np.ndarray, b: np.ndarray, sx: float, sy: float) -> np.ndarray:
    """Deterministic per-cell pseudo-random value in [0, 1).

    Classic GLSL-style hash — stable across runs so the same floor always
    renders identically (important for live preview / undo).
    """
    n = np.sin(a * sx + b * sy) * 43758.5453
    return n - np.floor(n)


def _bilinear_sample_pts(img: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinearly sample *img* at fractional (u, v) coords given as 1-D arrays.

    u, v are in [0, 1] tile space.  Edges are clamped (grout hides the seam).
    """
    th, tw = img.shape[:2]
    fx = np.clip(u, 0.0, 1.0) * (tw - 1)
    fy = np.clip(v, 0.0, 1.0) * (th - 1)
    x0 = np.floor(fx).astype(np.int32)
    y0 = np.floor(fy).astype(np.int32)
    x1 = np.minimum(x0 + 1, tw - 1)
    y1 = np.minimum(y0 + 1, th - 1)
    wx = (fx - x0)[:, None]
    wy = (fy - y0)[:, None]
    Ia = img[y0, x0]
    Ib = img[y0, x1]
    Ic = img[y1, x0]
    Id = img[y1, x1]
    top = Ia * (1.0 - wx) + Ib * wx
    bot = Ic * (1.0 - wx) + Id * wx
    return top * (1.0 - wy) + bot * wy


def _build_mips(tex: np.ndarray, levels: int = 5) -> list:
    """Build a Gaussian mip pyramid of a texture (float32 BGR)."""
    mips = [tex.astype(np.float32)]
    cur = mips[0]
    for _ in range(levels):
        if min(cur.shape[:2]) <= 2:
            break
        cur = cv2.pyrDown(cur)
        mips.append(cur)
    return mips


def _sample_texture_aa(
    mips: list,
    u_frac: np.ndarray,
    v_frac: np.ndarray,
    uv_step_u: np.ndarray,
    uv_step_v: np.ndarray,
) -> np.ndarray:
    """Anti-aliased texture lookup with per-pixel level-of-detail selection.

    Far-away tiles span many texels per screen pixel; sampling the full-res
    texture there produces shimmering moiré.  We pick a mip level so roughly
    one texel maps to one pixel, then bilinearly sample within it — the same
    trick GPUs use for textured floors.
    """
    base_h, base_w = mips[0].shape[:2]
    # Texels covered by one screen pixel along each tile axis.
    texels_per_px = np.maximum(uv_step_u * base_w, uv_step_v * base_h)
    lod = np.log2(np.maximum(texels_per_px, 1.0))
    lvl = np.clip(np.rint(lod), 0, len(mips) - 1).astype(np.int32)

    out = np.empty(u_frac.shape + (3,), dtype=np.float32)
    uf = u_frac.ravel()
    vf = v_frac.ravel()
    lv = lvl.ravel()
    flat = out.reshape(-1, 3)
    for L in range(len(mips)):
        m = lv == L
        if not m.any():
            continue
        flat[m] = _bilinear_sample_pts(mips[L], uf[m], vf[m])
    return out


# The main public function.  Takes the original image and floor mask, renders the perspective-correct tile pattern,
# applies shadow/tint from the original floor, and blends the result seamlessly back onto the original image.
def apply_perspective_tiles(image: np.ndarray, mask: np.ndarray, tile_color: str, tile_color2: str, grout_color: str, tile_width_cm: float, tile_height_cm: float, grout_h_thickness: int, grout_v_thickness: int, rotation_deg: float=0.0, pattern: str="grid", tile_texture: np.ndarray=None, tile_texture2: np.ndarray=None, visual_square_compensation: bool=True, translate_x: float=0.0, translate_y: float=0.0, perspective_compression: float=0.0) -> np.ndarray:
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
    
    # ── Perspective compression: increase perceived tile size ────────────────
    # Instead of geometric manipulation, we directly reduce the tile count by
    # scaling up the "virtual tile size" used for depth calculation.
    # This makes ALL tiles larger but preserves perspective geometry.
    effective_tile_height = tile_height_cm
    if perspective_compression > 0.001:
        # Scale up the tile size: 0% = no change, 100% = 2.5x larger tiles
        # 65% compression → 1.85x larger tiles
        scale_factor = 1.0 + perspective_compression * 1.5
        effective_tile_height = tile_height_cm * scale_factor
    
    n_tiles_x = max(2, int(round(DEFAULT_REAL_WIDTH_CM / tile_width_cm)))
    n_tiles_y = max(2, int(round(real_depth_cm / effective_tile_height)))
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
    
    if abs(rotation_deg) > 0.001:
        theta = np.radians(rotation_deg)
        cx, cy = float(n_tiles_x) / 2.0, float(n_tiles_y) / 2.0
        u_shifted = u_all - cx
        v_shifted = v_all - cy
        u_rot = u_shifted * np.cos(theta) - v_shifted * np.sin(theta) + cx
        v_rot = u_shifted * np.sin(theta) + v_shifted * np.cos(theta) + cy
        u_all, v_all = u_rot, v_rot

    # ── Translation (direct tile-unit offset) ──────────────────────────────────────────────
    # This is a simple shift in the tile UV space, which can be used to fine-tune the tile alignment by eye.  
    # It is NOT a pixel offset in the image space, which would produce non-uniform shifts across the perspective floor.
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
    pattern_result = get_pattern(pattern)(u_all, v_all, grout_h_frac=grout_h_frac_map, grout_v_frac=grout_v_frac_map, aspect_ratio=tile_width_cm / tile_height_cm if tile_height_cm > 0 else 1.0, du_dx=du_dx, du_dy=du_dy, dv_dx=dv_dx, dv_dy=dv_dy, grout_thickness_v=grout_v_thickness, grout_thickness_h=grout_h_thickness, uv_step_u=uv_step_u, uv_step_v=uv_step_v)
    
    if len(pattern_result) == 4:
        is_second, on_grout, u_frac, v_frac = pattern_result
    else:
        is_second, on_grout = pattern_result
        u_frac = u_all - np.floor(u_all)
        v_frac = v_all - np.floor(v_all)

    # ─── Texture / color fill ────────────────────────────────────────────────
    # Textures are sampled with mip-mapped bilinear filtering so distant tiles
    # don't shimmer/moiré (the classic give-away of a fake floor).
    if tile_texture is not None:
        mips1 = _build_mips(tile_texture)
        tex1 = _sample_texture_aa(mips1, u_frac, v_frac, uv_step_u, uv_step_v)
        if tile_texture2 is not None:
            mips2 = _build_mips(tile_texture2)
            tex2 = _sample_texture_aa(mips2, u_frac, v_frac, uv_step_u, uv_step_v)
            tile_fill = np.where(is_second[:, :, None], tex2, tex1)
        else:
            tile_fill = tex1
    else:
        tile_fill = np.where(is_second[:, :, None], tile2_bgr[None, None, :], tile_bgr[None, None, :]).astype(np.float32)

    # ── Per-tile tonal variation ────────────────────────────────────────────
    # Real tiles (especially stone / wood / fired ceramic) are never perfectly
    # identical — each piece has a slightly different shade and warmth.  A
    # stable per-cell hash gives every tile its own subtle tone so the floor
    # stops looking like one stamped, repeating texture.
    cell_u = np.floor(u_all)
    cell_v = np.floor(v_all)
    rnd_b = _hash01(cell_u, cell_v, 12.9898, 78.233)
    rnd_c = _hash01(cell_u, cell_v, 39.346, 11.135)
    bright_var = (1.0 + (rnd_b - 0.5) * 2.0 * TILE_BRIGHT_VARIATION)[:, :, None]
    # Warm/cool push: nudge R up & B down (or vice-versa) per tile.
    warm = (rnd_c - 0.5) * 2.0 * TILE_COLOR_VARIATION
    colour_shift = np.stack([1.0 - warm, np.ones_like(warm), 1.0 + warm], axis=-1)  # BGR
    tile_fill = tile_fill * bright_var * colour_shift

    # ── Grout compositing ──────────────────────────────────────────────
    step_max = np.maximum(uv_step_u, uv_step_v)
    fade_raw = 1.0 - np.clip((step_max - 0.25) / (0.5 - 0.25), 0.0, 1.0)
    grout_fade = fade_raw * fade_raw * (3.0 - 2.0 * fade_raw)
    grout_geom = np.clip(on_grout * grout_fade, 0.0, 1.0)
    grout_alpha = grout_geom[:, :, None]
    grout_f = grout_bgr[None, None, :].astype(np.float32)
    colour_img = grout_alpha * grout_f + (1.0 - grout_alpha) * tile_fill

    # ── Recessed-grout ambient occlusion + bevel catch-light ────────────────
    # Grout sits *below* the tile surface, so the tile pixels bordering a joint
    # fall into shadow (ambient occlusion) while the chamfered tile edge just
    # inside catches a thin highlight.  We derive both, pattern-agnostically,
    # by blurring the grout mask in screen space (so the effect auto-scales
    # with perspective — tight near the camera, soft in the distance).
    ao_k = max(3, min(h_img, w_img) // 220) | 1
    grout_soft = cv2.GaussianBlur(grout_geom.astype(np.float32), (ao_k, ao_k), 0)
    edge_halo = np.clip(grout_soft - grout_geom, 0.0, 1.0)
    tile_side = 1.0 - grout_geom  # don't shade the grout itself
    ao_shade = 1.0 - GROUT_AO_STRENGTH * edge_halo * tile_side
    # A thinner, brighter bevel highlight sits just inside the AO band.
    bevel = np.clip(edge_halo - grout_soft * 0.5, 0.0, 1.0)
    bevel_light = 1.0 + GROUT_BEVEL_HIGHLIGHT * bevel * tile_side
    colour_img = colour_img * ao_shade[:, :, None] * bevel_light[:, :, None]

    # ── Shadow & lighting recovery (LAB-based) ──────────────────────────────────────────────
    shadow_map = _extract_shadow_map(image, mask)
    ambient_tint = _extract_ambient_tint(image, mask)

    # Apply shadow map (preserves original room shadows on new tiles)
    colour_img = colour_img * shadow_map[:, :, None]

    # Apply ambient color temperature tint
    colour_img = colour_img * ambient_tint[None, None, :]

    # ── Clear-coat gloss sheen ──────────────────────────────────────────────
    # Glazed/polished tiles bounce the room light back at the camera.  We reuse
    # the recovered lighting (shadow_map > 1 = brighter-than-average areas,
    # i.e. where light pools) to add a soft additive specular sheen there, only
    # on the tile faces (not in the grout joints).
    gloss = np.clip(shadow_map - 1.0, 0.0, None)
    gloss = cv2.GaussianBlur(gloss.astype(np.float32), (ao_k, ao_k), 0)
    colour_img = colour_img + (gloss * GLOSS_SHEEN)[:, :, None] * (1.0 - grout_alpha)

    # Clamp to valid range (shadow + tint + gloss can push values beyond 255)
    colour_img = np.clip(colour_img, 0, 255)

    # ── Micro surface grain (solid colours only) ───────────────────────────
    # A flat fill is a dead give-away — even matte tiles have faint surface
    # noise.  Add a touch of stable grain on the tile faces (textures already
    # carry their own detail, so skip them).
    if tile_texture is None and MICRO_GRAIN_STD > 0:
        grain = np.random.default_rng(12345).standard_normal((h_img, w_img, 1)).astype(np.float32)
        colour_img = colour_img + grain * MICRO_GRAIN_STD * (1.0 - grout_alpha)
        colour_img = np.clip(colour_img, 0, 255)

    # Mild desaturation to match real-world appearance
    sat_factor = 0.90
    gray_ch = cv2.cvtColor(colour_img.astype(np.uint8), cv2.COLOR_BGR2GRAY)[:, :, None].astype(np.float32)
    colour_img = colour_img * sat_factor + gray_ch * (1.0 - sat_factor)
    colour_img = np.clip(colour_img, 0, 255).astype(np.uint8)

    # ── Seamless compositing (direct alpha blend) ──────────────────────────────────────────────
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

