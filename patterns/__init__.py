"""Tile pattern generators"""
import numpy as np


def pattern_grid(u: np.ndarray, v: np.ndarray,
                 grout_h_frac: float, grout_v_frac: float, **_) -> tuple:
    """Standard grid pattern.
    
    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)

    dist_u = np.minimum(frac_u, 1.0 - frac_u)  # 0 at vertical lines
    dist_v = np.minimum(frac_v, 1.0 - frac_v)  # 0 at horizontal lines

    on_grout = (dist_u < grout_v_frac / 2.0) | (dist_v < grout_h_frac / 2.0)

    is_second = np.zeros_like(on_grout)
    return is_second, on_grout 


def pattern_brick(u: np.ndarray, v: np.ndarray,
                  grout_h_frac: float, grout_v_frac: float, **_) -> tuple:
    """Brick (offset) pattern.
    
    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    row = np.floor(v).astype(np.int32)
    u_shifted = u + (row % 2) * 0.5
    frac_u = u_shifted - np.floor(u_shifted)
    frac_v = v - np.floor(v)

    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    on_grout = (dist_u < grout_v_frac / 2.0) | (dist_v < grout_h_frac / 2.0)

    is_second = np.zeros_like(on_grout)
    return is_second, on_grout    


def pattern_diagonal(u: np.ndarray, v: np.ndarray,
                     grout_h_frac: float, grout_v_frac: float, **_) -> tuple:
    """Diagonal 45° pattern.
    
    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    SQRT2 = np.sqrt(2.0)
    u_rot = (u + v) / SQRT2
    v_rot = (-u + v) / SQRT2
    frac_u = u_rot - np.floor(u_rot)
    frac_v = v_rot - np.floor(v_rot)

    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    # Average H/V fracs since the 45° rotation mixes both axes equally
    gf = (grout_h_frac + grout_v_frac) / 2.0
    on_grout = (dist_u < gf / 3.0) | (dist_v < gf / 3.0)

    is_second = np.zeros_like(on_grout)
    return is_second, on_grout

def pattern_herringbone(u: np.ndarray, v: np.ndarray,
                        grout_h_frac, grout_v_frac,
                        aspect_ratio: float = 2.0, **_) -> tuple:
    """Herringbone pattern.

    Each (L+S)×(L+S) repeat cell contains 4 brick regions + 1 grout junction:
      H1: horizontal brick  lu∈[0,L),  lv∈[0,S)
      V2: vertical   brick  lu∈[L,L+S),lv∈[0,L)
      V1: vertical   brick  lu∈[0,S),  lv∈[S,L+S)
      H2: horizontal brick  lu∈[S,L+S),lv∈[L,L+S)
      gap (lu∈[S,L), lv∈[S,L)): natural grout junction where 4 bricks meet

    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    L  = max(float(aspect_ratio), 1.01)
    S  = 1.5
    CW = L + S

    lu = u % CW
    lv = v % CW

    in_H1 = (lu <  L)  & (lv <  S)
    in_V2 = (lu >= L)  & (lv <  L)
    in_V1 = (lu <  S)  & (lv >= S)
    in_H2 = (lu >= S)  & (lv >= L)
    gap   = ~(in_H1 | in_V1 | in_V2 | in_H2)  # grout junction

    fu = np.zeros_like(u)
    fv = np.zeros_like(v)

    fu = np.where(in_H1,  lu      / L, fu)
    fv = np.where(in_H1,  lv      / S, fv)

    fu = np.where(in_V1,  lu      / S, fu)
    fv = np.where(in_V1, (lv - S) / L, fv)

    fu = np.where(in_V2, (lu - L) / S, fu)
    fv = np.where(in_V2,  lv      / L, fv)

    fu = np.where(in_H2, (lu - S) / L, fu)
    fv = np.where(in_H2, (lv - L) / S, fv)

    fu = np.clip(fu, 0.0, 1.0)
    fv = np.clip(fv, 0.0, 1.0)

    dist_u = np.minimum(fu, 1.0 - fu)
    dist_v = np.minimum(fv, 1.0 - fv)

    on_grout = gap | (dist_u < grout_v_frac / 4.0) | (dist_v < grout_h_frac / 4.0)

    is_second = np.zeros_like(on_grout)
    return is_second, on_grout  

def pattern_checkerboard(u: np.ndarray, v: np.ndarray,
                         grout_h_frac: float, grout_v_frac: float, **_) -> tuple:
    """Checkerboard (chess) pattern with alternating colors.
    
    Every tile alternates between two colors in a chessboard pattern.
    
    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    # return is_second, on_grout
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)

    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    on_grout = (dist_u < grout_v_frac / 4.0) | (dist_v < grout_h_frac / 4.0)

    # Alternate tile colour based on checkerboard parity
    cell_u = np.floor(u).astype(np.int32)
    cell_v = np.floor(v).astype(np.int32)
    is_second = ((cell_u + cell_v) % 2) == 1

    return is_second, on_grout    


def pattern_diagonal_checkerboard(u: np.ndarray, v: np.ndarray,
                                  grout_h_frac: float, grout_v_frac: float, **_) -> tuple:
    """Diagonal Chess pattern — 45° grid with alternating colors.
    
    Combines diagonal 45° grid with checkerboard color alternation.
    Result: diamond-shaped tiles in two colors, like a chessboard tilted 45°.
    
    Returns:
        Tuple of (is_second, on_grout) boolean arrays
    """
    SQRT2 = np.sqrt(2.0)
    u_rot = (u + v) / SQRT2
    v_rot = (-u + v) / SQRT2

    frac_u = u_rot - np.floor(u_rot)
    frac_v = v_rot - np.floor(v_rot)

    dist_u = np.minimum(frac_u, 1.0 - frac_u)
    dist_v = np.minimum(frac_v, 1.0 - frac_v)

    gf = (grout_h_frac + grout_v_frac) / 2.0
    on_grout = (dist_u < gf / 4.0) | (dist_v < gf / 4.0)

    # Chess parity in rotated tile indices
    cell_u = np.floor(u_rot).astype(np.int32)
    cell_v = np.floor(v_rot).astype(np.int32)
    is_second = ((cell_u + cell_v) % 2) == 1

    return is_second, on_grout    


# Pattern registry
PATTERN_FUNCTIONS = {
    "grid": pattern_grid,
    "brick": pattern_brick,
    "diagonal": pattern_diagonal,
    "herringbone": pattern_herringbone,
    "checkerboard": pattern_checkerboard,
    "diagonal_checkerboard": pattern_diagonal_checkerboard,
}


def get_pattern(pattern_name: str):
    """Get pattern function by name.
    
    Args:
        pattern_name: Name of the pattern
    
    Returns:
        Pattern function or default grid function
    """
    return PATTERN_FUNCTIONS.get(pattern_name, pattern_grid)


__all__ = [
    "pattern_grid",
    "pattern_brick",
    "pattern_diagonal",
    "pattern_herringbone",
    "pattern_checkerboard",
    "pattern_diagonal_checkerboard",
    "PATTERN_FUNCTIONS",
    "get_pattern",
]
