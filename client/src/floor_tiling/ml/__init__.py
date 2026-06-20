"""Machine-learning model wrappers.

Each wrapper is an offline-first singleton: weights download once into the
shared model cache (see :mod:`floor_tiling.paths`) and load from disk thereafter.

  - Mask2Former / OneFormer → semantic segmentation (floor / wall / ceiling)
  - Depth Anything V2        → metric depth (wall-plane separation)
"""

from .mask2former import Mask2FormerManager, get_mask2former_predictor
from .oneformer import OneFormerManager, get_oneformer_predictor
from .depth import DepthManager, get_depth_predictor
from .mlsd import MLSDManager, get_mlsd_predictor

__all__ = [
    "Mask2FormerManager",
    "get_mask2former_predictor",
    "OneFormerManager",
    "get_oneformer_predictor",
    "DepthManager",
    "get_depth_predictor",
    "MLSDManager",
    "get_mlsd_predictor",
]
