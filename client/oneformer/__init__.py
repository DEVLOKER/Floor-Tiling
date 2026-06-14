"""OneFormer segmentation package (ADE20K, used in ensemble with Mask2Former)."""

from .oneformer import OneFormerManager, get_oneformer_predictor

__all__ = ["OneFormerManager", "get_oneformer_predictor"]
