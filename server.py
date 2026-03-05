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

# Force CPU mode
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",  # VS Code Live Server
        "http://localhost:5500",   # Alternative localhost
        "http://127.0.0.1:8000",   # FastAPI server itself
        "http://localhost:8000",    # Alternative FastAPI
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🟡 Loading SAM2 model on CPU (this may take 1-2 minutes)...")

# Load SAM 2 model - just specify the variant: tiny, small, base_plus, or large
model_variant = "tiny"  # Change to "small", "base_plus", or "large" as needed

try:
    model = build_sam2(model_variant, device="cpu")
    predictor = SAM2ImagePredictor(model)
    print("✅ Model loaded successfully on CPU")
except Exception as e:
    print(f"❌ Error loading model: {e}")
    raise


@app.post("/segment-floor")
async def segment_floor(
    image: UploadFile = File(...),
    click_x: float = Form(...),
    click_y: float = Form(...)
):
    """
    Get floor mask from user click
    """
    try:
        print(f"🟡 Received floor click at ({click_x}, {click_y})")
        
        # Read image
        image_data = await image.read()
        pil_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        image_np = np.array(pil_image)
        
        # Set image in predictor
        predictor.set_image(image_np)
        
        # User's click point
        input_point = np.array([[click_x, click_y]], dtype=np.float32)
        input_label = np.array([1], dtype=np.int32)
        
        # Run inference
        with torch.inference_mode():
            masks, scores, logits = predictor.predict(
                point_coords=input_point,
                point_labels=input_label,
                multimask_output=True
            )
        
        # Return best mask
        best_mask_idx = int(np.argmax(scores))
        best_mask = masks[best_mask_idx]
        
        # Convert to numpy if needed
        if hasattr(best_mask, 'cpu'):
            best_mask = best_mask.cpu().numpy()
        elif not isinstance(best_mask, np.ndarray):
            best_mask = np.array(best_mask)
        
        # Clean mask
        best_mask = np.where(np.isnan(best_mask), 0, best_mask)
        floor_mask = best_mask.astype(float).tolist()
        
        return JSONResponse({
            "mask": floor_mask,
            "score": float(scores[best_mask_idx]),
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)




def apply_perspective_tiles(image, mask, tile_color, grout_color, tile_size_cm, pattern):
    """
    Apply tiles to floor with realistic perspective and scaling
    """
    # Ensure mask is binary
    mask = (mask > 0).astype(np.uint8)
    
    # Find floor contour
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("⚠️ No contours found in mask")
        return image
    
    floor_contour = max(contours, key=cv2.contourArea)
    
    # Get the four corners of the floor with perspective
    corners = get_floor_corners_with_perspective(floor_contour)
    
    if corners is None:
        print("⚠️ Could not determine floor corners")
        return image
    
    near_left, near_right, far_left, far_right = corners
    
    # Calculate dimensions
    near_width_px = np.linalg.norm(near_right - near_left)
    depth_px = np.linalg.norm(far_left - near_left)
    
    # Estimate real dimensions (can be adjusted)
    estimated_width_cm = 400  # 4 meters
    estimated_depth_cm = 500  # 5 meters
    
    # Calculate number of tiles
    tiles_across = max(5, int(estimated_width_cm / tile_size_cm) + 1)
    tiles_down = max(5, int(estimated_depth_cm / tile_size_cm) + 1)
    
    print(f"🟡 Creating grid: {tiles_across}×{tiles_down} tiles")
    
    # Create perspective grid
    grid_points = create_perspective_grid(
        near_left, near_right, far_left, far_right,
        tiles_across, tiles_down
    )
    
    # Create result image
    result = image.copy()
    
    # Draw each tile
    for i in range(tiles_across):
        for j in range(tiles_down):
            # Get the four corners of this tile
            tile_corners = np.array([
                grid_points[j][i],      # top-left
                grid_points[j][i+1],    # top-right
                grid_points[j+1][i+1],  # bottom-right
                grid_points[j+1][i]      # bottom-left
            ], dtype=np.int32)
            
            # Check if tile is within mask (optional - speeds up rendering)
            center = np.mean(tile_corners, axis=0).astype(int)
            if 0 <= center[0] < mask.shape[1] and 0 <= center[1] < mask.shape[0]:
                if mask[center[1], center[0]] > 0:
                    draw_perspective_tile(result, tile_corners, tile_color, grout_color)
    
    # Transfer lighting for realism
    result = transfer_lighting(image, result, mask)
    
    return result

def get_floor_corners_with_perspective(contour):
    """
    Identify the four corners of the floor with perspective in mind
    """
    # Simplify contour
    epsilon = 0.02 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    
    points = approx.reshape(-1, 2)
    
    if len(points) < 4:
        return None
    
    # Sort by y-coordinate (top to bottom)
    sorted_by_y = points[np.argsort(points[:, 1])]
    
    # Take top 2 as far points, bottom 2 as near points
    far_points = sorted_by_y[:2]
    near_points = sorted_by_y[-2:]
    
    # Sort far points by x
    far_left = far_points[np.argmin(far_points[:, 0])]
    far_right = far_points[np.argmax(far_points[:, 0])]
    
    # Sort near points by x
    near_left = near_points[np.argmin(near_points[:, 0])]
    near_right = near_points[np.argmax(near_points[:, 0])]
    
    return np.array([near_left, near_right, far_left, far_right], dtype=np.float32)

def create_perspective_grid(near_left, near_right, far_left, far_right, tiles_across, tiles_down):
    """
    Create a grid that follows perspective - tiles get smaller toward the back
    """
    grid = []
    
    for j in range(tiles_down + 1):
        # Progress from near (0) to far (1)
        t = j / tiles_down
        
        # Use perspective interpolation (tiles get smaller faster in the distance)
        # This creates a realistic perspective effect
        perspective_t = t / (1.0 + 0.3 * t)  # Adjust 0.3 for more/less perspective
        
        # Interpolate left edge
        left_x = near_left[0] * (1 - perspective_t) + far_left[0] * perspective_t
        left_y = near_left[1] * (1 - perspective_t) + far_left[1] * perspective_t
        
        # Interpolate right edge
        right_x = near_right[0] * (1 - perspective_t) + far_right[0] * perspective_t
        right_y = near_right[1] * (1 - perspective_t) + far_right[1] * perspective_t
        
        row = []
        for i in range(tiles_across + 1):
            # Interpolate horizontally
            s = i / tiles_across
            x = left_x * (1 - s) + right_x * s
            y = left_y * (1 - s) + right_y * s
            row.append([x, y])
        
        grid.append(np.array(row))
    
    return grid

def hex_to_rgb(hex_color):
    """
    Convert hex color string (e.g., "#E8D1B5") to RGB tuple (r, g, b)
    """
    # Remove '#' if present
    hex_color = hex_color.lstrip('#')
    
    # Convert hex to RGB
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b)
    except (ValueError, IndexError):
        # Return default gray if conversion fails
        print(f"⚠️ Invalid hex color: {hex_color}, using default")
        return (128, 128, 128)

