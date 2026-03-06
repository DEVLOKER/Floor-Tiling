import torch
import os
import numpy as np
import json
import cv2
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

os.environ["CUDA_VISIBLE_DEVICES"] = ""

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

app = FastAPI()
MAX_SIZE = 1024 * 1024 * 10
app.state.limit_max_request_body = MAX_SIZE

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500", "http://localhost:5500",
        "http://127.0.0.1:8000", "http://localhost:8000",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

print("🟡 Loading SAM2 model on CPU...")
model_variant = "tiny"
try:
    model = build_sam2(model_variant, device="cpu")
    predictor = SAM2ImagePredictor(model)
    print("✅ Model loaded successfully on CPU")
except Exception as e:
    print(f"❌ Error loading model: {e}"); raise


@app.post("/segment-floor")
async def segment_floor(image: UploadFile = File(...),
                        click_x: float = Form(...), click_y: float = Form(...)):
    try:
        image_data = await image.read()
        pil_image  = Image.open(io.BytesIO(image_data)).convert("RGB")
        image_np   = np.array(pil_image)
        predictor.set_image(image_np)
        input_point = np.array([[click_x, click_y]], dtype=np.float32)
        input_label = np.array([1], dtype=np.int32)
        with torch.inference_mode():
            masks, scores, logits = predictor.predict(
                point_coords=input_point, point_labels=input_label,
                multimask_output=True)
        best = int(np.argmax(scores))
        mask = masks[best]
        if hasattr(mask, 'cpu'): mask = mask.cpu().numpy()
        mask = np.where(np.isnan(mask), 0, mask)
        return JSONResponse({"mask": mask.astype(float).tolist(),
                             "score": float(scores[best])})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def hex_to_bgr(h: str):
    h = h.lstrip('#')
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except:
        return (128, 128, 128)


def extract_floor_quad(mask: np.ndarray):
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    if len(ys) == 0: return None

    y_near = int(ys.max())
    y_far  = int(ys.min())

    def get_edges(y_center: int, band: int = 8):
        lefts, rights = [], []
        for dy in range(-band, band + 1):
            y = y_center + dy
            if 0 <= y < h:
                cols = np.where(mask[y] > 0)[0]
                if len(cols) >= 2:
                    lefts.append(int(cols[0]))
                    rights.append(int(cols[-1]))
        if not lefts:
            cols = np.where(mask[y_center] > 0)[0]
            if len(cols) < 2: return None, None
            return float(cols[0]), float(cols[-1])
        return float(np.median(lefts)), float(np.median(rights))

    nl, nr = get_edges(y_near, band=8)
    fl, fr = get_edges(y_far,  band=8)
    if nl is None or fl is None: return None

    near_left  = np.array([nl, float(y_near)], dtype=np.float32)
    near_right = np.array([nr, float(y_near)], dtype=np.float32)
    far_left   = np.array([fl, float(y_far)],  dtype=np.float32)
    far_right  = np.array([fr, float(y_far)],  dtype=np.float32)

    print(f"  Quad NL={near_left} NR={near_right} FL={far_left} FR={far_right}")
    return near_left, near_right, far_left, far_right


def estimate_real_depth_cm(near_left, near_right, far_left, far_right,
                           real_width_cm: float = 400.0) -> float:
    near_w = float(np.linalg.norm(near_right - near_left))
    far_w  = float(np.linalg.norm(far_right  - far_left))
    if near_w <= 0: return real_width_cm
    ratio = float(np.clip(far_w / near_w, 0.05, 0.99))
    real_depth = real_width_cm * (1.0 / ratio - 1.0)
    real_depth = float(np.clip(real_depth, 50.0, 2000.0))
    print(f"  near_w={near_w:.1f} far_w={far_w:.1f} ratio={ratio:.3f} depth={real_depth:.1f}cm")
    return real_depth


# ─────────────────────────────────────────────────────────────────────────────
# Pattern functions
# Each returns (is_second_color: bool array, on_grout: bool array)
# is_second_color: True = use grout_color2 (for checkerboard), False = tile_color
# ─────────────────────────────────────────────────────────────────────────────

