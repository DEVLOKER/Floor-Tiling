"""Tile pattern generators — with anti-aliased grout lines"""
import numpy as np


# ── Anti-aliased grout helper ─────────────────────────────────────────────────

def _grout_alpha(dist: np.ndarray, half_frac: np.ndarray,
                 step: np.ndarray = None) -> np.ndarray:
    """
    Return a float grout mask [0..1] with thin, solid, anti-aliased grout lines.

    Strategy:
      - Keep half_frac as-is (controls actual line width = grout_thickness_px)
      - Use feather = max(half_frac * 0.3, step * 0.8) so the soft edge always
        spans at least ~1 pixel → lines appear solid even at 45° without being thick.

    At 45°, a line needs the feather to bleed into adjacent pixels to close gaps.
    Using step-based feather achieves this without widening the opaque core.

    Args:
        dist:      per-pixel distance to nearest tile boundary [0..0.5]
        half_frac: half grout width in UV units (= step * grout_thickness_px / 2)
        step:      per-pixel UV advance (= 1/tile_size_in_pixels at this location)
    """
    if step is not None:
        # Feather must span at least 0.8px so adjacent pixels get partial alpha
        # → no gaps in diagonal lines. DO NOT increase half_frac (keeps line thin).
        feather = np.maximum(half_frac * 0.3, step * 0.8)
    else:
        feather = half_frac * 0.4

    feather = np.clip(feather, 1e-6, half_frac * 2.0)
    t = np.clip((half_frac + feather - dist) / (feather + 1e-9), 0.0, 1.0)
    # Remap so: dist <= half_frac → alpha=1,  dist >= half_frac+feather → alpha=0
    t2 = np.clip((half_frac - dist) / (feather + 1e-9), -1.0, 1.0)
    t2 = (t2 + 1.0) * 0.5   # map [-1,1] → [0,1]
    return t2 * t2 * (3.0 - 2.0 * t2)   # cubic smoothstep

# def _grout_alpha(dist: np.ndarray, half_frac: np.ndarray,
#                  step: np.ndarray = None) -> np.ndarray:
#     if step is not None:
#         feather = np.maximum(half_frac * 0.3, step * 0.8)
#     else:
#         feather = half_frac * 0.4
#     feather = np.clip(feather, 1e-6, half_frac * 2.0)
#     t2 = np.clip((half_frac - dist) / (feather + 1e-9), -1.0, 1.0)
#     t2 = (t2 + 1.0) * 0.5
#     return t2 * t2 * (3.0 - 2.0 * t2)


def _combine_grout(alpha_u: np.ndarray, alpha_v: np.ndarray) -> np.ndarray:
    """Combine U and V grout alphas (union: max)."""
    return np.maximum(alpha_u, alpha_v)


# ── Rotated grout helper ──────────────────────────────────────────────────────

def _rotated_grout_fracs(du_dx, du_dy, dv_dx, dv_dy,
                          grout_thickness_v, grout_thickness_h,
                          angle_deg: float = 45.0):
    """
    Compute correct grout fractions for a rotated tile grid.
    Recomputes step sizes from rotated-space gradients so line thickness
    is correct for any rotation angle.
    """
    if du_dx is None:
        return None, None   # signal: use fallback

    rad = np.radians(angle_deg)
    c, s = np.cos(rad), np.sin(rad)

    du_rot_dx = c * du_dx + s * dv_dx
    du_rot_dy = c * du_dy + s * dv_dy
    dv_rot_dx = -s * du_dx + c * dv_dx
    dv_rot_dy = -s * du_dy + c * dv_dy

    step_u_rot = np.clip(np.sqrt(du_rot_dx**2 + du_rot_dy**2), 1e-6, 10.0)
    step_v_rot = np.clip(np.sqrt(dv_rot_dx**2 + dv_rot_dy**2), 1e-6, 10.0)

    grout_v_frac_rot = np.clip(step_u_rot * grout_thickness_v, 0.0005, 0.45)
    grout_h_frac_rot = np.clip(step_v_rot * grout_thickness_h, 0.0005, 0.45)

    return grout_v_frac_rot, grout_h_frac_rot


# ── Pattern functions ─────────────────────────────────────────────────────────

