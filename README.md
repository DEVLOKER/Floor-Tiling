# Floor Tiling Visualizer

An AI-powered room re-finishing visualiser.  
Upload a room photo, let the AI auto-detect the floor, walls and ceiling, then preview tile patterns on the floor and paint (colour **or** texture) on the walls/ceiling — all in the browser.

---

## Features

- **Automatic surface detection** – floor, individual wall planes, and ceiling, using Mask2Former (semantic segmentation) + Depth Anything V2 (depth → per-wall plane separation)
- **Multiple tile patterns** – grid, brick offset, herringbone, chevron, checker, and more
- **Wall & ceiling painting** – solid colour or perspective-mapped texture, with the room's real lighting preserved
- **Colour + texture support** – solid colours or real-texture images per tile
- **Dual-texture checker** – assign a different texture to light and dark tiles
- **Perspective-correct rendering** – homography warp so tiles follow the floor plane
- **Grout control** – set horizontal / vertical grout thickness independently
- **Fully browser-based UI** – no frontend build step required

---

## Project Structure

```
.
├── server.py               # FastAPI entry-point (imports app.py)
├── app.py                  # FastAPI application & lifespan (loads models)
├── requirements.txt        # Python dependencies
├── config/
│   └── settings.py         # Tile/paint constraints, JPEG quality, etc.
├── core/
│   ├── geometry.py         # Vanishing-point floor-quad estimation
│   ├── planes.py           # Depth-normal wall-plane separation
│   └── masks.py            # Edge-aware mask refinement
├── mask2former/
│   ├── mask2former.py      # Segmentation model loader (floor/walls/ceiling)
│   └── models/             # Auto-downloaded weights (config + safetensors)
├── depth/
│   ├── depth.py            # Depth model loader (Depth Anything V2)
│   └── models/             # Auto-downloaded weights (config + safetensors)
├── patterns/
│   └── patterns.py         # Tile pattern generators (grid, herringbone, etc.)
├── processors/
│   ├── tile_renderer.py    # Perspective-correct tile renderer
│   └── wall_painter.py     # Wall/ceiling colour + texture painter
└── static/
    ├── index.html          # Application shell
    ├── css/                # Styles
    └── js/modules/         # Frontend logic
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

### 5. Models (downloaded automatically on first run)

No manual download is needed. On first start the app fetches and caches both
models into their local `models/` folders, then loads them offline thereafter:

| Purpose | Model | Cached to |
|---|---|---|
| Segmentation (floor / walls / ceiling) | `facebook/mask2former-swin-large-ade-semantic` (~866 MB) | `mask2former/models/` |
| Depth (per-wall plane separation) | `depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf` (~390 MB) | `depth/models/` |

> First start needs internet and takes a while (downloads ~1.25 GB). For an
> air-gapped install, pre-seed those two `models/` folders with the weights
> (or build the Docker image with `MODEL_SOURCE=download`/`local`).

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

1. **Upload a photo** of a room — the floor, walls and ceiling are detected automatically.
2. Use the **Carrelage du sol** tab: the floor is pre-selected; pick a pattern, size, colour/texture and grout, then **Appliquer le carrelage**.
3. Use the **Peinture murs & plafond** tab: click one or more walls (or the ceiling) on the image, choose a colour or texture, then **Appliquer la peinture**.
4. Floor tiles and wall/ceiling paint **compound** into one result, which you can download.

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
| `POST` | `/api/auto-detect` | Auto-detect floor / walls / ceiling (streams progress via SSE) |
| `POST` | `/api/apply-tiles` | Render tiles onto the selected floor mask |
| `POST` | `/api/apply-paint` | Paint (colour or texture) onto the selected wall/ceiling mask |

### POST `/api/auto-detect`

| Field | Type | Description |
|---|---|---|
| `image` | file | JPEG/PNG room photo |

Streams Server-Sent Events with step progress, then a final `done` event whose
payload is a gzipped binary blob containing the surface labels (floor + wall
planes + ceiling centroids) and the floor / labeled-wall / ceiling masks.

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
| `source` | file (optional) | Pristine original (lighting source) for idempotent re-apply |

Returns the composited room image as JPEG.

### POST `/api/apply-paint`

| Field | Type | Description |
|---|---|---|
| `image` | file | Image to paint onto (the accumulated composite) |
| `mask` | file | Labeled wall/ceiling mask blob (one id per plane) |
| `paint_color` | string (form) | Paint colour (hex) |
| `finish` | string (form) | `matte` \| `satin` \| `gloss` |
| `paint_texture` | file (optional) | Texture image (perspective-mapped per plane) |
| `texture_scale` | float (form, optional) | Real-world texture repeat size in metres |
| `source` | file (optional) | Pristine original (lighting source) for idempotent re-apply |

Returns the composited room image as JPEG.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed description of the processing pipeline.

---

## License

This project is for personal / educational use.  
Models used: **Mask2Former** (facebook/mask2former-swin-large-ade-semantic) and
**Depth Anything V2** (depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf),
each under its respective Hugging Face model license.