def pattern_grid(u, v, grout_h_frac, grout_v_frac, **_):
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)
    on_grout = (
        (frac_u < grout_v_frac) | (frac_u > 1.0 - grout_v_frac) |
        (frac_v < grout_h_frac) | (frac_v > 1.0 - grout_h_frac)
    )
    is_second = np.zeros_like(on_grout)
    return is_second, on_grout


def pattern_brick(u, v, grout_h_frac, grout_v_frac, **_):
    row = np.floor(v).astype(np.int32)
    u_shifted = u + (row % 2) * 0.5
    frac_u = u_shifted - np.floor(u_shifted)
    frac_v = v - np.floor(v)
    on_grout = (
        (frac_u < grout_v_frac) | (frac_u > 1.0 - grout_v_frac) |
        (frac_v < grout_h_frac) | (frac_v > 1.0 - grout_h_frac)
    )
    is_second = np.zeros_like(on_grout)
    return is_second, on_grout


def pattern_diagonal(u, v, grout_h_frac, grout_v_frac, **_):
    SQRT2 = np.sqrt(2.0)
    u_rot = (u + v) / SQRT2
    v_rot = (-u + v) / SQRT2
    frac_u = u_rot - np.floor(u_rot)
    frac_v = v_rot - np.floor(v_rot)
    gf = (grout_h_frac + grout_v_frac) / 2.0
    on_grout = (
        (frac_u < gf) | (frac_u > 1.0 - gf) |
        (frac_v < gf) | (frac_v > 1.0 - gf)
    )
    is_second = np.zeros_like(on_grout)
    return is_second, on_grout


def pattern_herringbone(u, v, grout_h_frac, grout_v_frac, aspect_ratio=2.0, **_):
    AR  = float(aspect_ratio)
    S   = 1.0 / AR
    CW  = 1.0 + S
    CH  = 1.0 + S

    cell_x = np.floor(u / CW).astype(np.int32)
    cell_y = np.floor(v / CH).astype(np.int32)
    lu = u - cell_x * CW
    lv = v - cell_y * CH

    in_H = (lv < S)
    in_V = (~in_H) & (lv < S + 1.0)

    frac_u = np.where(in_H, lu,      lu / S)
    frac_v = np.where(in_H, lv / S,  lv - S)

    outside  = ~(in_H | in_V)
    gv = grout_v_frac
    gh = grout_h_frac
    on_grout = outside | (
        (frac_u < gv) | (frac_u > 1.0 - gv) |
        (frac_v < gh) | (frac_v > 1.0 - gh)
    )
    is_second = np.zeros_like(on_grout)
    return is_second, on_grout


def pattern_checkerboard(u, v, grout_h_frac, grout_v_frac, **_):
    """
    Checkerboard (chess) pattern.

    Every tile is the same size (square grid), but alternating tiles
    use a second colour — exactly like a chessboard.

    The second colour is the grout_color passed from the frontend,
    so the user picks:
      • tile_color  → light squares
      • grout_color → dark squares
    Grout lines are drawn between ALL tiles in a neutral mid-grey
    derived by blending the two colours.

    is_second = (floor(u) + floor(v)) % 2 == 1
    """
    frac_u = u - np.floor(u)
    frac_v = v - np.floor(v)

    # Grout lines (thin border around every tile)
    on_grout = (
        (frac_u < grout_v_frac) | (frac_u > 1.0 - grout_v_frac) |
        (frac_v < grout_h_frac) | (frac_v > 1.0 - grout_h_frac)
    )

    # Alternate tile colour based on checkerboard parity
    cell_u = np.floor(u).astype(np.int32)
    cell_v = np.floor(v).astype(np.int32)
    is_second = ((cell_u + cell_v) % 2) == 1   # bool array

    return is_second, on_grout


