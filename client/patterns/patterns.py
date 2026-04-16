"""All built-in tile pattern functions + the pattern registry.

Each pattern function has the signature::

    pattern_*(u, v, grout_h_frac, grout_v_frac, **kwargs)
        -> (is_second: np.ndarray[bool], on_grout: np.ndarray[float])

``is_second`` selects which tiles use the secondary colour / texture.
``on_grout`` is a 0-1 alpha map (1 = fully on grout).
"""

from __future__ import annotations

import numpy as np

from .base import grout_alpha, combine_grout


# ─── Standard patterns ────────────────────────────────────────────────────────

def pattern_grid(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    uv_step_u=None, uv_step_v=None,
    **_,
) -> tuple:
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 2.0, step=uv_step_u),
        grout_alpha(dist_v, grout_h_frac / 2.0, step=uv_step_v),
    )
    return (np.zeros(u.shape, dtype=bool), alpha)


def pattern_brick(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    uv_step_u=None, uv_step_v=None,
    **_,
) -> tuple:
    row = np.floor(v).astype(np.int32)
    u_shifted = u + row % 2 * 0.5
    frac_u = u_shifted - np.floor(u_shifted)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 2.0, step=uv_step_u),
        grout_alpha(dist_v, grout_h_frac / 2.0, step=uv_step_v),
    )
    return (np.zeros(u.shape, dtype=bool), alpha)


def pattern_herringbone(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 3.0,
    **_,
) -> tuple:
    """Mathematical Herringbone pattern.
    
    Returns (is_second, on_grout, custom_u, custom_v).
    Custom UVs ensure vertical tiles rotate their texture by 90-degrees so grain runs lengthwise.
    """
    L = max(float(aspect_ratio), 1.01)
    L_int = max(2, int(round(L)))
    
    # Map to uniform coordinate space where short edge is 1 unit.
    X_unrot = u * L
    Y_unrot = v
    
    # Classic Herringbone is laid diagonally (45 degrees) relative to the grid.
    # We rotate the uniform coordinates by 45 degrees (pi/4) before processing.
    theta = np.pi / 4.0
    c, s = np.cos(theta), np.sin(theta)
    
    X = X_unrot * c - Y_unrot * s
    Y = X_unrot * s + Y_unrot * c
    
    ix = np.floor(X).astype(np.int32)
    iy = np.floor(Y).astype(np.int32)
    
    S = ix + iy
    S_m = S % (2 * L_int)
    
    is_H = S_m < L_int
    is_V = ~is_H
    
    # Local coordinates for H-tiles
    tile_start_x_H = ix - S_m
    tile_start_y_H = iy
    local_u_H = X - tile_start_x_H
    local_v_H = Y - tile_start_y_H
    
    # Local coordinates for V-tiles
    tile_start_y_V = iy - (S_m - L_int)
    tile_start_x_V = ix
    local_u_V = X - tile_start_x_V
    local_v_V = Y - tile_start_y_V
    
    # Distances for grout.
    # dist_x is distance to the nearest vertical edge in X units.
    dist_x = np.where(
        is_H, 
        np.minimum(local_u_H, L_int - local_u_H), 
        np.minimum(local_u_V, 1.0 - local_u_V)
    )
    # dist_y is distance to the nearest horizontal edge in Y units.
    dist_y = np.where(
        is_H, 
        np.minimum(local_v_H, 1.0 - local_v_H), 
        np.minimum(local_v_V, L_int - local_v_V)
    )
    
    # Convert distances back to original u, v space for the caller's grout fractions.
    dist_u = dist_x / L
    dist_v = dist_y
    
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 2.0),
        grout_alpha(dist_v, grout_h_frac / 2.0),
    )
    
    # Texture UV mappings (0 to 1).
    # For H tiles: U spans the length (L_int), V spans the width (1.0).
    # For V tiles: To rotate the grain perfectly, we map U to the V-tile's length (which is along Y),
    # and V to the V-tile's width (which is along X).
    custom_u = np.where(is_H, local_u_H / L_int, local_v_V / L_int)
    custom_v = np.where(is_H, local_v_H, 1.0 - local_u_V)
    
    return (is_V, alpha, custom_u, custom_v)


def pattern_checkerboard(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    uv_step_u=None, uv_step_v=None,
    **_,
) -> tuple:
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 4.0, step=uv_step_u),
        grout_alpha(dist_v, grout_h_frac / 4.0, step=uv_step_v),
    )
    cell_u = np.floor(u).astype(np.int32)
    cell_v = np.floor(v).astype(np.int32)
    is_second = (cell_u + cell_v) % 2 == 1
    return (is_second, alpha)


