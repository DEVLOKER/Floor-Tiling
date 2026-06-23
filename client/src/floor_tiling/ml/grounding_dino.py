"""Grounding DINO — open-vocabulary object detection.

ADE20K segmentation only knows ~150 fixed classes, so wall objects it lacks
(air conditioner, pipe, socket, thermostat, vent…) get merged into the wall and
painted over.  Grounding DINO detects *any* object named in a free-text prompt,
so we can catch everything that must be excluded from painting.  Its boxes are
then turned into pixel-perfect masks by SAM (see :mod:`floor_tiling.ml.sam`).

Offline-first: weights download once into the local ``models/`` dir, then load
from disk (mirrors the Mask2Former manager).
"""
import logging

import numpy as np
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

from floor_tiling.paths import model_dir
from floor_tiling.config.settings import GROUNDING_DINO_VARIANT

logger = logging.getLogger(__name__)

_VARIANTS = {
    "tiny": "IDEA-Research/grounding-dino-tiny",
    "base": "IDEA-Research/grounding-dino-base",
}


class GroundingDINOManager:
    """Manages the Grounding DINO model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    # Size variant chosen in settings (GROUNDING_DINO_VARIANT). Tiny is fastest.
    _model_id = _VARIANTS.get(GROUNDING_DINO_VARIANT, _VARIANTS["tiny"])

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_path = model_dir("grounding_dino", "GROUNDING_DINO_DIR")
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            self.local_path.mkdir(parents=True, exist_ok=True)
            config_file = self.local_path / "config.json"
            has_weights = (
                (self.local_path / "model.safetensors").exists()
                or (self.local_path / "pytorch_model.bin").exists()
            )
            marker = self.local_path / ".model_id"
            cached_id = marker.read_text().strip() if marker.exists() else None
            mismatch = cached_id != self._model_id

            if not config_file.exists() or not has_weights or mismatch:
                if mismatch and has_weights:
                    logger.info("Grounding DINO changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("Grounding DINO weights not found in %s; downloading", self.local_path)
                self._processor = AutoProcessor.from_pretrained(self._model_id)
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self._model_id)
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                marker.write_text(self._model_id)
                logger.info("Grounding DINO downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading Grounding DINO from %s", self.local_path)
                self._processor = AutoProcessor.from_pretrained(str(self.local_path))
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(str(self.local_path))

            self._model.eval()
            logger.info("Grounding DINO ready (local weights)")
        except Exception as e:
            logger.error("Failed to load Grounding DINO: %s", e)
            raise

    def detect(
        self,
        image_np: np.ndarray,
        prompt: str,
        box_threshold: float = 0.3,
        text_threshold: float = 0.25,
    ) -> np.ndarray:
        """Detect objects named in ``prompt`` and return their boxes.

        Args:
            image_np: RGB image [H, W, 3].
            prompt:   Lower-case, period-separated phrases, e.g.
                      ``"air conditioner. radiator. socket."``.
        Returns:
            Float array of boxes ``[N, 4]`` in xyxy pixel coords (empty if none).
        """
        pil = Image.fromarray(image_np)
        inputs = self._processor(images=pil, text=prompt, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)
        results = self._processor.post_process_grounded_object_detection(
            outputs,
            inputs["input_ids"],
            threshold=box_threshold,
            text_threshold=text_threshold,
            target_sizes=[image_np.shape[:2]],
        )[0]
        boxes = results["boxes"].cpu().numpy() if len(results["boxes"]) else np.zeros((0, 4))
        return boxes.astype(np.float32)


def get_grounding_dino_predictor() -> GroundingDINOManager:
    """Get singleton Grounding DINO predictor instance."""
    return GroundingDINOManager()


__all__ = ["GroundingDINOManager", "get_grounding_dino_predictor"]
