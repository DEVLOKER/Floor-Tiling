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

from floor_tiling.core import hex_to_bgr
from .tile_renderer import _feather_mask


# Strength knobs (tuned conservative — believable paint, not a filter look).
SHADING_MIN = 0.62             # clamp on relative luminance (deepest shadow)
SHADING_MAX = 1.12             # clamp on relative luminance (tame highlight blooms)
SHEEN_GAIN = {"matte": 0.0, "satin": 22.0, "gloss": 48.0}  # additive specular
MICRO_GRAIN_STD = 2.0          # subtle surface grain so flat paint isn't plastic
PAINT_SATURATION = 0.86        # pull the fill toward neutral so it reads as paint, not a neon fill
PAINT_TEXTURE_AMOUNT = 0.35    # always-on fine wall texture (high-freq only) for realism


def _tile_texture(texture: np.ndarray, h: int, w: int) -> np.ndarray:
    """Tile ``texture`` to cover an [h, w] canvas (screen-space repeat).

    The texture is scaled so it repeats ~3 times across the width — a sensible
    density for a wall finish / wallpaper without needing per-plane geometry.
    """
    th, tw = texture.shape[:2]
    target_w = max(64, w // 3)
    scale = target_w / float(tw)
    rw = max(1, int(round(tw * scale)))
    rh = max(1, int(round(th * scale)))
    tex = cv2.resize(texture, (rw, rh), interpolation=cv2.INTER_AREA)
    # Mirror into a 2×2 block so tiling has no hard seams (edges match).
    block = np.concatenate([tex, tex[:, ::-1]], axis=1)
    block = np.concatenate([block, block[::-1, :]], axis=0)
    bh, bw = block.shape[:2]
    reps_y = int(np.ceil(h / bh))
    reps_x = int(np.ceil(w / bw))
    tiled = np.tile(block, (reps_y, reps_x, 1))[:h, :w]
    return tiled.astype(np.float32)


# Real-world size of one texture repeat on the wall, in metres. Larger = the
# pattern looks bigger / repeats less often.
TEXTURE_REPEAT_M = 1.3
CORNER_AO_STRENGTH = 0.22  # how much to darken where two planes meet


def _reflect01(x: np.ndarray) -> np.ndarray:
    """Map any real coordinate into [0, 1] with a mirror (triangle wave).

    Reflecting at each repeat boundary makes neighbouring tiles share an
    identical edge, so an ordinary (non-seamless) photo tiles without the hard
    grid seams that plain wrapping (sawtooth) produces.
    """
    q = np.mod(x, 2.0)
    return np.where(q > 1.0, 2.0 - q, q)


def _bilinear_clamp(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinearly sample ``tex`` at (u, v) in [0,1], clamping at the edges.

    Used with reflected coordinates, so clamping (not wrapping) is correct —
    the mirror already guarantees continuity across tile boundaries.
    """
    th, tw = tex.shape[:2]
    fx = np.clip(u, 0.0, 1.0) * (tw - 1)
    fy = np.clip(v, 0.0, 1.0) * (th - 1)
    x0 = np.floor(fx).astype(np.int64)
    y0 = np.floor(fy).astype(np.int64)
    x1 = np.minimum(x0 + 1, tw - 1)
    y1 = np.minimum(y0 + 1, th - 1)
    wx = (fx - x0)[:, None]
    wy = (fy - y0)[:, None]
    Ia, Ib = tex[y0, x0], tex[y0, x1]
    Ic, Id = tex[y1, x0], tex[y1, x1]
    return (Ia * (1 - wx) + Ib * wx) * (1 - wy) + (Ic * (1 - wx) + Id * wx) * wy


def _texture_planes_fill(
    labeled: np.ndarray,
    depth: np.ndarray,
    texture: np.ndarray,
    repeat_m: float = TEXTURE_REPEAT_M,
) -> np.ndarray:
    """Perspective-map ``texture`` onto each plane of ``labeled`` using depth.

    Each plane id is back-projected to a 3D point cloud, a gravity-aligned plane
    basis is built, and the texture is sampled in that plane's metric
    coordinates — so it foreshortens with depth and, because every plane has its
    own basis, the pattern breaks at corners (which makes the room read as 3D).

    Distant parts of a plane are blended toward a pre-filtered (downsampled)
    copy of the texture to suppress the shimmer/aliasing that otherwise betrays
    a fake surface receding into depth.
    """
    h, w = depth.shape
    focal = float(max(h, w))
    cx, cy = w / 2.0, h / 2.0
    tex = texture.astype(np.float32)
    tex_half = cv2.pyrDown(tex)  # prefiltered mip for far pixels
    repeat_m = max(0.2, float(repeat_m))
    fill = np.zeros((h, w, 3), np.float32)
    covered = np.zeros((h, w), bool)

    for pid in np.unique(labeled):
        if pid == 0:
            continue
        ys, xs = np.where(labeled == pid)
        if len(xs) < 50:
            continue
        Z = depth[ys, xs].astype(np.float64)
        X = (xs - cx) / focal * Z
        Y = (ys - cy) / focal * Z
        P = np.stack([X, Y, Z], axis=1)
        c = P.mean(axis=0)
        Pc = P - c
        try:
            # Plane normal = smallest singular vector of the point cloud.
            _, _, vt = np.linalg.svd(Pc, full_matrices=False)
        except np.linalg.LinAlgError:
            continue
        normal = vt[2]

        # Gravity-aligned in-plane axes so the texture runs vertically on walls
        # (not along the PCA principal direction, which looks diagonal/streaky).
        # Camera space has +Y pointing down, so world-up is (0, -1, 0).
        up = np.array([0.0, -1.0, 0.0])
        if abs(float(np.dot(up, normal))) > 0.85:
            # Near-horizontal plane (ceiling): up ∥ normal is degenerate, so
            # orient with the camera's horizontal axis instead.
            ref = np.array([1.0, 0.0, 0.0])
        else:
            ref = up
        v_axis = ref - np.dot(ref, normal) * normal
        nv = np.linalg.norm(v_axis)
        v_axis = vt[0] if nv < 1e-6 else v_axis / nv
        u_axis = np.cross(normal, v_axis)
        u_axis = u_axis / (np.linalg.norm(u_axis) + 1e-8)

        s = Pc @ u_axis
        t = Pc @ v_axis
        # Mirror-tile so non-seamless photos repeat without visible grid seams.
        u = _reflect01(s / repeat_m)
        v = _reflect01(t / repeat_m)

        # Anti-alias: blend toward the prefiltered mip on far parts of the
        # plane (texel density grows with depth, so far ≈ aliasing-prone).
        col_full = _bilinear_clamp(tex, u, v)
        col_half = _bilinear_clamp(tex_half, u, v)
        z_lo, z_hi = np.percentile(Z, 10), np.percentile(Z, 95)
        w_far = np.clip((Z - z_lo) / max(z_hi - z_lo, 1e-6), 0.0, 1.0)[:, None]
        fill[ys, xs] = col_full * (1.0 - w_far) + col_half * w_far
        covered[ys, xs] = True

    # Any plane too small to map → fall back to a screen-space tile there.
    if not covered.all():
        tiled = _tile_texture(texture, h, w)
        miss = (labeled > 0) & (~covered)
        fill[miss] = tiled[miss]
    return fill


def _corner_ao(labeled: np.ndarray, k: int) -> np.ndarray:
    """Soft darkening map along boundaries between different plane ids.

    Real wall/wall and wall/ceiling junctions sit in slight shadow; adding it
    makes the corners read even when both planes have the same texture/tone.
    """
    lab = labeled.astype(np.int32)
    edge = np.zeros(lab.shape, np.float32)
    for dy, dx in ((1, 0), (0, 1)):
        a = lab[:-dy or None, :-dx or None]
        b = lab[dy:, dx:]
        diff = (a != b) & (a > 0) & (b > 0)
        edge[:-dy or None, :-dx or None][diff] = 1.0
        edge[dy:, dx:][diff] = 1.0
    return cv2.GaussianBlur(edge, (k, k), 0)


def apply_wall_paint(
    image: np.ndarray,
    mask: np.ndarray,
    paint_color: str,
    finish: str = "matte",
    opacity: float = 1.0,
    lighting_source: np.ndarray = None,
    texture: np.ndarray = None,
    depth: np.ndarray = None,
    texture_scale: float = TEXTURE_REPEAT_M,
    light_strength: float = 1.0,
    saturation: float = PAINT_SATURATION,
) -> np.ndarray:
    """Repaint the masked wall region with a colour or a texture.

    Args:
        image:       Image to composite the paint ONTO, BGR uint8 [H, W, 3].
                     This may be an already-edited composite (tiled floor,
                     other painted walls) so previous edits are preserved.
        mask:        Paint mask.  For texture painting this should be a LABELED
                     mask (each plane a distinct id) so the texture is mapped
                     per plane; for colour, any non-zero value = paint.
        depth:       Optional depth map [H, W]; enables per-plane perspective
                     texture mapping (with corner shading) instead of a flat
                     screen-space tile.
        paint_color: CSS hex colour of the new paint, e.g. ``"#C8D6E5"``.
        finish:      ``"matte"`` | ``"satin"`` | ``"gloss"`` — controls sheen.
        opacity:     0-1.  <1 lets the original wall colour show through
                     (useful for translucent / wash effects).
        lighting_source: Image to sample the wall's lighting/texture FROM
                     (the pristine original).  Keeping this separate from
                     ``image`` makes re-applying paint idempotent — the shading
                     is always derived from the real wall, never from a
                     previously-painted result (which would stack artefacts).
        texture:     Optional BGR texture image.  When given, the wall is
                     covered with the tiled texture (modulated by the wall's
                     real lighting) instead of a flat colour.

    Returns:
        BGR uint8 image with the wall repainted and seamlessly blended.
    """
    # Keep plane labels (for per-plane texture); derive a binary mask for
    # shading/feathering.
    labeled = mask
    binmask = (mask > 0).astype(np.uint8)
    if not binmask.any():
        return image
    h_img, w_img = image.shape[:2]

    # Lighting/texture always comes from the original; compositing happens onto
    # the (possibly already-edited) ``image``.
    src = image if lighting_source is None else lighting_source
    if src.shape[:2] != image.shape[:2]:
        src = cv2.resize(src, (image.shape[1], image.shape[0]))

    paint_bgr = np.array(hex_to_bgr(paint_color), dtype=np.float32)
    img_f = image.astype(np.float32)
    src_f = src.astype(np.float32)

    # ── Relative luminance (LAB L*) drives the shading ──────────────────────
    # LAB is perceptually uniform, so L* tracks how the eye reads brightness.
    lab = cv2.cvtColor(src, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]  # 0-255 range

    wall_mean_L = float(np.mean(L[binmask > 0]))
    wall_mean_L = max(wall_mean_L, 1.0)

    # ── Broad lighting only (COVER the old surface) ─────────────────────────
    # Real paint hides the wall underneath. So we shade with only the *broad*
    # room lighting (window gradient, corner shadows) and blur away the original
    # surface pattern — tile grout, old texture — otherwise it bleeds through
    # the new paint and the wall reads as "old tiles tinted", not repainted.
    # Non-wall pixels are set to the wall mean first so the large blur doesn't
    # drag in cabinet/window luminance at the edges.
    L_clean = np.where(binmask > 0, L, wall_mean_L).astype(np.float32)
    # Smoothly blur out the old surface (tile blotches, grout) keeping only the
    # room's broad lighting (window gradient, corner falloff). A large kernel is
    # what keeps the painted wall clean instead of blotchy.
    bk = max(5, min(h_img, w_img) // 10) | 1
    L_broad = cv2.GaussianBlur(L_clean, (bk, bk), 0)
    shading = np.clip(L_broad / wall_mean_L, SHADING_MIN, SHADING_MAX)
    # Lighting intensity (client-tunable): 0 = flat fill, 1 = natural, >1 = punchier.
    shading = 1.0 + (shading - 1.0) * float(light_strength)
    k = max(3, min(h_img, w_img) // 50) | 1

    # ── Corner shading (both colour & texture) ──────────────────────────────
    # Darken the junctions between adjacent painted planes so corners read even
    # when neighbouring planes share the same colour/tone. Needs only the
    # labeled mask (no depth), so it's free for colour mode too.
    if int(labeled.max()) > 1:
        ao = _corner_ao(labeled, k)
        shading = shading * (1.0 - CORNER_AO_STRENGTH * ao)

    if texture is not None:
        # Texture finish modulated only by broad lighting (so the old surface
        # pattern doesn't show through the texture either).
        if depth is not None and depth.shape[:2] == (h_img, w_img):
            # Per-plane perspective mapping → reads as 3D.
            fill = _texture_planes_fill(labeled, depth, texture, repeat_m=texture_scale)
        else:
            fill = _tile_texture(texture, h_img, w_img)
        painted = fill * shading[:, :, None]
    else:
        # Solid colour finish: flat paint under broad lighting, plus a touch of
        # stable micro-grain so it doesn't look plastic (no original pattern).
        painted = paint_bgr[None, None, :] * shading[:, :, None]
        if MICRO_GRAIN_STD > 0:
            grain = np.random.default_rng(7).standard_normal((h_img, w_img, 1)).astype(np.float32)
            painted = painted + grain * MICRO_GRAIN_STD

    # ── Finish sheen (satin / gloss) ────────────────────────────────────────
    # Glossier paints bounce light back at the camera where the wall is already
    # lit (shading > 1).  Add a soft additive specular there.
    gain = SHEEN_GAIN.get(finish, 0.0)
    if gain > 0.0:
        sheen = np.clip(shading - 1.0, 0.0, None)
        sheen = cv2.GaussianBlur(sheen.astype(np.float32), (k, k), 0)
        painted += (sheen * gain)[:, :, None]

    # ── Saturation (client-tunable): pull toward neutral so it reads as paint ─
    sat = float(np.clip(saturation, 0.0, 1.0))
    if sat < 1.0:
        gray = painted.mean(axis=2, keepdims=True)
        painted = painted * sat + gray * (1.0 - sat)

    # ── Fine surface texture (high-frequency only) ──────────────────────────
    # Add the wall's fine detail (orange-peel, scuffs, trim shadows) for realism
    # — but NEVER its broad brightness, which on bright/blown walls would wash the
    # colour to white. Always on (independent of opacity); it's a zero-mean
    # signal so it can't shift the colour toward white.
    dk = max(3, min(h_img, w_img) // 120) | 1
    detail = src_f - cv2.GaussianBlur(src_f, (dk, dk), 0)
    painted = painted + PAINT_TEXTURE_AMOUNT * detail
    painted = np.clip(painted, 0, 255)

    # ── Opacity = paint coverage ────────────────────────────────────────────
    # 1.0 (default) = fully opaque, the new colour covers the wall. Lower lets
    # the original wall show through as a translucent tint/wash (user opt-in).
    opacity = float(np.clip(opacity, 0.0, 1.0))
    if opacity < 1.0:
        painted = opacity * painted + (1.0 - opacity) * src_f

    # ── Seamless composite with a feathered edge ────────────────────────────
    # Composite onto ``image`` (the accumulated result) so other surfaces stay.
    alpha = _feather_mask(binmask, radius=3)[:, :, None]
    result = alpha * painted + (1.0 - alpha) * img_f

    return np.clip(result, 0, 255).astype(np.uint8)


__all__ = ["apply_wall_paint"]