def pattern_chevron(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 1.0,
    uv_step_u=None, uv_step_v=None,
    grout_thickness_v=1, grout_thickness_h=1,
    du_dx=None, du_dy=None, dv_dx=None, dv_dy=None,
    **_,
) -> tuple:
    u_mod = u % 2.0
    v_mod = v % 1.0
    right_arm = u_mod >= 1.0
    u_arm = np.where(right_arm, u_mod - 1.0, u_mod)
    shear = np.where(right_arm, 1.0 - u_arm, u_arm)
    s_raw = (v_mod - shear) % 1.0
    t_raw = u_arm
    dist_s = np.minimum(s_raw, 1.0 - s_raw)
    dist_t = np.minimum(t_raw, 1.0 - t_raw)
    step_u = uv_step_u if uv_step_u is not None else np.full_like(u, 0.02)
    step_v = uv_step_v if uv_step_v is not None else np.full_like(v, 0.02)
    gf_long = np.clip(step_v * grout_thickness_h, 0.0, 0.45)
    gf_end = np.clip(step_u * grout_thickness_v, 0.0, 0.45)
    alpha_long = grout_alpha(dist_s, gf_long / 2.0, step=step_v)
    alpha_end = grout_alpha(dist_t, gf_end / 2.0, step=step_u)
    dist_seam = np.abs(u_mod - 1.0)
    gf_seam = np.clip(step_u * grout_thickness_v * 0.8, 0.0, 0.3)
    alpha_seam = grout_alpha(dist_seam, gf_seam / 2.0, step=step_u)
    on_grout = np.maximum(np.maximum(alpha_long, alpha_end), alpha_seam)
    return (right_arm, on_grout)


def pattern_basketweave(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 1.0,
    uv_step_u=None, uv_step_v=None,
    grout_thickness_v: int = 1, grout_thickness_h: int = 1,
    du_dx=None, du_dy=None, dv_dx=None, dv_dy=None,
    **_,
) -> tuple:
    block_u = np.floor(u / 2.0).astype(int)
    block_v = np.floor(v / 2.0).astype(int)
    is_h = (block_u + block_v) % 2 == 0
    lu = u % 2.0
    lv = v % 2.0
    step_u = uv_step_u if uv_step_u is not None else np.full_like(u, 0.02)
    step_v = uv_step_v if uv_step_v is not None else np.full_like(v, 0.02)
    dist_mid_h = np.abs(lv - 1.0)
    dist_edge_lu = np.minimum(lu, 2.0 - lu)
    dist_edge_lv = np.minimum(lv, 2.0 - lv)
    gf_h_mid = np.clip(step_v * grout_thickness_h, 0.0, 0.45)
    gf_h_edgeU = np.clip(step_u * grout_thickness_v, 0.0, 0.45)
    gf_h_edgeV = np.clip(step_v * grout_thickness_h, 0.0, 0.45)
    alpha_h = np.maximum(
        np.maximum(
            grout_alpha(dist_mid_h, gf_h_mid / 2.0, step=step_v),
            grout_alpha(dist_edge_lu, gf_h_edgeU / 2.0, step=step_u),
        ),
        grout_alpha(dist_edge_lv, gf_h_edgeV / 2.0, step=step_v),
    )
    dist_mid_v = np.abs(lu - 1.0)
    dist_edge_vu = np.minimum(lu, 2.0 - lu)
    dist_edge_vv = np.minimum(lv, 2.0 - lv)
    gf_v_mid = np.clip(step_u * grout_thickness_v, 0.0, 0.45)
    gf_v_edgeU = np.clip(step_u * grout_thickness_v, 0.0, 0.45)
    gf_v_edgeV = np.clip(step_v * grout_thickness_h, 0.0, 0.45)
    alpha_v = np.maximum(
        np.maximum(
            grout_alpha(dist_mid_v, gf_v_mid / 2.0, step=step_u),
            grout_alpha(dist_edge_vu, gf_v_edgeU / 2.0, step=step_u),
        ),
        grout_alpha(dist_edge_vv, gf_v_edgeV / 2.0, step=step_v),
    )
    on_grout = np.where(is_h, alpha_h, alpha_v)
    is_second = ~is_h
    
    # Custom UV logic for texture grain rotation
    custom_u = np.where(is_h, lu / 2.0, lv / 2.0)
    custom_v = np.where(is_h, lv % 1.0, 1.0 - (lu % 1.0))
    
    return (is_second, on_grout, custom_u, custom_v)