PATTERN_FN = {
    "grid":         pattern_grid,
    "brick":        pattern_brick,
    "diagonal":     pattern_diagonal,
    "herringbone":  pattern_herringbone,
    "checkerboard": pattern_checkerboard,
}


# ─────────────────────────────────────────────────────────────────────────────
# Core renderer
# ─────────────────────────────────────────────────────────────────────────────

def apply_perspective_tiles(image: np.ndarray,
                            mask: np.ndarray,
                            tile_color: str,
                            tile_color2: str,       # second colour (checkerboard dark tile / grout)
                            grout_color: str,
                            tile_width_cm: float,
                            tile_height_cm: float,
                            grout_h_thickness: int,
                            grout_v_thickness: int,
                            pattern: str) -> np.ndarray:

    mask = (mask > 0).astype(np.uint8)

    tile_bgr   = np.array(hex_to_bgr(tile_color),   dtype=np.float32)
    tile2_bgr  = np.array(hex_to_bgr(tile_color2),  dtype=np.float32)
    grout_bgr  = np.array(hex_to_bgr(grout_color),  dtype=np.float32)

    h_img, w_img = image.shape[:2]

    quad = extract_floor_quad(mask)
    if quad is None:
        print("⚠️ No quad"); return image

    near_left, near_right, far_left, far_right = quad
    near_width_px = float(np.linalg.norm(near_right - near_left))
    if near_width_px <= 0: return image

    real_width_cm = 400.0
    real_depth_cm = estimate_real_depth_cm(
        near_left, near_right, far_left, far_right, real_width_cm)

    n_tiles_x = max(2, int(round(real_width_cm  / tile_width_cm)))
    n_tiles_y = max(2, int(round(real_depth_cm  / tile_height_cm)))

    # ── Homography ────────────────────────────────────────────────────────────
    plane_pts = np.array([
        [0,         0        ],
        [n_tiles_x, 0        ],
        [n_tiles_x, n_tiles_y],
        [0,         n_tiles_y],
    ], dtype=np.float32)

    image_pts = np.array([far_left, far_right, near_right, near_left],
                         dtype=np.float32)

    H_fwd, _ = cv2.findHomography(plane_pts, image_pts)
    if H_fwd is None:
        print("⚠️ Homography failed"); return image
    H_inv = np.linalg.inv(H_fwd)

    # ── Compute grout fractions via H_inv (perspective-correct) ───────────────
    # We project the near-centre floor point and offset versions through H_inv.
    # The tile-plane distance for N image pixels = exact grout fraction.
    # This is correct at ALL depths because the homography encodes perspective.
    def img_to_plane(px, py):
        p = H_inv @ np.array([px, py, 1.0], dtype=np.float64)
        return p[0] / p[2], p[1] / p[2]

    cx = float((near_left[0] + near_right[0]) / 2)
    cy = float(near_left[1])

    u0, v0 = img_to_plane(cx, cy)
    u1, _  = img_to_plane(cx + grout_v_thickness, cy)       # horizontal offset → V grout
    _, v1  = img_to_plane(cx, cy - grout_h_thickness)       # vertical offset   → H grout

    grout_v_frac = float(np.clip(abs(u1 - u0), 0.0005, 0.45))
    grout_h_frac = float(np.clip(abs(v1 - v0), 0.0005, 0.45))

    print(f"🟡 Pattern={pattern}  tiles={n_tiles_x}×{n_tiles_y}  "
          f"tile={tile_width_cm}×{tile_height_cm}cm  "
          f"grout px=({grout_v_thickness},{grout_h_thickness})  "
          f"grout_frac H={grout_h_frac:.4f} V={grout_v_frac:.4f}")

    # ── Project all pixels ────────────────────────────────────────────────────
    ys_all, xs_all = np.mgrid[0:h_img, 0:w_img]
    ones = np.ones(h_img * w_img, dtype=np.float64)
    img_coords = np.stack([
        xs_all.ravel().astype(np.float64),
        ys_all.ravel().astype(np.float64),
        ones
    ], axis=1)

    plane_coords = img_coords @ H_inv.T
    w_div = plane_coords[:, 2]
    w_div = np.where(np.abs(w_div) < 1e-9, 1e-9, w_div)

    u_all = (plane_coords[:, 0] / w_div).reshape(h_img, w_img)
    v_all = (plane_coords[:, 1] / w_div).reshape(h_img, w_img)

    # ── Apply pattern ─────────────────────────────────────────────────────────
    fn = PATTERN_FN.get(pattern, pattern_grid)
    is_second, on_grout = fn(
        u_all, v_all,
        grout_h_frac=grout_h_frac,
        grout_v_frac=grout_v_frac,
        aspect_ratio=tile_width_cm / tile_height_cm if tile_height_cm > 0 else 2.0
    )

    # ── Lighting ──────────────────────────────────────────────────────────────
    orig_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    mb = float(np.mean(orig_gray[mask > 0])) if mask.any() else 0.5
    mb = max(mb, 0.01)
    light = np.clip(orig_gray / mb, 0.3, 2.0)

    # ── Colour map ────────────────────────────────────────────────────────────
    # Priority: grout > second colour > primary colour
    colour_img = np.where(
        on_grout[:, :, np.newaxis],
        grout_bgr[np.newaxis, np.newaxis, :],
        np.where(
            is_second[:, :, np.newaxis],
            tile2_bgr[np.newaxis, np.newaxis, :],
            tile_bgr[np.newaxis, np.newaxis, :]
        )
    ).astype(np.float32)

    colour_img *= light[:, :, np.newaxis]
    colour_img  = np.clip(colour_img, 0, 255).astype(np.uint8)

    # ── Composite ─────────────────────────────────────────────────────────────
    result = image.copy()
    result[mask > 0] = colour_img[mask > 0]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/apply-tiles")