def pattern_grid(u: np.ndarray, v: np.ndarray,
                 grout_h_frac, grout_v_frac,
                 uv_step_u=None, uv_step_v=None, **_) -> tuple:
    """Standard grid pattern."""
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    alpha = _combine_grout(
        _grout_alpha(dist_u, grout_v_frac / 2.0, step=uv_step_u),
        _grout_alpha(dist_v, grout_h_frac / 2.0, step=uv_step_v),
    )
    return np.zeros(u.shape, dtype=bool), alpha


def pattern_brick(u: np.ndarray, v: np.ndarray,
                  grout_h_frac, grout_v_frac,
                  uv_step_u=None, uv_step_v=None, **_) -> tuple:
    """Brick (offset) pattern."""
    row = np.floor(v).astype(np.int32)
    u_shifted = u + (row % 2) * 0.5
    frac_u = u_shifted - np.floor(u_shifted)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    alpha = _combine_grout(
        _grout_alpha(dist_u, grout_v_frac / 2.0, step=uv_step_u),
        _grout_alpha(dist_v, grout_h_frac / 2.0, step=uv_step_v),
    )
    return np.zeros(u.shape, dtype=bool), alpha


def pattern_diagonal(u: np.ndarray, v: np.ndarray,
                     grout_h_frac, grout_v_frac,
                     du_dx=None, du_dy=None, dv_dx=None, dv_dy=None,
                     grout_thickness_v=1, grout_thickness_h=1,
                     uv_step_u=None, uv_step_v=None, **_) -> tuple:
    """Diagonal 45° pattern with correct anti-aliased grout lines."""
    SQRT2 = np.sqrt(2.0)
    u_rot = (u + v) / SQRT2
    v_rot = (-u + v) / SQRT2

    frac_u = u_rot - np.floor(u_rot)
    frac_v = v_rot - np.floor(v_rot)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    gv, gh = _rotated_grout_fracs(du_dx, du_dy, dv_dx, dv_dy,
                                   grout_thickness_v, grout_thickness_h, 45.0)
    if gv is None:
        gv, gh = grout_v_frac / np.sqrt(2), grout_h_frac / np.sqrt(2)

    # step_rot: per-pixel UV advance in rotated space (= gv / grout_thickness_v)
    step_u_rot = gv / max(grout_thickness_v, 1)
    step_v_rot = gh / max(grout_thickness_h, 1)

    alpha = _combine_grout(
        _grout_alpha(dist_u, gv / 2.0, step=step_u_rot),
        _grout_alpha(dist_v, gh / 2.0, step=step_v_rot),
    )
    return np.zeros(u.shape, dtype=bool), alpha


def pattern_herringbone(u: np.ndarray, v: np.ndarray,
                        grout_h_frac, grout_v_frac,
                        aspect_ratio: float = 2.0, **_) -> tuple:
    """Herringbone pattern."""
    L  = max(float(aspect_ratio), 1.01)
    S  = 1.5
    CW = L + S

    lu = u % CW
    lv = v % CW

    in_H1 = (lu <  L)  & (lv <  S)
    in_V2 = (lu >= L)  & (lv <  L)
    in_V1 = (lu <  S)  & (lv >= S)
    in_H2 = (lu >= S)  & (lv >= L)
    gap   = ~(in_H1 | in_V1 | in_V2 | in_H2)

    fu = np.zeros_like(u);  fv = np.zeros_like(v)
    fu = np.where(in_H1,  lu      / L, fu);  fv = np.where(in_H1,  lv      / S, fv)
    fu = np.where(in_V1,  lu      / S, fu);  fv = np.where(in_V1, (lv-S)   / L, fv)
    fu = np.where(in_V2, (lu-L)   / S, fu);  fv = np.where(in_V2,  lv      / L, fv)
    fu = np.where(in_H2, (lu-S)   / L, fu);  fv = np.where(in_H2, (lv-L)   / S, fv)
    fu = np.clip(fu, 0.0, 1.0);  fv = np.clip(fv, 0.0, 1.0)

    dist_u = np.minimum(fu, 1.0 - fu)
    dist_v = np.minimum(fv, 1.0 - fv)

    alpha = np.where(gap, 1.0, _combine_grout(
        _grout_alpha(dist_u, grout_v_frac / 4.0),
        _grout_alpha(dist_v, grout_h_frac / 4.0),
    ))
    return np.zeros(u.shape, dtype=bool), alpha


