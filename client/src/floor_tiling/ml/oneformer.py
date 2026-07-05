"""OneFormer semantic segmentation (ADE20K, swin-large).

Used in an ensemble with Mask2Former: the two models miss different walls
(Mask2Former misses some tiled walls; OneFormer misses some plain walls), so
detection unions their wall/floor/ceiling masks for the best coverage.

Same offline-first lifecycle as the other models: weights download once into the
local ``models/`` dir (or an env-pointed volume), then load from disk.
"""
import logging

import numpy as np
import torch
from transformers import OneFormerProcessor, OneFormerForUniversalSegmentation

from floor_tiling.paths import model_dir
from floor_tiling.ml.labels import object_class_ids, opening_class_ids
from floor_tiling.config.settings import ONEFORMER_VARIANT

logger = logging.getLogger(__name__)

# ADE20K OneFormer variants (tiny is ~3-4× faster than large; dinat needs the
# `natten` package installed).
_VARIANTS = {
    "tiny": "shi-labs/oneformer_ade20k_swin_tiny",
    "large": "shi-labs/oneformer_ade20k_swin_large",
    "dinat_large": "shi-labs/oneformer_ade20k_dinat_large",
}


class OneFormerManager:
    """Manages the OneFormer model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    _object_ids = None   # cached ADE20K ids of wall fixtures/decor to exclude
    _opening_ids = None  # cached ADE20K ids of doors & windows
    # Size variant chosen in settings (ONEFORMER_VARIANT); tiny is much faster.
    # Re-downloads automatically when the id changes (manager cleans old weights).
    _model_id = _VARIANTS.get(ONEFORMER_VARIANT, _VARIANTS["tiny"])

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OneFormerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_path = model_dir("oneformer", "ONEFORMER_DIR", ONEFORMER_VARIANT, self._model_id)
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            self.local_path.mkdir(parents=True, exist_ok=True)
            config_file = self.local_path / "config.json"
            has_weights = (self.local_path / "model.safetensors").exists() or (
                self.local_path / "pytorch_model.bin"
            ).exists()
            marker_file = self.local_path / ".model_id"
            cached_id = marker_file.read_text().strip() if marker_file.exists() else None
            mismatch = cached_id != self._model_id

            if not config_file.exists() or not has_weights or mismatch:
                if mismatch and has_weights:
                    logger.info("OneFormer model changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("OneFormer weights not found in %s; downloading from Hugging Face", self.local_path)
                self._processor = OneFormerProcessor.from_pretrained(self._model_id)
                self._model = OneFormerForUniversalSegmentation.from_pretrained(self._model_id)
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                marker_file.write_text(self._model_id)
                logger.info("OneFormer downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading OneFormer (%s) from %s", self._model_id, self.local_path)
                self._processor = OneFormerProcessor.from_pretrained(str(self.local_path))
                self._model = OneFormerForUniversalSegmentation.from_pretrained(
                    str(self.local_path), use_safetensors=True
                )

            self._model.eval()
            logger.info("OneFormer ready (local weights)")
        except Exception as e:
            logger.error("Failed to load OneFormer: %s", e)
            raise

    def predict(self, image_np: np.ndarray):
        """Semantic segmentation → (floor, wall, ceiling, objects, openings).

        ADE20K IDs: 0 = wall, 3 = floor, 5 = ceiling. ``objects`` are wall
        fixtures/decor (lamp/radiator/tv/…) and ``openings`` are doors & windows
        — two separate paint-exclusion categories.
        """
        inputs = self._processor(images=image_np, task_inputs=["semantic"], return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)
        seg = self._processor.post_process_semantic_segmentation(
            outputs, target_sizes=[image_np.shape[:2]]
        )[0].cpu().numpy()
        wall = (seg == 0).astype(np.uint8)
        floor = (seg == 3).astype(np.uint8)
        ceiling = (seg == 5).astype(np.uint8)
        if self._object_ids is None:
            self._object_ids = object_class_ids(self._model.config.id2label)
            self._opening_ids = opening_class_ids(self._model.config.id2label)
        objects = (
            np.isin(seg, list(self._object_ids)).astype(np.uint8)
            if self._object_ids else np.zeros_like(wall)
        )
        openings = (
            np.isin(seg, list(self._opening_ids)).astype(np.uint8)
            if self._opening_ids else np.zeros_like(wall)
        )
        return floor, wall, ceiling, objects, openings


def get_oneformer_predictor() -> OneFormerManager:
    """Get singleton OneFormer predictor instance."""
    return OneFormerManager()


__all__ = ["OneFormerManager", "get_oneformer_predictor"]
