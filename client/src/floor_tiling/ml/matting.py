"""ViTMatte — trimap-based image matting for crisp paint edges.

Semantic masks can't resolve fine foreground structure (plant leaves, fronds),
so painting over them leaves faint "ghost" edges where wispy leaves sit inside
the wall mask.  ViTMatte refines a coarse mask into a soft alpha that captures
those thin edges precisely; the paint route then composites the new colour with
that alpha so foliage stays untouched and the wall paint stops exactly on the
real silhouette.

Offline-first: weights download once into the local ``models/`` dir.  The image
processor is constructed from defaults (no files needed), so only the model
weights are cached.
"""
import logging

import cv2
import numpy as np
import torch
from transformers import VitMatteForImageMatting, VitMatteImageProcessor

from floor_tiling.paths import model_dir

logger = logging.getLogger(__name__)


class VitMatteManager:
    """Manages the ViTMatte model lifecycle and inference (singleton)."""

    _instance = None
    _model = None
    _processor = None
    _model_id = "hustvl/vitmatte-small-composition-1k"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.local_path = model_dir("vitmatte", "VITMATTE_DIR")
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
                    logger.info("ViTMatte changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("ViTMatte weights not found in %s; downloading", self.local_path)
                self._model = VitMatteForImageMatting.from_pretrained(self._model_id)
                self._model.save_pretrained(self.local_path)
                marker.write_text(self._model_id)
                logger.info("ViTMatte downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading ViTMatte from %s", self.local_path)
                self._model = VitMatteForImageMatting.from_pretrained(str(self.local_path))

            # The processor has no repo files — build it from defaults.
            self._processor = VitMatteImageProcessor()
            self._model.eval()
            logger.info("ViTMatte ready (local weights)")
        except Exception as e:
            logger.error("Failed to load ViTMatte: %s", e)
            raise

    def matte(
        self,
        image_rgb: np.ndarray,
        mask: np.ndarray,
        max_side: int = 768,
        fg_erode: int = 9,
        bg_dilate: int = 5,
        color_demote_t: float = 22.0,
    ) -> np.ndarray:
        """Return a soft alpha [H, W] (float 0-1) for ``mask`` as foreground.

        A trimap is built automatically:
          * sure-foreground = the eroded mask MINUS pixels whose colour is far
            from the wall's own colour.  This demotes wispy leaves the mask
            wrongly swallowed (and which sit *inside* it, detached from any
            boundary) to "unknown" so ViTMatte can carve them out — fixing the
            ghost-leaf artefacts a pure boundary trimap can't reach.
          * sure-background = far from the mask.
          * unknown = the rest (boundary band + colour-deviant interior +
            wall-coloured holes), which ViTMatte resolves by appearance: green
            leaves / wood floor stay original, wall-coloured gaps get painted.

        ``color_demote_t`` is the LAB distance (0 disables the colour cue).

        Args:
            image_rgb: RGB image [H, W, 3].
            mask:      Binary-ish foreground mask [H, W] (the wall to paint).
        """
        h, w = mask.shape[:2]
        m = (mask > 0).astype(np.uint8)
        if not m.any():
            return np.zeros((h, w), np.float32)

        k = lambda s: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (s, s))
        fg = cv2.erode(m, k(fg_erode))
        # Demote colour-outliers (foliage, dark objects) inside the mask so they
        # become "unknown" rather than forced-paint. Use CHROMA only (LAB a,b) —
        # NOT lightness L — otherwise a bright/blown wall (flooded by window
        # light) reads as "far from wall colour" and gets carved out, reverting
        # to the white original (ghost blooms). Green leaves differ in chroma;
        # bright walls differ only in lightness, so chroma distance keeps them.
        if color_demote_t > 0:
            lab = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            sure = cv2.erode(m, k(31))
            sample = lab[(sure > 0) if sure.any() else (fg > 0)]
            if len(sample):
                wall_col = np.median(sample, axis=0)
                dist = np.linalg.norm(lab[:, :, 1:] - wall_col[1:], axis=2)
                fg = ((fg > 0) & (dist <= color_demote_t)).astype(np.uint8)
        bg = 1 - cv2.dilate(m, k(bg_dilate))
        tri = np.full((h, w), 0.5, np.float32)
        tri[fg > 0] = 1.0
        tri[bg > 0] = 0.0

        # Downscale for CPU speed; alpha is upsampled back to full resolution.
        lw = min(max_side, w)
        nh = int(round(h * lw / w))
        ri = cv2.resize(image_rgb, (lw, nh))
        rt = cv2.resize(tri, (lw, nh), interpolation=cv2.INTER_NEAREST)

        inputs = self._processor(images=ri, trimaps=rt * 255.0, return_tensors="pt")
        with torch.no_grad():
            alpha = self._model(**inputs).alphas[0, 0].cpu().numpy()
        # The processor pads to a multiple of 32 — crop back before upscaling.
        alpha = alpha[:nh, :lw]
        alpha = cv2.resize(alpha, (w, h))
        return np.clip(alpha, 0.0, 1.0).astype(np.float32)


def get_matting_predictor() -> VitMatteManager:
    """Get singleton ViTMatte predictor instance."""
    return VitMatteManager()


__all__ = ["VitMatteManager", "get_matting_predictor"]
