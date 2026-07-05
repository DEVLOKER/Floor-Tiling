"""SAM (Segment Anything) — box-prompted, pixel-perfect object masks.

Grounding DINO gives boxes for wall objects; SAM turns each box into a precise
mask so painting is excluded exactly at the object's silhouette (no halo ring
from dilating a coarse box).  We use SlimSAM — a pruned SAM (~38 MB) that loads
through the stock ``transformers`` ``SamModel`` and runs in ~1-2 s on CPU, the
lightweight equivalent of MobileSAM without an extra dependency/encoder.

Offline-first: weights download once into the local ``models/`` dir.
"""
import logging

import numpy as np
from PIL import Image
import torch
from transformers import SamModel, SamProcessor

from floor_tiling.paths import model_dir
from floor_tiling.config.settings import SAM_VARIANT

logger = logging.getLogger(__name__)

# SlimSAM (pruned, tiny, CPU-friendly) vs full facebook SAM (sharper, slower).
# All load through the same transformers SamModel/SamProcessor.
_VARIANTS = {
    "slim50": "Zigeng/SlimSAM-uniform-50",
    "slim77": "Zigeng/SlimSAM-uniform-77",
    "base": "facebook/sam-vit-base",
    "large": "facebook/sam-vit-large",
    "huge": "facebook/sam-vit-huge",
}


class SamManager:
    """Manages the SAM model lifecycle and box-prompted inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    # Size variant chosen in settings (SAM_VARIANT); SlimSAM is tiny/fast.
    _model_id = _VARIANTS.get(SAM_VARIANT, _VARIANTS["slim77"])

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_path = model_dir("sam", "SAM_DIR", SAM_VARIANT, self._model_id)
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
                    logger.info("SAM changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("SAM weights not found in %s; downloading", self.local_path)
                self._processor = SamProcessor.from_pretrained(self._model_id)
                self._model = SamModel.from_pretrained(self._model_id)
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                marker.write_text(self._model_id)
                logger.info("SAM downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading SAM from %s", self.local_path)
                self._processor = SamProcessor.from_pretrained(str(self.local_path))
                self._model = SamModel.from_pretrained(str(self.local_path))

            self._model.eval()
            logger.info("SAM ready (local weights)")
        except Exception as e:
            logger.error("Failed to load SAM: %s", e)
            raise

    def segment_boxes(self, image_np: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        """Return the union mask of the objects in ``boxes``.

        Args:
            image_np: RGB image [H, W, 3].
            boxes:    xyxy boxes ``[N, 4]`` (e.g. from Grounding DINO).
        Returns:
            Binary mask [H, W] (uint8) — union of every box's best SAM mask.
        """
        h, w = image_np.shape[:2]
        if boxes is None or len(boxes) == 0:
            return np.zeros((h, w), np.uint8)

        pil = Image.fromarray(image_np)
        # One box list for one image → shape [1, N, 4].
        input_boxes = [[[float(x) for x in b] for b in boxes]]
        inputs = self._processor(pil, input_boxes=input_boxes, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)

        masks = self._processor.image_processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"].cpu(),
            inputs["reshaped_input_sizes"].cpu(),
        )[0]  # tensor [N, 3, H, W] — 3 multimask candidates per box
        scores = outputs.iou_scores.cpu()[0]  # [N, 3]

        union = np.zeros((h, w), np.uint8)
        for i in range(masks.shape[0]):
            best = int(torch.argmax(scores[i]))
            union |= masks[i, best].numpy().astype(np.uint8)
        return union


def get_sam_predictor() -> SamManager:
    """Get singleton SAM predictor instance."""
    return SamManager()


__all__ = ["SamManager", "get_sam_predictor"]
