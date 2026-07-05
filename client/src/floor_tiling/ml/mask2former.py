"""Mask2Former Model management for automatic floor/wall detection"""
import logging

import torch
import numpy as np
from PIL import Image
from transformers import Mask2FormerForUniversalSegmentation, AutoImageProcessor

from floor_tiling.paths import model_dir
from floor_tiling.ml.labels import object_class_ids, opening_class_ids
from floor_tiling.config.settings import MASK2FORMER_VARIANT

logger = logging.getLogger(__name__)

# ADE20K-semantic Swin variants (bigger = cleaner masks, slower).
_VARIANTS = {
    "tiny": "facebook/mask2former-swin-tiny-ade-semantic",
    "small": "facebook/mask2former-swin-small-ade-semantic",
    "base": "facebook/mask2former-swin-base-ade-semantic",
    "large": "facebook/mask2former-swin-large-ade-semantic",
}


class Mask2FormerManager:
    """Manages Mask2Former model lifecycle and inference."""
    
    _instance = None
    _model = None
    _processor = None
    _object_ids = None   # cached ADE20K ids of wall fixtures/decor to exclude
    _opening_ids = None  # cached ADE20K ids of doors & windows
    # Size variant chosen in settings (MASK2FORMER_VARIANT); bigger = cleaner
    # masks but slower. Downloaded once into the local ``models/`` dir, then
    # loaded offline; changing the variant re-downloads on next start.
    _model_id = _VARIANTS.get(MASK2FORMER_VARIANT, _VARIANTS["large"])
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Mask2FormerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Weight cache: MASK2FORMER_DIR env override (e.g. a mounted volume)
        # falling back to the shared models dir (see floor_tiling.paths).
        self.local_path = model_dir("mask2former", "MASK2FORMER_DIR", MASK2FORMER_VARIANT, self._model_id)
        if self._model is None:
            self._load_model()

    def _load_model(self):
        """Load model from local storage or download if missing."""
        try:
            self.local_path.mkdir(parents=True, exist_ok=True)
            
            # Check if essential files exist locally (config + weights)
            config_file = self.local_path / "config.json"
            # Support both standard pytorch and safetensors
            has_weights = (self.local_path / "model.safetensors").exists() or (self.local_path / "pytorch_model.bin").exists()

            # Check if cached model matches expected model ID
            marker_file = self.local_path / ".model_id"
            cached_id = marker_file.read_text().strip() if marker_file.exists() else None
            model_mismatch = cached_id != self._model_id
            
            if not config_file.exists() or not has_weights or model_mismatch:
                if model_mismatch and has_weights:
                    logger.info("Mask2Former model changed (%s -> %s); re-downloading", cached_id, self._model_id)
                    # Clean old model files
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    logger.info("Mask2Former weights not found in %s; downloading from Hugging Face", self.local_path)

                self._processor = AutoImageProcessor.from_pretrained(self._model_id, use_fast=True)
                self._model = Mask2FormerForUniversalSegmentation.from_pretrained(self._model_id)
                # Save locally for future use
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                # Write marker so we detect model changes in future
                marker_file.write_text(self._model_id)
                logger.info("Mask2Former downloaded and cached to %s", self.local_path)
            else:
                logger.info("Loading Mask2Former (%s) from %s", self._model_id, self.local_path)
                self._processor = AutoImageProcessor.from_pretrained(str(self.local_path), use_fast=True)
                # use_safetensors=True will prioritize .safetensors files if available
                self._model = Mask2FormerForUniversalSegmentation.from_pretrained(
                    str(self.local_path),
                    use_safetensors=True
                )

            self._model.eval()
            logger.info("Mask2Former ready (local weights)")
        except Exception as e:
            logger.error("Failed to load Mask2Former: %s", e)
            raise

    def predict(self, image_np: np.ndarray):
        """
        Perform semantic segmentation to find floors, walls and the ceiling.

        ADE20K IDs (0-indexed in Transformers):
        0: wall
        3: floor
        5: ceiling

        Args:
            image_np: RGB image as numpy array [H, W, 3]

        Returns:
            floor_mask:   Binary numpy array [H, W]
            wall_mask:    Binary numpy array [H, W]
            ceiling_mask: Binary numpy array [H, W]
            object_mask:  Binary [H, W] — wall fixtures/decor to EXCLUDE.
            opening_mask: Binary [H, W] — doors & windows to EXCLUDE.
        """
        inputs = self._processor(images=image_np, return_tensors="pt")

        with torch.no_grad():
            outputs = self._model(**inputs)

        # Post-process to get semantic map
        target_sizes = [image_np.shape[:2]]
        predicted_semantic_map = self._processor.post_process_semantic_segmentation(
            outputs, target_sizes=target_sizes
        )[0]

        semantic_map = predicted_semantic_map.cpu().numpy()

        # Extract specific classes
        wall_mask = (semantic_map == 0).astype(np.uint8)
        floor_mask = (semantic_map == 3).astype(np.uint8)
        ceiling_mask = (semantic_map == 5).astype(np.uint8)

        # Excluded classes, split into fixtures/decor vs doors&windows (resolved
        # once from the model's label map).
        if self._object_ids is None:
            self._object_ids = object_class_ids(self._model.config.id2label)
            self._opening_ids = opening_class_ids(self._model.config.id2label)
        object_mask = (
            np.isin(semantic_map, list(self._object_ids)).astype(np.uint8)
            if self._object_ids else np.zeros_like(wall_mask)
        )
        opening_mask = (
            np.isin(semantic_map, list(self._opening_ids)).astype(np.uint8)
            if self._opening_ids else np.zeros_like(wall_mask)
        )

        return floor_mask, wall_mask, ceiling_mask, object_mask, opening_mask

def get_mask2former_predictor() -> Mask2FormerManager:
    """Get singleton Mask2Former predictor instance."""
    return Mask2FormerManager()

__all__ = ["Mask2FormerManager", "get_mask2former_predictor"]
