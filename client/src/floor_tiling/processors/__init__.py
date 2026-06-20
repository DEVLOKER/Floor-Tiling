"""Processors package.

Public API: ``apply_perspective_tiles``, ``apply_wall_paint``
"""

from .tile_renderer import apply_perspective_tiles
from .wall_painter import apply_wall_paint

__all__ = ["apply_perspective_tiles", "apply_wall_paint"]
