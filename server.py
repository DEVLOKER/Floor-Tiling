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
        r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        return (b, g, r)
    except: return (128,128,128)


def estimate_vanishing_point(mask: np.ndarray):
    """
    Estimate the vanishing point (where the floor meets the wall).
    Strategy: find the top edge of the mask and fit a horizontal line.
    The VP x is the horizontal centre of the floor at the top edge.
    The VP y is slightly above that top edge.
    """
    h, w = mask.shape
    # For each column, find the topmost mask pixel
    top_y = np.full(w, h, dtype=np.float32)
    for x in range(w):
        col = np.where(mask[:, x] > 0)[0]
        if len(col): top_y[x] = float(col.min())

    # Only use columns that actually have floor pixels
    valid_cols = np.where(top_y < h)[0]
    if len(valid_cols) < 2:
        return w / 2.0, 0.0

    # Robust estimate: use median of top-edge y values in centre 60% of floor
    x_min, x_max = valid_cols.min(), valid_cols.max()
    cx = (x_min + x_max) // 2
    margin = (x_max - x_min) // 5
    centre_cols = valid_cols[(valid_cols > x_min + margin) &
                             (valid_cols < x_max - margin)]
    if len(centre_cols) == 0:
        centre_cols = valid_cols

    vp_y = float(np.median(top_y[centre_cols]))
    vp_x = float(cx)

    # Push VP slightly above the top edge
    vp_y -= 2
    print(f"  Vanishing point: ({vp_x:.1f}, {vp_y:.1f})")
    return vp_x, vp_y


def get_near_edge(mask: np.ndarray):
    """Return (y_near, x_left_near, x_right_near) — the bottom row of the mask."""
    ys, xs = np.where(mask > 0)
    if len(ys) == 0: return None
    y_near = int(ys.max())
    cols   = np.where(mask[y_near] > 0)[0]
    return y_near, int(cols.min()), int(cols.max())


# ─────────────────────────────────────────────────────────────────────────────
# Core renderer
# ─────────────────────────────────────────────────────────────────────────────

