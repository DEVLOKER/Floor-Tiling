"""Smoke tests: the package imports and the app wires up its routes.

These don't load ML models (that happens in the FastAPI lifespan), so they run
fast and offline.
"""


def test_app_factory_builds_routes():
    from floor_tiling.app import app

    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert "/api/auto-detect" in paths
    assert "/api/apply-tiles" in paths
    assert "/api/apply-paint" in paths


def test_public_api_imports():
    from floor_tiling.processors import apply_perspective_tiles, apply_wall_paint
    from floor_tiling.core.planes import split_wall_planes
    from floor_tiling.ml import (
        get_mask2former_predictor,
        get_oneformer_predictor,
        get_depth_predictor,
    )

    assert all(
        callable(fn)
        for fn in (
            apply_perspective_tiles,
            apply_wall_paint,
            split_wall_planes,
            get_mask2former_predictor,
            get_oneformer_predictor,
            get_depth_predictor,
        )
    )


def test_model_paths_resolve():
    from floor_tiling.paths import MODELS_DIR, model_dir

    assert model_dir("mask2former", "MASK2FORMER_DIR") == MODELS_DIR / "mask2former"