def draw_perspective_tile(image, corners, tile_color, grout_color):
    """
    Draw a single tile with perspective
    """
    # Parse colors
    if isinstance(tile_color, str):
        tile_color = hex_to_rgb(tile_color)
    if isinstance(grout_color, str):
        grout_color = hex_to_rgb(grout_color)
    
    # Ensure corners are integer coordinates
    corners = corners.astype(np.int32)
    
    # Check if tile is within image bounds (optional optimization)
    # Get bounding box of tile
    x, y, w, h = cv2.boundingRect(corners)
    
    # Only draw if tile intersects with image
    if x < image.shape[1] and y < image.shape[0] and x + w > 0 and y + h > 0:
        # Fill the tile
        cv2.fillPoly(image, [corners], tile_color)
        
        # Draw grout lines (edges)
        cv2.polylines(image, [corners], True, grout_color, 2)

def transfer_lighting(original, tiled, mask):
    """
    Transfer lighting from original floor to make tiles look realistic
    """
    # Convert to float
    original_float = original.astype(np.float32) / 255.0
    tiled_float = tiled.astype(np.float32) / 255.0
    
    # Get grayscale of original
    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    
    # Create lighting map (only where mask is 1)
    mask_float = mask.astype(np.float32)
    lighting_map = np.ones_like(gray)
    
    if np.any(mask):
        # Calculate lighting based on original image brightness
        mean_brightness = np.mean(gray[mask > 0])
        lighting_map = gray / (mean_brightness + 1e-6)
        lighting_map = np.clip(lighting_map, 0.7, 1.3)
    
    # Apply to each channel
    for c in range(3):
        tiled_float[:,:,c] = tiled_float[:,:,c] * lighting_map
    
    tiled_float = np.clip(tiled_float, 0, 1)
    
    # Blend with original outside mask
    result = original_float.copy()
    mask_3ch = np.stack([mask, mask, mask], axis=2)
    result[mask_3ch > 0] = tiled_float[mask_3ch > 0]
    
    return (result * 255).astype(np.uint8)

@app.post("/apply-tiles")
async def apply_tiles(
    image: UploadFile = File(...),
    mask: str = Form(...),
    tile_size: float = Form(30),
    tile_color: str = Form("#E8D1B5"),
    grout_color: str = Form("#A9A9A9"),
    pattern: str = Form("grid")
):
    """
    Apply tiles to floor with realistic perspective and lighting
    """
    try:
        # Load image
        image_data = await image.read()
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return JSONResponse({"error": "Could not decode image"}, status_code=400)
        
        # Parse mask
        try:
            floor_mask = np.array(json.loads(mask))
            floor_mask = (floor_mask > 0).astype(np.uint8)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid mask format"}, status_code=400)
        
        # Ensure mask matches image dimensions
        if floor_mask.shape != img.shape[:2]:
            floor_mask = cv2.resize(floor_mask.astype(np.uint8), 
                                   (img.shape[1], img.shape[0]), 
                                   interpolation=cv2.INTER_NEAREST)
        
        print(f"🟡 Applying tiles: {tile_size}cm, {pattern}")
        
        # Apply tiles with perspective
        result = apply_perspective_tiles(
            img, floor_mask, tile_color, grout_color, tile_size, pattern
        )
        
        # Encode result
        success, buffer = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        if not success:
            return JSONResponse({"error": "Could not encode result"}, status_code=500)
        
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
        
    except Exception as e:
        print(f"❌ Tile error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "device": "cpu",
        "cuda_available": torch.cuda.is_available(),
    }

@app.get("/")
async def root():
    return {"message": "Floor Tile Visualizer API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    import uvicorn
    # For hot reload, run from command line instead:
    # python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        log_level="info"
    )