def pattern_straight_weave(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 1.0,
    uv_step_u=None, uv_step_v=None,
    **_,
) -> tuple:
    # A simple grid pattern where colors alternate by column (vertical stripes).
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)
    
    step_u = uv_step_u * 2.0 if uv_step_u is not None else grout_v_frac
    step_v = uv_step_v * 2.0 if uv_step_v is not None else grout_h_frac
    
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 2.0, step=step_u),
        grout_alpha(dist_v, grout_h_frac / 2.0, step=step_v),
    )
    
    cell_u = np.floor(u).astype(np.int32)
    is_second = (cell_u % 2) == 1
    
    return (is_second, alpha)


def pattern_bookmatch(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 1.0,
    uv_step_u=None, uv_step_v=None,
    **_,
) -> tuple:
    # Bookmatch lays tiles in a grid but mirrors the texture coordinates
    # to create a butterfly/diamond pattern across 4 abutting slabs.
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)
    
    step_u = uv_step_u * 2.0 if uv_step_u is not None else grout_v_frac
    step_v = uv_step_v * 2.0 if uv_step_v is not None else grout_h_frac
    
    alpha = combine_grout(
        grout_alpha(dist_u, grout_v_frac / 2.0, step=step_u),
        grout_alpha(dist_v, grout_h_frac / 2.0, step=step_v),
    )
    
    cell_u = np.floor(u).astype(np.int32)
    cell_v = np.floor(v).astype(np.int32)
    
    # 4-Slab Bookmatch: mirror U on odd columns, V on odd rows
    custom_u = np.where((cell_u % 2) == 1, 1.0 - frac_u, frac_u)
    custom_v = np.where((cell_v % 2) == 1, 1.0 - frac_v, frac_v)
    
    is_second = np.zeros_like(u, dtype=bool)
    
    return (is_second, alpha, custom_u, custom_v)





def pattern_versailles(
    u: np.ndarray, v: np.ndarray,
    grout_h_frac, grout_v_frac,
    aspect_ratio: float = 1.0,
    uv_step_u=None, uv_step_v=None,
    grout_thickness_v: int = 1, grout_thickness_h: int = 1,
    du_dx=None, du_dy=None, dv_dx=None, dv_dy=None,
    **_,
) -> tuple:
    CELL = 4.0
    ar = float(aspect_ratio) if aspect_ratio and aspect_ratio > 0 else 1.0
    uc = u * 2.0 % CELL
    vc = v * 2.0 * ar % CELL

    def dist_to_boundaries(c):
        d0 = np.minimum(c, CELL - c)
        d1 = np.abs(c - 1.0)
        d3 = np.abs(c - 3.0)
        return np.minimum(d0, np.minimum(d1, d3))

    dist_u = dist_to_boundaries(uc)
    dist_v = dist_to_boundaries(vc)
    step_u = uv_step_u * 2.0 if uv_step_u is not None else grout_v_frac
    step_v = uv_step_v * 2.0 * ar if uv_step_v is not None else grout_h_frac
    gf_u = np.clip(step_u * grout_thickness_v / 2.0, 0.0, 0.4)
    gf_v = np.clip(step_v * grout_thickness_h / 2.0, 0.0, 0.4)
    alpha = np.maximum(
        grout_alpha(dist_u, gf_u / 2.0, step=step_u),
        grout_alpha(dist_v, gf_v / 2.0, step=step_v),
    )
    in_center = (uc >= 1.0) & (uc < 3.0) & (vc >= 1.0) & (vc < 3.0)
    is_second = ~in_center
    return (is_second, alpha)


# ─── Registry ─────────────────────────────────────────────────────────────────

PATTERN_FUNCTIONS: dict = {
    "grid": pattern_grid,
    "brick": pattern_brick,
    "herringbone": pattern_herringbone,
    "checkerboard": pattern_checkerboard,
    "chevron": pattern_chevron,
    "basketweave": pattern_basketweave,
    "straightweave": pattern_straight_weave,
    "bookmatch": pattern_bookmatch,
    "versailles": pattern_versailles,
}


def get_pattern(pattern_name: str):
    """Return the pattern function for *pattern_name*, defaulting to grid."""
    return PATTERN_FUNCTIONS.get(pattern_name, pattern_grid)
