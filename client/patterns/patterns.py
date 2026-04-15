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
    aspect_ratio: float = 2.0,
    **_,
) -> tuple:
    L = max(float(aspect_ratio), 1.01)
    S = 1.5
    CW = L + S
    lu = u % CW
    lv = v % CW
    in_H1 = (lu < L) & (lv < S)
    in_V2 = (lu >= L) & (lv < L)
    in_V1 = (lu < S) & (lv >= S)
    in_H2 = (lu >= S) & (lv >= L)
    gap = ~(in_H1 | in_V1 | in_V2 | in_H2)
    fu = np.zeros_like(u)
    fv = np.zeros_like(v)
    fu = np.where(in_H1, lu / L, fu)
    fv = np.where(in_H1, lv / S, fv)
    fu = np.where(in_V1, lu / S, fu)
    fv = np.where(in_V1, (lv - S) / L, fv)
    fu = np.where(in_V2, (lu - L) / S, fu)
    fv = np.where(in_V2, lv / L, fv)
    fu = np.where(in_H2, (lu - S) / L, fu)
    fv = np.where(in_H2, (lv - L) / S, fv)
    fu = np.clip(fu, 0.0, 1.0)
    fv = np.clip(fv, 0.0, 1.0)
    dist_u = np.minimum(fu, 1.0 - fu)
    dist_v = np.minimum(fv, 1.0 - fv)
    alpha = np.where(
        gap,
        1.0,
        combine_grout(
            grout_alpha(dist_u, grout_v_frac / 4.0),
            grout_alpha(dist_v, grout_h_frac / 4.0),
        ),
    )
    return (np.zeros(u.shape, dtype=bool), alpha)


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
    return (is_second, on_grout)


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
    "versailles": pattern_versailles,
}


def get_pattern(pattern_name: str):
    """Return the pattern function for *pattern_name*, defaulting to grid."""
    return PATTERN_FUNCTIONS.get(pattern_name, pattern_grid)