def apply_perspective_tiles(image: np.ndarray, mask: np.ndarray,
                            tile_color: str, grout_color: str,
                            tile_size_cm: float, pattern: str) -> np.ndarray:
    """
    Perspective-correct tiling using a vanishing-point coordinate system.

    Algorithm
    ---------
    For every pixel (x, y) inside the mask:

    1.  Compute rays from the vanishing point VP through (x, y).
    2.  Measure depth  d = distance from VP along the ray, normalised so
        d=1 at the near edge (bottom of floor).
    3.  Horizontal coordinate  u = angle of the ray relative to the floor
        centre, also normalised.
    4.  Perspective-correct tile coords:
          tile_u  =  u / d  *  scale_u
          tile_v  =  (1/d)  *  scale_v
        This gives smaller tiles near the VP and larger near the camera,
        exactly matching real perspective.
    5.  Grout lines where frac(tile_u) or frac(tile_v) < grout_fraction.
    6.  Lighting from original image brightness.
    7.  Composite onto original using mask as clip.

    No quad fitting → no gaps.  Straight grout lines because coordinates
    are derived from a fixed VP, not from the noisy mask boundary.
    """
    mask = (mask > 0).astype(np.uint8)

    tile_bgr  = np.array(hex_to_bgr(tile_color),  dtype=np.float32)
    grout_bgr = np.array(hex_to_bgr(grout_color), dtype=np.float32)

    h_img, w_img = image.shape[:2]

    near = get_near_edge(mask)
    if near is None: return image
    y_near, x_left_near, x_right_near = near
    near_width_px = float(x_right_near - x_left_near)
    if near_width_px <= 0: return image

    vp_x, vp_y = estimate_vanishing_point(mask)

    # Real-world scale
    real_width_cm = 400.0
    px_per_cm     = near_width_px / real_width_cm
    real_depth_cm = (y_near - vp_y) / px_per_cm if px_per_cm > 0 else 300.0

    # How many tiles fit
    n_tiles_x = max(4, int(np.ceil(real_width_cm / tile_size_cm)))
    n_tiles_y = max(4, int(np.ceil(real_depth_cm  / tile_size_cm)))
    grout_f   = 0.05   # 5 % of tile → thin grout line

    print(f"🟡 VP-based tiling  tiles={n_tiles_x}×{n_tiles_y}  "
          f"near_w={near_width_px:.0f}  depth={y_near - vp_y:.0f} px")

    # ── build pixel coordinate grids ─────────────────────────────────────────
    ys_grid, xs_grid = np.mgrid[0:h_img, 0:w_img]   # (H,W)

    # Vector from VP to each pixel
    dx = xs_grid.astype(np.float32) - vp_x
    dy = ys_grid.astype(np.float32) - vp_y          # positive downward

    # Only pixels below VP (dy > 0) are on the floor
    # dy_near = y_near - vp_y  (depth of the near edge)
    dy_near = float(y_near) - vp_y
    if dy_near <= 0: dy_near = 1.0

    # Normalised depth d:  d=1 at near edge,  d→0 at VP
    d = dy / dy_near   # (H,W)

    # Horizontal angle normalised by near-edge half-width
    # At depth d the apparent half-width is d * (near_width_px/2)
    half_w_near = near_width_px / 2.0
    u_norm = dx / (d * half_w_near + 1e-6)   # ∈ [-1, 1] at near edge

    # Perspective-correct tile coordinates
    # tile_u: advances n_tiles_x over u_norm in [-1,1]
    tile_u = (u_norm + 1.0) / 2.0 * n_tiles_x   # 0..n_tiles_x

    # tile_v: advances n_tiles_y as 1/d goes from 1 (near) to ∞ (VP)
    # Map: v=0 at near (d=1), v=n_tiles_y at far (d≈0)
    # Use   tile_v = (1/d - 1) * scale
    # Choose scale so that tile_v = n_tiles_y when d = vp_y/y_near (approx)
    scale_v = n_tiles_y / (1.0 / max(vp_y / y_near, 0.05) - 1.0 + 1e-6) \
              if y_near > 0 else n_tiles_y
    # Simpler & robust: tile_v = (1-d)/d * n_tiles_y   → 0 at near, ∞ at VP
    # Cap at n_tiles_y * 2 to avoid overflow
    with np.errstate(divide='ignore', invalid='ignore'):
        tile_v = np.where(d > 0.001, (1.0 - d) / d * n_tiles_y, n_tiles_y * 10)

    # Fractional parts → grout detection
    frac_u = tile_u - np.floor(tile_u)
    frac_v = tile_v - np.floor(tile_v)

    on_grout = (frac_u < grout_f) | (frac_u > 1.0 - grout_f) | \
               (frac_v < grout_f) | (frac_v > 1.0 - grout_f)

    # ── lighting ─────────────────────────────────────────────────────────────
    orig_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    mb = float(np.mean(orig_gray[mask > 0])) if mask.any() else 0.5
    mb = max(mb, 0.01)
    light = np.clip(orig_gray / mb, 0.35, 1.9)   # (H,W)

    # ── colour assignment ─────────────────────────────────────────────────────
    # Expand to (H,W,3)
    tile_colour  = tile_bgr[np.newaxis, np.newaxis, :]   * np.ones((h_img, w_img, 1))
    grout_colour = grout_bgr[np.newaxis, np.newaxis, :] * np.ones((h_img, w_img, 1))

    colours = np.where(on_grout[:,:,np.newaxis], grout_colour, tile_colour)
    colours = colours * light[:,:,np.newaxis]
    colours = np.clip(colours, 0, 255).astype(np.uint8)

    # ── composite ────────────────────────────────────────────────────────────
    result = image.copy()
    floor_px = (mask > 0) & (d > 0.001) & (d <= 1.0 + grout_f)
    result[floor_px] = colours[floor_px]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/apply-tiles")
async def apply_tiles(
    image: UploadFile = File(...),
    mask: str  = Form(...),
    tile_size:   float = Form(30),
    tile_color:  str   = Form("#E8D1B5"),
    grout_color: str   = Form("#A9A9A9"),
    pattern:     str   = Form("grid")
):
    try:
        image_data = await image.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return JSONResponse({"error": "Could not decode image"}, status_code=400)

        try:
            floor_mask = (np.array(json.loads(mask)) > 0).astype(np.uint8)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid mask"}, status_code=400)

        if floor_mask.shape != img.shape[:2]:
            floor_mask = cv2.resize(floor_mask, (img.shape[1], img.shape[0]),
                                    interpolation=cv2.INTER_NEAREST)

        result = apply_perspective_tiles(
            img, floor_mask, tile_color, grout_color, tile_size, pattern)

        ok, buf = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            return JSONResponse({"error": "Encode failed"}, status_code=500)
        return Response(content=buf.tobytes(), media_type="image/jpeg")

    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"status":"healthy","device":"cpu",
            "cuda_available": torch.cuda.is_available()}

@app.get("/")
async def root():
    return {"message":"Floor Tile Visualizer API","status":"running"}


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