def pattern_checkerboard(u: np.ndarray, v: np.ndarray,
                         grout_h_frac, grout_v_frac,
                         uv_step_u=None, uv_step_v=None, **_) -> tuple:
    """Checkerboard pattern with alternating colors."""
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    alpha = _combine_grout(
        _grout_alpha(dist_u, grout_v_frac / 4.0, step=uv_step_u),
        _grout_alpha(dist_v, grout_h_frac / 4.0, step=uv_step_v),
    )
    cell_u = np.floor(u).astype(np.int32)
    cell_v = np.floor(v).astype(np.int32)
    is_second = ((cell_u + cell_v) % 2) == 1
    return is_second, alpha


def pattern_diagonal_checkerboard(u: np.ndarray, v: np.ndarray,
                                   grout_h_frac, grout_v_frac,
                                   du_dx=None, du_dy=None, dv_dx=None, dv_dy=None,
                                   grout_thickness_v=1, grout_thickness_h=1,
                                   uv_step_u=None, uv_step_v=None, **_) -> tuple:
    """Diagonal checkerboard — 45° grid with alternating colors and anti-aliased grout."""
    SQRT2 = np.sqrt(2.0)
    u_rot = (u + v) / SQRT2
    v_rot = (-u + v) / SQRT2

    frac_u = u_rot - np.floor(u_rot)
    frac_v = v_rot - np.floor(v_rot)
    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    gv, gh = _rotated_grout_fracs(du_dx, du_dy, dv_dx, dv_dy,
                                   grout_thickness_v, grout_thickness_h, 45.0)
    if gv is None:
        gv, gh = grout_v_frac / np.sqrt(2), grout_h_frac / np.sqrt(2)

    step_u_rot = gv / max(grout_thickness_v, 1)
    step_v_rot = gh / max(grout_thickness_h, 1)

    alpha = _combine_grout(
        _grout_alpha(dist_u, gv / 2.0, step=step_u_rot),
        _grout_alpha(dist_v, gh / 2.0, step=step_v_rot),
    )
    cell_u = np.floor(u_rot).astype(np.int32)
    cell_v = np.floor(v_rot).astype(np.int32)
    is_second = ((cell_u + cell_v) % 2) == 1
    return is_second, alpha


def pattern_chevron(u: np.ndarray, v: np.ndarray,
                    grout_h_frac,
                    grout_v_frac,
                    aspect_ratio: float = 1.0,   # unused in geometry, kept for API compat
                    uv_step_u=None,
                    uv_step_v=None,
                    grout_thickness_v=1,
                    grout_thickness_h=1,
                    du_dx=None, du_dy=None,
                    dv_dx=None, dv_dy=None,
                    **_) -> tuple:
    """
    Chevron (V-parquet) pattern.

    L = 1 always.  One arm = 1 u-unit wide × 1 v-unit tall.
    Physical size and V angle are determined by tile_width_cm / tile_height_cm,
    which is already encoded in the UV coordinates by the renderer.

    Layout (UV space, one full period):
    ┌──────────────────────────────┐
    │   u: 0────────1────────2    │
    │       ╲      ╱╲      ╱     │  v=0 (far)
    │        ╲ R  ╱  ╲ R  ╱      │
    │         ╲  ╱    ╲  ╱       │
    │      L   ╲╱  L   ╲╱        │  v=1 (near)
    └──────────────────────────────┘
    L = left-leaning arm  (is_second=False → tile_color / tile_texture)
    R = right-leaning arm (is_second=True  → tile_color2 / tile_texture2)

    One full V = period_u=2, period_v=1.
    """

    # ── Fold into one V cell (period 2 × 1) ──────────────────────────────
    u_mod     = u % 2.0          # ∈ [0, 2)
    v_mod     = v % 1.0          # ∈ [0, 1)

    right_arm = u_mod >= 1.0                              # True = right arm (\)
    u_arm     = np.where(right_arm, u_mod - 1.0, u_mod)  # ∈ [0, 1) for both arms

    # ── Shear: map parallelogram → unit square ────────────────────────────
    # Left arm  (/): apex at top-left,  base at bottom-right
    #   as u_arm goes 0→1, the V boundary shifts v by +1
    #   → subtract u_arm from v to "un-shear"
    # Right arm (\): mirror of left arm
    #   as u_arm goes 0→1 (left to right within arm), boundary shifts v by -1
    #   → subtract (1 - u_arm) from v to "un-shear"
    shear = np.where(right_arm, 1.0 - u_arm, u_arm)

    s_raw = (v_mod - shear) % 1.0   # across-plank position [0,1]
    t_raw = u_arm                    # along-plank  position [0,1]

    # ── Grout distances ───────────────────────────────────────────────────
    dist_s = np.minimum(s_raw, 1.0 - s_raw)   # long-edge grout
    dist_t = np.minimum(t_raw, 1.0 - t_raw)   # end-cut  grout

    # ── Adaptive grout fractions ──────────────────────────────────────────
    step_u = uv_step_u if uv_step_u is not None else np.full_like(u, 0.02)
    step_v = uv_step_v if uv_step_v is not None else np.full_like(v, 0.02)

    gf_long = np.clip(step_v * grout_thickness_h, 0.0005, 0.45)  # long-edge gap
    gf_end  = np.clip(step_u * grout_thickness_v, 0.0005, 0.45)  # end-cut gap

    alpha_long = _grout_alpha(dist_s, gf_long / 2.0, step=step_v)
    alpha_end  = _grout_alpha(dist_t, gf_end  / 2.0, step=step_u)

    # ── Apex seam: thin grout line where left and right arms meet ─────────
    dist_seam  = np.abs(u_mod - 1.0)            # distance from u=1 seam
    gf_seam    = np.clip(step_u * grout_thickness_v * 0.8, 0.0005, 0.30)
    alpha_seam = _grout_alpha(dist_seam, gf_seam / 2.0, step=step_u)

    # ── Combine ───────────────────────────────────────────────────────────
    on_grout  = np.maximum(np.maximum(alpha_long, alpha_end), alpha_seam)
    is_second = right_arm

    return is_second, on_grout


