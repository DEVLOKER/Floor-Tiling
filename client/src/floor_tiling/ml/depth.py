"""Monocular metric-depth estimation (Depth Anything V2, indoor).

Used to recover per-pixel surface normals so a single semantic "wall" blob can
be split into its individual planes (left / back / right walls, etc.).

Follows the same offline-first lifecycle as the segmenter: the weights are
downloaded once into this package's local ``models/`` directory and then loaded
from disk on every subsequent run.
"""
import logging

import numpy as np
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from floor_tiling.paths import model_dir
from floor_tiling.config.settings import DEPTH_VARIANT

logger = logging.getLogger(__name__)

# Metric-indoor Depth-Anything-V2 sizes (bigger = more accurate normals, slower).
_VARIANTS = {
    "small": "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
    "base": "depth-anything/Depth-Anything-V2-Metric-Indoor-Base-hf",
    "large": "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
}


class DepthManager:
    """Manages the depth model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    # Metric indoor variant — trained on interior scenes, so planes stay flat in
    # the back-projected point cloud. Size chosen in settings (DEPTH_VARIANT).
    _model_id = _VARIANTS.get(DEPTH_VARIANT, _VARIANTS["base"])

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DepthManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Weight cache: DEPTH_DIR env override (e.g. a mounted volume) falling
        # back to the shared models dir (see floor_tiling.paths).
        self.local_path = model_dir("depth", "DEPTH_DIR")
        if self._model is None:
            self._load_model()

    def _load_model(self):
        """Load model from local storage or download it once if missing."""
        try:
            self.local_path.mkdir(parents=True, exist_ok=True)

            config_file = self.local_path / "config.json"
            has_weights = (self.local_path / "model.safetensors").exists() or (
                self.local_path / "pytorch_model.bin"
            ).exists()
            marker_file = self.local_path / ".model_id"
            cached_id = marker_file.read_text().strip() if marker_file.exists() else None
            model_mismatch = cached_id != self._model_id

            if not config_file.exists() or not has_weights or model_mismatch:
                if model_mismatch and has_weights:
                    logger.info("Depth Anything V2 model changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("Depth Anything V2 weights not found in %s; downloading from Hugging Face", self.local_path)

                self._processor = AutoImageProcessor.from_pretrained(self._model_id, use_fast=True)
                self._model = AutoModelForDepthEstimation.from_pretrained(self._model_id)
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                marker_file.write_text(self._model_id)
                logger.info("Depth Anything V2 downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading Depth Anything V2 (%s) from %s", self._model_id, self.local_path)
                self._processor = AutoImageProcessor.from_pretrained(str(self.local_path), use_fast=True)
                self._model = AutoModelForDepthEstimation.from_pretrained(
                    str(self.local_path), use_safetensors=True
                )

            self._model.eval()
            logger.info("Depth Anything V2 ready (local weights)")
        except Exception as e:
            logger.error("Failed to load Depth Anything V2: %s", e)
            raise

    def predict(self, image_np: np.ndarray) -> np.ndarray:
        """Estimate metric depth.

        Args:
            image_np: RGB image as numpy array [H, W, 3]

        Returns:
            depth: float32 array [H, W] (metres; larger = farther).
        """
        inputs = self._processor(images=image_np, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)

        post = self._processor.post_process_depth_estimation(
            outputs, target_sizes=[image_np.shape[:2]]
        )
        depth = post[0]["predicted_depth"]
        return depth.cpu().numpy().astype(np.float32)


def get_depth_predictor() -> DepthManager:
    """Get singleton depth predictor instance."""
    return DepthManager()


__all__ = ["DepthManager", "get_depth_predictor"]
