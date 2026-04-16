"""Mask2Former Model management for automatic floor/wall detection"""
import os
import torch
import numpy as np
from PIL import Image
from transformers import Mask2FormerForUniversalSegmentation, AutoImageProcessor
from pathlib import Path

class Mask2FormerManager:
    """Manages Mask2Former model lifecycle and inference."""
    
    _instance = None
    _model = None
    _processor = None
    _model_id = "facebook/mask2former-swin-base-IN21k-ade-semantic"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Mask2FormerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Resolve local path relative to project root
        self.local_path = Path(__file__).resolve().parent / "models"
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
                    print(f"🔄 Model changed from {cached_id} → {self._model_id}, re-downloading...")
                    # Clean old model files
                    for f in self.local_path.glob("*"):
                        if f.is_file():
                            f.unlink()
                else:
                    print(f"⏬ Mask2Former not found in {self.local_path}, downloading from Hugging Face...")
                
                self._processor = AutoImageProcessor.from_pretrained(self._model_id, use_fast=True)
                self._model = Mask2FormerForUniversalSegmentation.from_pretrained(self._model_id)
                # Save locally for future use
                self._processor.save_pretrained(self.local_path)
                self._model.save_pretrained(self.local_path)
                # Write marker so we detect model changes in future
                marker_file.write_text(self._model_id)
                print(f"✅ Model downloaded and saved to {self.local_path}")
            else:
                print(f"🟡 Loading Mask2Former ({self._model_id}) from local storage")
                self._processor = AutoImageProcessor.from_pretrained(str(self.local_path), use_fast=True)
                # use_safetensors=True will prioritize .safetensors files if available
                self._model = Mask2FormerForUniversalSegmentation.from_pretrained(
                    str(self.local_path), 
                    use_safetensors=True
                )
                print("✅ Model loaded successfully (from local weights)")
            
            self._model.eval()
        except Exception as e:
            print(f"❌ Error loading Mask2Former: {e}")
            raise

    def predict(self, image_np: np.ndarray):
        """
        Perform semantic segmentation to find floors and walls.
        
        ADE20K IDs (0-indexed in Transformers):
        0: wall
        3: floor
        
        Args:
            image_np: RGB image as numpy array [H, W, 3]
            
        Returns:
            floor_mask: Binary numpy array [H, W]
            wall_mask: Binary numpy array [H, W]
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

        return floor_mask, wall_mask

def get_mask2former_predictor() -> Mask2FormerManager:
    """Get singleton Mask2Former predictor instance."""
    return Mask2FormerManager()

__all__ = ["Mask2FormerManager", "get_mask2former_predictor"]
