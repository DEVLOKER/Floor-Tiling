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
# Core renderer
# ─────────────────────────────────────────────────────────────────────────────

def apply_perspective_tiles(image: np.ndarray,
                            mask: np.ndarray,
                            tile_color: str,
                            grout_color: str,
                            tile_width_cm: float,       # real-world tile width
                            tile_height_cm: float,      # real-world tile height
                            grout_h_thickness: int,     # horizontal grout line thickness in px
                            grout_v_thickness: int,     # vertical grout line thickness in px
                            pattern: str) -> np.ndarray:
    """
    Inverse-homography tile renderer with fully configurable:
      - tile_width_cm  : real-world width of one tile  (X direction)
      - tile_height_cm : real-world height of one tile (Y / depth direction)
      - grout_h_thickness : pixel thickness of horizontal grout lines
      - grout_v_thickness : pixel thickness of vertical grout lines

    Grout lines are detected via tile-index edge detection (floor(u) and
    floor(v) change maps), then dilated independently for H and V lines
    using asymmetric kernels so thickness is controlled separately.
    """
    mask = (mask > 0).astype(np.uint8)

    tile_bgr  = np.array(hex_to_bgr(tile_color),  dtype=np.float32)
    grout_bgr = np.array(hex_to_bgr(grout_color), dtype=np.float32)

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

    # Tile counts using independent width / height
    n_tiles_x = max(2, int(round(real_width_cm / tile_width_cm)))
    n_tiles_y = max(2, int(round(real_depth_cm  / tile_height_cm)))

    print(f"🟡 tiles={n_tiles_x}×{n_tiles_y}  "
          f"tile={tile_width_cm}×{tile_height_cm}cm  "
          f"grout H={grout_h_thickness}px V={grout_v_thickness}px  "
          f"real={real_width_cm:.0f}×{real_depth_cm:.0f}cm")

    # ── Homography: flat floor plane → image ──────────────────────────────────
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

    # ── Project all pixels → tile-plane coords ────────────────────────────────
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

    # ── Tile index maps ────────────────────────────────────────────────────────
    tile_u = np.floor(u_all).astype(np.int32)
    tile_v = np.floor(v_all).astype(np.int32)

    # ── Separate edge maps for H and V grout lines ────────────────────────────
    # Horizontal grout lines = where tile_v changes between vertically adjacent pixels
    h_edges = np.zeros((h_img, w_img), dtype=np.uint8)
    h_edges[:-1, :] = (tile_v[:-1, :] != tile_v[1:, :]).astype(np.uint8)

    # Vertical grout lines = where tile_u changes between horizontally adjacent pixels
    v_edges = np.zeros((h_img, w_img), dtype=np.uint8)
    v_edges[:, :-1] = (tile_u[:, :-1] != tile_u[:, 1:]).astype(np.uint8)

    # Dilate each independently with asymmetric kernels
    # H lines: tall kernel  (thickness controls how many pixel rows the line spans)
    # V lines: wide kernel  (thickness controls how many pixel cols the line spans)
    grout_h_t = max(1, grout_h_thickness)
    grout_v_t = max(1, grout_v_thickness)

    kernel_h = np.ones((grout_h_t, 1), dtype=np.uint8)   # vertical dilation for H lines
    kernel_v = np.ones((1, grout_v_t), dtype=np.uint8)   # horizontal dilation for V lines

    h_grout_map = cv2.dilate(h_edges, kernel_h, iterations=1).astype(bool)
    v_grout_map = cv2.dilate(v_edges, kernel_v, iterations=1).astype(bool)

    grout_map = h_grout_map | v_grout_map

    # ── Lighting ──────────────────────────────────────────────────────────────
    orig_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    mb = float(np.mean(orig_gray[mask > 0])) if mask.any() else 0.5
    mb = max(mb, 0.01)
    light = np.clip(orig_gray / mb, 0.3, 2.0)

    # ── Colour map ────────────────────────────────────────────────────────────
    colour_img = np.where(
        grout_map[:, :, np.newaxis],
        grout_bgr[np.newaxis, np.newaxis, :],
        tile_bgr[np.newaxis, np.newaxis, :]
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
    image:               UploadFile = File(...),
    mask:                str        = Form(...),

    # Tile dimensions (real-world cm) — width and height independently
    tile_width:          float      = Form(30),   # cm, X direction
    tile_height:         float      = Form(30),   # cm, Y / depth direction

    # Legacy: tile_size sets both width & height if the new params aren't used
    tile_size:           float      = Form(None),

    # Colours
    tile_color:          str        = Form("#E8D1B5"),
    grout_color:         str        = Form("#FFFFFF"), # A9A9A9

    # Grout line thickness in pixels (horizontal and vertical independently)
    grout_h_thickness:   int        = Form(1),    # horizontal lines (px)
    grout_v_thickness:   int        = Form(1),    # vertical lines   (px)

    pattern:             str        = Form("grid")
):
    """
    Parameters
    ──────────
    tile_width          cm – real-world width  of one tile (left-right)
    tile_height         cm – real-world height of one tile (front-back depth)
    tile_size           cm – sets both width and height (legacy, overridden by above)
    tile_color          hex – tile face colour
    grout_color         hex – grout line colour
    grout_h_thickness   px – thickness of horizontal grout lines
    grout_v_thickness   px – thickness of vertical grout lines
    pattern             "grid" | "brick"
    """
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

        # Legacy tile_size overrides if both width/height are at default
        if tile_size is not None:
            tile_width  = tile_size
            tile_height = tile_size

        # Clamp to sensible ranges
        tile_width        = float(np.clip(tile_width,        5.0,  200.0))
        tile_height       = float(np.clip(tile_height,       5.0,  200.0))
        grout_h_thickness = int(np.clip(grout_h_thickness,   1,    20))
        grout_v_thickness = int(np.clip(grout_v_thickness,   1,    20))

        result = apply_perspective_tiles(
            img, floor_mask,
            tile_color, grout_color,
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