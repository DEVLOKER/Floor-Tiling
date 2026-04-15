# Floor Tiling Visualizer

An AI-powered floor-tile visualisation tool.  
Click on any floor surface in a photo, let SAM 2 segment it automatically, then preview different tile patterns, colours, grout widths, and textures — all in the browser.

---

## Features

- **One-click floor segmentation** using Meta's SAM 2 (Segment Anything Model 2)
- **Multiple tile patterns** – grid, brick offset, herringbone, chevron, checker, and more
- **Colour + texture support** – solid colours or real-texture images per tile
- **Dual-texture checker** – assign a different texture to light and dark tiles
- **Perspective-correct rendering** – homography warp so tiles follow the floor plane
- **Grout control** – set horizontal / vertical grout thickness independently
- **Fully browser-based UI** – no frontend build step required

---

## Project Structure

```
.
├── server.py               # FastAPI application & API routes
├── requirements.txt        # Python dependencies
├── config/
│   └── settings.py         # Model variant, device, tile constraints, JPEG quality
├── core/
│   └── helpers.py          # Shared utility functions
├── ml_models/
│   └── __init__.py         # SAM 2 model loader (singleton)
├── patterns/
│   └── __init__.py         # Tile pattern generators (grid, herringbone, etc.)
├── processors/
│   └── __init__.py         # Perspective-correct tile renderer
├── sam2/                   # Local copy of Meta's SAM 2 library
│   ├── configs/            # Hydra YAML configs for each model variant
│   ├── models/             # Model checkpoint files (.pt)
│   └── modeling/           # SAM 2 architecture source
└── static/
    ├── index.html          # Application shell
    ├── css/style.css       # Styles
    └── js/app.js           # Frontend logic
```

---

## Getting Started

There are two ways to run this application — choose the one that suits you best:

| Method | Best for | Effort |
|---|---|---|
| **[Option A — Docker](#docker)** (recommended) | Quick setup, no Python environment needed | Low — pull & run one command |
| **[Option B — Local install](#prerequisites)** | Development, customisation, GPU support | Higher — install Python deps manually |

> Jump directly to [Option A (Docker)](#docker) if you just want to try the app quickly.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or later |
| pip | 22+ |
| (Optional) CUDA GPU | For faster segmentation |

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd "Floor Tiling"
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install PyTorch

Choose the variant that matches your hardware.

**CPU only (works everywhere):**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**NVIDIA GPU — CUDA 12.1:**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> See https://pytorch.org/get-started/locally/ for other CUDA versions.

### 4. Install the remaining Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Download SAM 2.1 model checkpoints

Download the checkpoint(s) you need and place them in the `sam2/models/` folder.

| Variant | File | Download |
|---|---|---|
| Tiny *(default, fastest)* | `sam2.1_hiera_tiny.pt` | [Download](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt) |
| Small | `sam2.1_hiera_small.pt` | [Download](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt) |
| Base+ | `sam2.1_hiera_base_plus.pt` | [Download](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt) |
| Large *(most accurate, slowest)* | `sam2.1_hiera_large.pt` | [Download](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt) |

Using `curl` or `wget` from the project root:

```bash
# Tiny (recommended starting point — ~38 MB)
curl -L -o sam2/models/sam2.1_hiera_tiny.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt

# Small (~46 MB)
curl -L -o sam2/models/sam2.1_hiera_small.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt

# Base+ (~80 MB)
curl -L -o sam2/models/sam2.1_hiera_base_plus.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt

# Large (~224 MB)
curl -L -o sam2/models/sam2.1_hiera_large.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
```

After downloading, the folder should look like:

```
sam2/models/
├── sam2.1_hiera_tiny.pt
├── sam2.1_hiera_small.pt
├── sam2.1_hiera_base_plus.pt
└── sam2.1_hiera_large.pt
```

> You only need to download the variant(s) you intend to use (see step 6).

### 6. (Optional) Change the model variant or device

Open `config/settings.py` and edit `MODEL_CONFIG`:

```python
MODEL_CONFIG = {
    "variant": "tiny",   # tiny | small | base_plus | large
    "device": "cpu",     # cpu  | cuda
}
```

Smaller variants (`tiny`, `small`) load faster and use less memory.  
Use `"device": "cuda"` if you installed the CUDA build of PyTorch.

---

## Running the Server

```bash
python server.py
```

Or directly with uvicorn:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Then open your browser at **http://localhost:8000**.

---

## Docker

The pre-built image is available on DockerHub at [`berghout/ceramic`](https://hub.docker.com/r/berghout/ceramic).

### Pull the image

```bash
docker pull berghout/ceramic:latest
```

### Run the container

```bash
docker run -d \
  -p 8000:8000 \
  --name floor-tile-visualizer \
  berghout/ceramic:latest
```

### Or with Docker Compose (recommended)

```bash
docker compose up
```

### Open in browser

| Page | URL |
|---|---|
| Application UI | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| API info | http://localhost:8000/api |

### Stop and remove the container

```bash
docker stop floor-tile-visualizer
docker rm floor-tile-visualizer
```

---

## Usage

1. **Upload a photo** of a room with a visible floor.
2. **Click on the floor** in the canvas — SAM 2 will segment it.
3. Adjust **tile pattern, size, colour, and grout** settings in the right panel.
4. Optionally upload a **tile texture image** (JPEG/PNG) to replace the solid colour.
5. For checker patterns, upload a **second texture** for the dark tiles.
6. Click **Apply Tiles** to render the result.

> **Test assets included** — the `__tests__/` folder contains sample images you can use right away:
>
> | Folder | Contents |
> |---|---|
> | `__tests__/rooms/` | Sample room photos (various empty room scenes) |
> | `__tests__/rooms/large/` | Higher-resolution room photos |
> | `__tests__/textures/` | Sample tile texture images (JPEG) |
>
> Simply upload any image from `__tests__/rooms/` as your room photo, and optionally use one from `__tests__/textures/` as a tile texture.

---

## API Reference

All endpoints are served under the `/api` prefix.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves the web UI |
| `GET` | `/api` | Returns API info JSON |
| `GET` | `/health` | Health check |
| `POST` | `/api/segment-floor` | Segment the floor from an uploaded image + click coordinates |
| `POST` | `/api/apply-tiles` | Render tiles onto a previously segmented floor mask |

### POST `/api/segment-floor`

| Field | Type | Description |
|---|---|---|
| `image` | file | JPEG/PNG room photo |
| `x` | float (form) | Click X coordinate (0–1 normalised) |
| `y` | float (form) | Click Y coordinate (0–1 normalised) |

Returns `{ mask, confidence, image_width, image_height }`.

### POST `/api/apply-tiles`

| Field | Type | Description |
|---|---|---|
| `image` | file | Original room photo |
| `mask` | file | Binary mask blob (uint8 flat array) |
| `pattern` | string (form) | Tile pattern name |
| `tile_color` | string (form) | Primary colour (hex) |
| `tile_color2` | string (form) | Secondary colour (hex, checker only) |
| `grout_color` | string (form) | Grout colour (hex) |
| `tile_width_cm` | float (form) | Tile width in cm |
| `tile_height_cm` | float (form) | Tile height in cm |
| `grout_thickness` | int (form) | Grout thickness in px (both directions) |
| `tile_texture` | file (optional) | Texture image for primary tile |
| `tile_texture2` | file (optional) | Texture image for secondary tile (checker) |

Returns the composited room image as JPEG.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed description of the processing pipeline.

---

## License

This project is for personal / educational use.  
SAM 2 is released by Meta under the Apache 2.0 license — see `sam2/` for details.