async def apply_tiles(
    image:             UploadFile = File(...),
    mask:              str        = Form(...),
    tile_width:        float      = Form(30),
    tile_height:       float      = Form(30),
    tile_size:         float      = Form(None),
    tile_color:        str        = Form("#E8D1B5"),
    tile_color2:       str        = Form("#333333"),   # second colour for checkerboard
    grout_color:       str        = Form("#A9A9A9"),
    grout_h_thickness: int        = Form(3),
    grout_v_thickness: int        = Form(3),
    pattern:           str        = Form("grid"),
):
    try:
        image_data = await image.read()
        nparr      = np.frombuffer(image_data, np.uint8)
        img        = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return JSONResponse({"error": "Could not decode image"}, status_code=400)

        try:
            floor_mask = (np.array(json.loads(mask)) > 0).astype(np.uint8)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid mask"}, status_code=400)

        if floor_mask.shape != img.shape[:2]:
            floor_mask = cv2.resize(floor_mask, (img.shape[1], img.shape[0]),
                                    interpolation=cv2.INTER_NEAREST)

        if tile_size is not None:
            tile_width = tile_height = tile_size

        tile_width        = float(np.clip(tile_width,        5.0, 200.0))
        tile_height       = float(np.clip(tile_height,       5.0, 200.0))
        grout_h_thickness = int(np.clip(grout_h_thickness,   1,   20))
        grout_v_thickness = int(np.clip(grout_v_thickness,   1,   20))

        if pattern not in PATTERN_FN:
            pattern = "grid"

        result = apply_perspective_tiles(
            img, floor_mask,
            tile_color, tile_color2, grout_color,
            tile_width, tile_height,
            grout_h_thickness, grout_v_thickness,
            pattern
        )

        ok, buf = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            return JSONResponse({"error": "Encode failed"}, status_code=500)
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status": "healthy", "device": "cpu",
            "cuda_available": torch.cuda.is_available()}

@app.get("/")
async def root():
    return {"message": "Floor Tile Visualizer API", "status": "running"}



if __name__ == "__main__":
    import uvicorn
    # python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload --limit-max-requests 10485760
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        log_level="info",
        limit_max_requests=MAX_SIZE, 
        limit_max_requests_jitter=MAX_SIZE
    )