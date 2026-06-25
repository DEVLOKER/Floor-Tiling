"""Internal grout-rendering helpers shared by all pattern functions.

These utilities compute soft grout alpha values and handle
rotated UV coordinate transformations.  They are not part of the
public API — import patterns via ``patterns/__init__.py`` instead.
"""

import numpy as np


def grout_alpha(
    dist: np.ndarray,
    half_frac: np.ndarray,
    step: np.ndarray = None,
) -> np.ndarray:
    """Return a smooth (0–1) grout alpha for pixels at *dist* from a grout line.

    Args:
        dist:      Distance of each pixel from the nearest grout centre-line
                   (in UV tile-space units).
        half_frac: Half the grout width in the same units.  Pixels with
                   ``dist < half_frac`` are fully inside the grout band.
        step:      Optional per-pixel UV step size used to set the feather
                   width.  When provided the feather adapts to perspective
                   (wider feather in the distance, narrower in the fore-
                   ground), producing even-looking grout lines.

    Returns:
        Float32 array in [0, 1].  1.0 = grout colour, 0.0 = tile colour.
    """
    if step is not None:
        feather = np.maximum(half_frac * 0.3, step * 0.8)
    else:
        feather = half_frac * 0.4

    feather = np.clip(feather, 1e-6, np.maximum(half_frac * 2.0, 1e-6))
    t = np.clip((half_frac + feather - dist) / (feather + 1e-9), 0.0, 1.0)
    t2 = np.clip((half_frac - dist) / (feather + 1e-9), -1.0, 1.0)
    t2 = (t2 + 1.0) * 0.5
    alpha = t2 * t2 * (3.0 - 2.0 * t2)

    # Force zero alpha where thickness is zero
    if isinstance(half_frac, np.ndarray):
        alpha[half_frac <= 0] = 0.0
    elif half_frac <= 0:
        return np.zeros_like(dist)

    return alpha


def combine_grout(
    alpha_u: np.ndarray,
    alpha_v: np.ndarray,
) -> np.ndarray:
    """Combine horizontal and vertical grout alphas with a max operation."""
    return np.maximum(alpha_u, alpha_v)


def rotated_grout_fracs(
    du_dx, du_dy, dv_dx, dv_dy,
    grout_thickness_v, grout_thickness_h,
    angle_deg: float = 45.0,
) -> tuple:
    """Compute grout fractions in a rotated UV frame (used by diagonal patterns).

    Returns a ``(grout_v_frac, grout_h_frac)`` tuple in the rotated frame,
    or ``(None, None)`` when the UV gradient arrays are unavailable.
    """
    if du_dx is None:
        return (None, None)

    rad = np.radians(angle_deg)
    c, s = np.cos(rad), np.sin(rad)

    du_rot_dx = c * du_dx + s * dv_dx
    du_rot_dy = c * du_dy + s * dv_dy
    dv_rot_dx = -s * du_dx + c * dv_dx
    dv_rot_dy = -s * du_dy + c * dv_dy

    step_u_rot = np.clip(np.sqrt(du_rot_dx**2 + du_rot_dy**2), 1e-6, 10.0)
    step_v_rot = np.clip(np.sqrt(dv_rot_dx**2 + dv_rot_dy**2), 1e-6, 10.0)

    grout_v_frac_rot = np.clip(step_u_rot * grout_thickness_v, 0.0, 0.45)
    grout_h_frac_rot = np.clip(step_v_rot * grout_thickness_h, 0.0, 0.45)
    return (grout_v_frac_rot, grout_h_frac_rot)
