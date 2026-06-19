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

```powershell
scripts\install_deps.ps1          # venv + pip (use -Gpu for CUDA torch)
pip install -e .                  # editable install (or set PYTHONPATH=src)
python -m floor_tiling            # http://localhost:8000  (hot-reload)
```

## Models & weights

Each wrapper in `ml/` is an offline-first singleton: weights download once into
`models/<name>/` and load from disk thereafter. Override the cache location with
`MODELS_DIR`, or per model with `MASK2FORMER_DIR` / `ONEFORMER_DIR` / `DEPTH_DIR`
(used by the Docker volume deployment).

## Build

```powershell
scripts\build_exe.ps1             # Windows EXE  → dist/floor-tiling/
scripts\build_docker.ps1          # Docker image (download | local | volume)
```

Docker / EXE compile the proprietary subpackages (`config, core, ml, patterns,
processors, licensing`) to native extensions; `app.py`, `__main__.py` and the
`api` routing layer stay as plain Python.
