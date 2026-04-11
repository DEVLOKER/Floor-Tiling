"""Machine Learning Models management"""
import os
import torch
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor
from config.settings import MODEL_CONFIG


class SAM2ModelManager:
    """Manages SAM2 model lifecycle."""
    
    _instance = None
    _model = None
    _predictor = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SAM2ModelManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize SAM2 model on first instantiation."""
        if self._model is None:
            self._load_model()
    
    def _load_model(self):
        """Load SAM2 model."""
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        
        print("🟡 Loading SAM2 model on CPU...")
        try:
            variant = MODEL_CONFIG["variant"]
            device = MODEL_CONFIG["device"]
            self._model = build_sam2(variant, device=device)
            self._predictor = SAM2ImagePredictor(self._model)
            print("✅ Model loaded successfully on CPU")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            raise
    
    @property
    def predictor(self) -> SAM2ImagePredictor:
        """Get SAM2 predictor instance."""
        if self._predictor is None:
            self._load_model()
        return self._predictor
    
    def is_cuda_available(self) -> bool:
        """Check if CUDA is available."""
        return torch.cuda.is_available()


def get_sam2_predictor() -> SAM2ImagePredictor:
    """Get singleton SAM2 predictor instance.
    
    Returns:
        SAM2ImagePredictor instance
    """
    manager = SAM2ModelManager()
    return manager.predictor


from .mask2former import get_mask2former_predictor

__all__ = ["SAM2ModelManager", "get_sam2_predictor", "get_mask2former_predictor"]
