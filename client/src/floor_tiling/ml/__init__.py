"""Machine-learning model wrappers.

Each wrapper is an offline-first singleton: weights download once into the
shared model cache (see :mod:`floor_tiling.paths`) and load from disk thereafter.

  - Mask2Former / OneFormer → semantic segmentation (floor / wall / ceiling)
  - Depth Anything V2        → metric depth (wall-plane separation)
  - Grounding DINO + SAM     → open-vocab wall objects to exclude from painting
"""

from .mask2former import Mask2FormerManager, get_mask2former_predictor
from .oneformer import OneFormerManager, get_oneformer_predictor
from .depth import DepthManager, get_depth_predictor
from .mlsd import MLSDManager, get_mlsd_predictor
from .grounding_dino import GroundingDINOManager, get_grounding_dino_predictor
from .yolo_world import YoloWorldManager, get_yolo_world_predictor
from .sam import SamManager, get_sam_predictor
from .matting import VitMatteManager, get_matting_predictor

__all__ = [
    "Mask2FormerManager",
    "get_mask2former_predictor",
    "OneFormerManager",
    "get_oneformer_predictor",
    "DepthManager",
    "get_depth_predictor",
    "MLSDManager",
    "get_mlsd_predictor",
    "GroundingDINOManager",
    "get_grounding_dino_predictor",
    "YoloWorldManager",
    "get_yolo_world_predictor",
    "SamManager",
    "get_sam_predictor",
    "VitMatteManager",
    "get_matting_predictor",
]
