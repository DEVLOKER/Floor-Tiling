"""YOLO-World — fast open-vocabulary object detection.

A lighter, CPU-friendly alternative to Grounding DINO for finding wall objects
to exclude from painting (air conditioner, sockets, pipes…): ~0.8 s/image vs
~7 s, with comparable box quality.

Offline-first.  YOLO-World normally needs a CLIP text encoder at runtime to turn
the class prompts into embeddings, which would require network access.  We avoid
that by *baking* our fixed prompt list (``OPEN_VOCAB_OBJECT_PROMPT``) into the
weights once with ``set_classes`` + ``save``; the resulting model carries the
text embeddings, so inference is fully offline and CLIP-free.  The baked model is
rebuilt only when the prompt list changes (tracked by a signature marker).
"""
import hashlib
import logging

import numpy as np

from floor_tiling.paths import model_dir
from floor_tiling.config.settings import OPEN_VOCAB_OBJECT_PROMPT, YOLO_WORLD_VARIANT

logger = logging.getLogger(__name__)

_VALID_VARIANTS = {"s", "m", "l", "x"}


def _prompt_classes() -> list:
    return [c.strip() for c in OPEN_VOCAB_OBJECT_PROMPT.split(".") if c.strip()]


class YoloWorldManager:
    """Manages the YOLO-World model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    # Size variant chosen in settings (YOLO_WORLD_VARIANT): s/m/l/x. x gives the
    # best recall (~1s CPU); s is smallest/fastest. Baked file is per-variant so
    # switching size rebuilds the right one.
    _variant = YOLO_WORLD_VARIANT if YOLO_WORLD_VARIANT in _VALID_VARIANTS else "x"
    _base_name = f"yolov8{_variant}-worldv2.pt"
    _baked_name = f"ft_world_{_variant}.pt"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_dir = model_dir("yolo_world", "YOLO_WORLD_DIR")
        self.classes = _prompt_classes()
        if self._model is None:
            self._load_model()

    def _signature(self) -> str:
        return hashlib.md5("|".join(self.classes).encode("utf-8")).hexdigest()

    def _load_model(self):
        try:
            from ultralytics import YOLOWorld

            self.local_dir.mkdir(parents=True, exist_ok=True)
            baked = self.local_dir / self._baked_name
            marker = self.local_dir / ".classes"
            cached = marker.read_text().strip() if marker.exists() else None
            sig = self._signature()

            if not baked.exists() or cached != sig:
                # ── One-time build: bake the prompt embeddings into the model ──
                base = self.local_dir / self._base_name
                if not base.exists():
                    logger.info("YOLO-World base weights missing; downloading to %s", base)
                    from ultralytics.utils.downloads import attempt_download_asset
                    attempt_download_asset(str(base))
                logger.info("Baking %d open-vocab classes into YOLO-World", len(self.classes))
                builder = YOLOWorld(str(base))
                builder.set_classes(self.classes)   # needs CLIP (cached on first run)
                builder.save(str(baked))
                # Drop optimizer/EMA state so the on-disk model is inference-sized.
                try:
                    from ultralytics.utils.torch_utils import strip_optimizer
                    strip_optimizer(str(baked))
                except Exception as exc:  # non-fatal: just leaves a larger file
                    logger.warning("strip_optimizer skipped: %s", exc)
                marker.write_text(sig)
                logger.info("YOLO-World baked model saved to %s", baked)
            else:
                logger.info("Loading YOLO-World (baked) from %s", baked)

            self._model = YOLOWorld(str(baked))
            logger.info("YOLO-World ready (local weights, %d classes)", len(self.classes))
        except Exception as e:
            logger.error("Failed to load YOLO-World: %s", e)
            raise

    def detect(self, image_np: np.ndarray, box_threshold: float = 0.1) -> np.ndarray:
        """Detect the baked-in classes and return their boxes.

        Args:
            image_np: RGB image [H, W, 3].
        Returns:
            Float array of xyxy boxes ``[N, 4]`` (empty if none).
        """
        # Ultralytics expects BGR numpy (cv2 convention); our pipeline is RGB.
        bgr = image_np[:, :, ::-1]
        result = self._model.predict(bgr, conf=box_threshold, verbose=False)[0]
        if len(result.boxes) == 0:
            return np.zeros((0, 4), np.float32)
        return result.boxes.xyxy.cpu().numpy().astype(np.float32)


def get_yolo_world_predictor() -> YoloWorldManager:
    """Get singleton YOLO-World predictor instance."""
    return YoloWorldManager()


__all__ = ["YoloWorldManager", "get_yolo_world_predictor"]
