"""Floor Tiling Visualizer — application package.

A FastAPI service that auto-detects room surfaces (floor, walls, ceiling) and
renders perspective-correct floor tiling and wall/ceiling paint previews.
"""
import sys

from floor_tiling.paths import REPO_ROOT

# The licensing layer depends on the sibling ``shared`` package, which lives at
# the repository root (outside this installable project). Make it importable.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

__version__ = "1.0.0"
