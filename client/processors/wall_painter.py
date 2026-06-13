"""Realistic wall re-painting.

Unlike the floor tiler — which synthesises a brand-new perspective surface —
wall painting must *keep the wall exactly where it is* and only change its
colour.  A flat colour fill looks fake, so we preserve everything that makes a
real painted wall read as real:

  - broad room lighting (the soft gradient from window → corner, cast shadows)
  - fine surface detail (orange-peel texture, trim shadows, scuffs)
  - an optional sheen for satin / gloss finishes

The technique is a luminance-preserving recolour: the new paint colour is
modulated by the wall's *relative* luminance so darker areas of the original
wall stay darker and lit areas stay lit.

Import via the package: ``from processors import apply_wall_paint``
"""
import cv2
import numpy as np

from core import hex_to_bgr
from .tile_renderer import _feather_mask


# Strength knobs (tuned conservative — believable paint, not a filter look).
WALL_DETAIL_STRENGTH = 0.6     # how much fine surface texture to carry over
SHADING_MIN = 0.45             # clamp on relative luminance (deepest shadow)
SHADING_MAX = 1.55             # clamp on relative luminance (brightest catch-light)
SHEEN_GAIN = {"matte": 0.0, "satin": 30.0, "gloss": 65.0}  # additive specular


def apply_wall_paint(
    image: np.ndarray,
    mask: np.ndarray,
    paint_color: str,
    finish: str = "matte",
    opacity: float = 1.0,
) -> np.ndarray:
    """Repaint the masked wall region with ``paint_color``.

    Args:
        image:       Room photo, BGR uint8 [H, W, 3].
        mask:        Wall mask, any non-zero value = wall.
        paint_color: CSS hex colour of the new paint, e.g. ``"#C8D6E5"``.
        finish:      ``"matte"`` | ``"satin"`` | ``"gloss"`` — controls sheen.
        opacity:     0-1.  <1 lets the original wall colour show through
                     (useful for translucent / wash effects).

    Returns:
        BGR uint8 image with the wall repainted and seamlessly blended.
    """
    mask = (mask > 0).astype(np.uint8)
    if not mask.any():
        return image

    paint_bgr = np.array(hex_to_bgr(paint_color), dtype=np.float32)
    img_f = image.astype(np.float32)

    # ── Relative luminance (LAB L*) drives the shading ──────────────────────
    # LAB is perceptually uniform, so L* tracks how the eye reads brightness.
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]  # 0-255 range

    wall_mean_L = float(np.mean(L[mask > 0]))
    wall_mean_L = max(wall_mean_L, 1.0)

    # Relative shading: 1.0 = average wall brightness, <1 shadow, >1 highlight.
    # Multiplying the flat paint colour by this keeps every shadow and lit
    # gradient of the real wall, so the paint "sits" on the actual surface.
    shading = np.clip(L / wall_mean_L, SHADING_MIN, SHADING_MAX)
    painted = paint_bgr[None, None, :] * shading[:, :, None]

    # ── Fine surface detail ─────────────────────────────────────────────────
    # The broad shading above misses small stuff (orange-peel, plaster bumps,
    # the thin shadow under a light switch).  Recover it as the high-frequency
    # residual of luminance and add it equally to all channels so the paint
    # hue is unchanged while the surface stops looking dead-flat.
    k = max(3, min(image.shape[:2]) // 50) | 1
    L_blur = cv2.GaussianBlur(L, (k, k), 0)
    detail = L - L_blur
    painted += detail[:, :, None] * WALL_DETAIL_STRENGTH

    # ── Finish sheen (satin / gloss) ────────────────────────────────────────
    # Glossier paints bounce light back at the camera where the wall is already
    # lit (shading > 1).  Add a soft additive specular there.
    gain = SHEEN_GAIN.get(finish, 0.0)
    if gain > 0.0:
        sheen = np.clip(shading - 1.0, 0.0, None)
        sheen = cv2.GaussianBlur(sheen.astype(np.float32), (k, k), 0)
        painted += (sheen * gain)[:, :, None]

    painted = np.clip(painted, 0, 255)

    # ── Opacity: let the original wall bleed through for wash effects ────────
    opacity = float(np.clip(opacity, 0.0, 1.0))
    if opacity < 1.0:
        painted = opacity * painted + (1.0 - opacity) * img_f

    # ── Seamless composite with a feathered edge ────────────────────────────
    alpha = _feather_mask(mask, radius=3)[:, :, None]
    result = alpha * painted + (1.0 - alpha) * img_f

    return np.clip(result, 0, 255).astype(np.uint8)


__all__ = ["apply_wall_paint"]
