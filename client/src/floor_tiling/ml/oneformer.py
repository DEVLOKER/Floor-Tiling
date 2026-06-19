"""OneFormer semantic segmentation (ADE20K, swin-large).

Used in an ensemble with Mask2Former: the two models miss different walls
(Mask2Former misses some tiled walls; OneFormer misses some plain walls), so
detection unions their wall/floor/ceiling masks for the best coverage.

Same offline-first lifecycle as the other models: weights download once into the
local ``models/`` dir (or an env-pointed volume), then load from disk.
"""
import numpy as np
import torch
from transformers import OneFormerProcessor, OneFormerForUniversalSegmentation

from floor_tiling.paths import model_dir


class OneFormerManager:
    """Manages the OneFormer model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    _model_id = "shi-labs/oneformer_ade20k_swin_large"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OneFormerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_path = model_dir("oneformer", "ONEFORMER_DIR")
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
                    print(f"OneFormer changed from {cached_id} -> {self._model_id}, re-downloading...")
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    print(f"OneFormer not found in {self.local_path}, downloading from Hugging Face...")
                self._processor = OneFormerProcessor.from_pretrained(self._model_id)
                self._model = OneFormerForUniversalSegmentation.from_pretrained(self._model_id)
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                marker_file.write_text(self._model_id)
                print(f"OneFormer downloaded and saved to {self.local_path}")
            else:
                print(f"Loading OneFormer ({self._model_id}) from local storage")
                self._processor = OneFormerProcessor.from_pretrained(str(self.local_path))
                self._model = OneFormerForUniversalSegmentation.from_pretrained(
                    str(self.local_path), use_safetensors=True
                )
                print("OneFormer loaded successfully (from local weights)")

            self._model.eval()
        except Exception as e:
            print(f"Error loading OneFormer: {e}")
            raise

    def predict(self, image_np: np.ndarray):
        """Semantic segmentation → (floor, wall, ceiling) binary masks.

        ADE20K IDs: 0 = wall, 3 = floor, 5 = ceiling.
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
        return floor, wall, ceiling


def get_oneformer_predictor() -> OneFormerManager:
    """Get singleton OneFormer predictor instance."""
    return OneFormerManager()


__all__ = ["OneFormerManager", "get_oneformer_predictor"]