def pattern_basketweave(u: np.ndarray, v: np.ndarray,
                        grout_h_frac,
                        grout_v_frac,
                        aspect_ratio: float = 1.0,
                        uv_step_u=None,
                        uv_step_v=None,
                        grout_thickness_v: int = 1,
                        grout_thickness_h: int = 1,
                        du_dx=None, du_dy=None,
                        dv_dx=None, dv_dy=None,
                        **_) -> tuple:
    """
    2-plank basketweave pattern.

    GEOMETRY (in tile-UV space, 1 unit = 1 tile):
    ─────────────────────────────────────────────
    Period = 4×4 tiles.

    The floor is divided into 2×2 tile blocks. Blocks alternate H/V
    like a large checkerboard of blocks:

        H H | V V | H H | V V  ...
        H H | V V | H H | V V
        ────┼─────┼─────┼────
        V V | H H | V V | H H  ...
        V V | H H | V V | H H

    H-bundle (2×2 tile block):
        2 horizontal planks stacked in v
        Each plank = 2 tiles wide × 1 tile tall
        → Physical: (2 × tile_width_cm) long × tile_height_cm wide
        → 2:1 ratio when tile_width ≈ tile_height ✓

    V-bundle (2×2 tile block):
        2 vertical planks side-by-side in u
        Each plank = 1 tile wide × 2 tiles tall
        → Physical: tile_width_cm wide × (2 × tile_height_cm) long
        → 1:2 ratio ✓

    Grout lines:
        - Bundle edges: at every 2-tile boundary in both u and v
        - Within H-bundle: horizontal line at lv=1 (between the 2 planks)
        - Within V-bundle: vertical line at lu=1 (between the 2 planks)

    PREVIOUS BUG HISTORY:
        v1: bundle = N UV-units → 60×60cm with 30cm tiles → plain checkerboard
        v2: bundle = 1 UV-unit  → 30×30cm but alternated every tile → still checkerboard
        v3 (this): bundle = 2×2 tiles with block-level alternation → correct basketweave ✓
    """

    # ── Bundle assignment ─────────────────────────────────────────────────
    # Group tiles into 2×2 blocks, then checkerboard the blocks
    block_u = np.floor(u / 2.0).astype(int)
    block_v = np.floor(v / 2.0).astype(int)
    is_h    = ((block_u + block_v) % 2) == 0   # H when even, V when odd

    # ── Local position within the 2×2 tile bundle ────────────────────────
    lu = u % 2.0   # [0, 2)
    lv = v % 2.0   # [0, 2)

    # ── Per-pixel UV step sizes ───────────────────────────────────────────
    step_u = uv_step_u if uv_step_u is not None else np.full_like(u, 0.02)
    step_v = uv_step_v if uv_step_v is not None else np.full_like(v, 0.02)

    # ── H bundle grout ────────────────────────────────────────────────────
    # Between-plank line: at lv=1 (midpoint of [0,2))
    dist_mid_h   = np.abs(lv - 1.0)           # 0 at lv=1, max=1 at edges
    # Bundle left/right edges: at lu=0 and lu=2
    dist_edge_lu = np.minimum(lu, 2.0 - lu)
    # Bundle top/bottom edges: at lv=0 and lv=2
    dist_edge_lv = np.minimum(lv, 2.0 - lv)

    gf_h_mid  = np.clip(step_v * grout_thickness_h,       0.0005, 0.45)
    gf_h_edgeU= np.clip(step_u * grout_thickness_v,       0.0005, 0.45)
    gf_h_edgeV= np.clip(step_v * grout_thickness_h,       0.0005, 0.45)

    alpha_h = np.maximum(
        np.maximum(
            _grout_alpha(dist_mid_h,   gf_h_mid   / 2.0, step=step_v),
            _grout_alpha(dist_edge_lu, gf_h_edgeU / 2.0, step=step_u),
        ),
        _grout_alpha(dist_edge_lv, gf_h_edgeV / 2.0, step=step_v),
    )

    # ── V bundle grout ────────────────────────────────────────────────────
    # Between-plank line: at lu=1
    dist_mid_v   = np.abs(lu - 1.0)
    # Bundle left/right edges: at lu=0 and lu=2
    dist_edge_vu = np.minimum(lu, 2.0 - lu)
    # Bundle top/bottom edges: at lv=0 and lv=2
    dist_edge_vv = np.minimum(lv, 2.0 - lv)

    gf_v_mid  = np.clip(step_u * grout_thickness_v,       0.0005, 0.45)
    gf_v_edgeU= np.clip(step_u * grout_thickness_v,       0.0005, 0.45)
    gf_v_edgeV= np.clip(step_v * grout_thickness_h,       0.0005, 0.45)

    alpha_v = np.maximum(
        np.maximum(
            _grout_alpha(dist_mid_v,   gf_v_mid   / 2.0, step=step_u),
            _grout_alpha(dist_edge_vu, gf_v_edgeU / 2.0, step=step_u),
        ),
        _grout_alpha(dist_edge_vv, gf_v_edgeV / 2.0, step=step_v),
    )

    on_grout  = np.where(is_h, alpha_h, alpha_v)

    # Color alternates at PLANK level within each bundle (not bundle level)
    # H-bundle: top plank = color1, bottom plank = color2  (split in v)
    # V-bundle: left plank = color1, right plank = color2  (split in u)
    plank_h   = np.floor(lv).astype(int) % 2   # 0=top, 1=bottom (within H-bundle)
    plank_v   = np.floor(lu).astype(int) % 2   # 0=left, 1=right  (within V-bundle)
    is_second = np.where(is_h, plank_h == 1, plank_v == 1)

    return is_second, on_grout

# ── Pattern registry ──────────────────────────────────────────────────────────
PATTERN_FUNCTIONS = {
    "grid":                   pattern_grid,
    "brick":                  pattern_brick,
    "diagonal":               pattern_diagonal,
    "herringbone":            pattern_herringbone,
    "checkerboard":           pattern_checkerboard,
    "diagonal_checkerboard":  pattern_diagonal_checkerboard,
    "chevron":                pattern_chevron,
    "basketweave":                pattern_basketweave
}


def get_pattern(pattern_name: str):
    return PATTERN_FUNCTIONS.get(pattern_name, pattern_grid)


__all__ = [
    "pattern_grid", "pattern_brick", "pattern_diagonal",
    "pattern_herringbone", "pattern_checkerboard",
    "pattern_diagonal_checkerboard", "pattern_chevron", 
    "PATTERN_FUNCTIONS", "get_pattern",
]