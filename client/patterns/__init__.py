"""Tile patterns package.

Public API
----------
``PATTERN_FUNCTIONS`` — dict mapping name -> function
``get_pattern(name)``  — look up a pattern function by name
Individual pattern functions are also importable directly.
"""

from .patterns import (
    PATTERN_FUNCTIONS,
    get_pattern,
    pattern_grid,
    pattern_brick,
    pattern_herringbone,
    pattern_checkerboard,
    pattern_chevron,
    pattern_basketweave,
    pattern_versailles,
)

__all__ = [
    "PATTERN_FUNCTIONS",
    "get_pattern",
    "pattern_grid",
    "pattern_brick",
    "pattern_herringbone",
    "pattern_checkerboard",
    "pattern_chevron",
    "pattern_basketweave",
    "pattern_versailles",
]
