# Floor Tiling Visualizer — client

FastAPI service that auto-detects room surfaces (floor / walls / ceiling) and
renders perspective-correct **floor tiling** and **wall/ceiling paint** previews.

## Layout

```
client/
├── pyproject.toml            # packaging, deps, ruff/black config
├── setup_cython.py           # compile proprietary modules → native .pyd/.so
├── floor_tiling.spec         # PyInstaller (Windows EXE) build
├── requirements.txt          # pip install (carries the torch CPU index)
├── models/                   # ML weight cache (gitignored; downloaded once)
│   ├── mask2former/  oneformer/  depth/
├── scripts/                  # build / launch / docker helpers
├── tests/
└── src/floor_tiling/         # the importable package
    ├── app.py                # FastAPI application factory (`app`)
    ├── __main__.py           # `python -m floor_tiling` entry point
    ├── paths.py              # project root + model-cache resolution
    ├── api/                  # routing layer (dependencies, routes/*)
    ├── config/               # settings + secrets
    ├── core/                 # geometry, mask refinement, depth planes
    ├── ml/                   # model wrappers: mask2former, oneformer, depth
    ├── patterns/             # tile pattern generators
    ├── processors/           # tile_renderer, wall_painter
    ├── licensing/            # device-bound license verification
    └── static/               # frontend (served by the app)
```

Imports are namespaced, e.g. `from floor_tiling.core.planes import floor_plane_uv`.

## Develop

`requirements.txt` is the single source of truth for runtime dependencies (it
also carries the PyTorch CPU `--extra-index-url`). `pyproject.toml` packages the
code only — it declares no deps — so install in this order:

```powershell
scripts\install_deps.ps1          # venv + pip install -r requirements.txt (-Gpu for CUDA)
pip install -e . --no-deps        # the floor_tiling package only
python -m floor_tiling            # http://localhost:8000  (hot-reload)
```

(Or skip the editable install and just `$env:PYTHONPATH = "src"; python -m floor_tiling`.)

## Models & weights

Each wrapper in `ml/` is an offline-first singleton: weights download once into
`models/<name>/` and load from disk thereafter. Override the cache location with
`MODELS_DIR`, or per model with `MASK2FORMER_DIR` / `ONEFORMER_DIR` / `DEPTH_DIR`
(used by the Docker volume deployment).

## Build

```powershell
scripts\build_exe.ps1             # Windows EXE  → dist/floor-tiling/
```

**Docker — customer (offline, weights baked):**
```bash
docker compose build              # needs weights in client/models/<name>/
docker compose up                 # runs fully offline
docker save floortiling:latest | gzip > app.tar.gz   # deliver
```

**Docker — dev (downloads weights once into a cache volume):**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Docker / EXE compile the proprietary subpackages (`config, core, ml, patterns,
processors, licensing`) **and the `shared` package** to native extensions;
`app.py`, `__main__.py` and the `api` routing layer stay as plain Python.
