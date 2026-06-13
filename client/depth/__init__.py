"""Monocular depth estimation package (Depth Anything V2, metric-indoor)."""

from .depth import DepthManager, get_depth_predictor

__all__ = ["DepthManager", "get_depth_predictor"]
