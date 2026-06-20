"""M-LSD line-segment detector (vendored).

Lightweight deep line detector used to estimate the room's dominant floor-grid
orientation (vanishing direction) for the depth tiling algorithm. Runs on CPU,
offline, on the project's pinned torch.

Model + decode utilities are vendored from the original M-LSD work
(NAVER, Apache-2.0) via controlnet_aux, so the app doesn't depend on
controlnet_aux at runtime (which pulls an unpinned torch).
"""
import logging

import numpy as np
import torch

from floor_tiling.paths import model_dir
from .model import MobileV2_MLSD_Large
from .utils import pred_lines

logger = logging.getLogger(__name__)

_WEIGHTS_NAME = "mlsd_large_512_fp32.pth"
_WEIGHTS_URL = (
    "https://huggingface.co/lllyasviel/Annotators/resolve/main/mlsd_large_512_fp32.pth"
)


class MLSDManager:
    """Manages the M-LSD model lifecycle and inference (singleton, CPU)."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_dir = model_dir("mlsd", "MLSD_DIR")
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            self.local_dir.mkdir(parents=True, exist_ok=True)
            weights = self.local_dir / _WEIGHTS_NAME
            if not weights.exists():
                logger.info("M-LSD weights not found in %s; downloading", self.local_dir)
                torch.hub.download_url_to_file(_WEIGHTS_URL, str(weights))
                logger.info("M-LSD downloaded to %s", weights)
            else:
                logger.info("Loading M-LSD from %s", weights)
            model = MobileV2_MLSD_Large()
            model.load_state_dict(torch.load(str(weights), map_location="cpu"), strict=True)
            model.eval()
            self._model = model
            logger.info("M-LSD ready (local weights)")
        except Exception as exc:
            logger.error("Failed to load M-LSD: %s", exc)
            raise

    def predict(self, image_np: np.ndarray, score_thr: float = 0.1, dist_thr: float = 0.1) -> np.ndarray:
        """Detect line segments. Returns an (N, 4) array of [x1, y1, x2, y2]."""
        with torch.no_grad():
            lines = pred_lines(image_np, self._model, [512, 512], score_thr, dist_thr)
        return np.asarray(lines, dtype=np.float64).reshape(-1, 4)


def get_mlsd_predictor() -> MLSDManager:
    """Get the singleton M-LSD predictor instance."""
    return MLSDManager()


__all__ = ["MLSDManager", "get_mlsd_predictor", "pred_lines"]
