"""Project structure documentation"""

# Floor Tile Visualizer - Refactored Architecture

## Project Structure

```
Floor Tiling/
├── server.py                 # Main Fast API application (routes only)
├── index.html               # Frontend UI
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuration constants & environment-specific settings
├── core/
│   ├── __init__.py
│   └── helpers.py           # Helper functions (hex_to_bgr, extract_floor_quad, estimate_real_depth_cm)
├── patterns/
│   └── __init__.py          # Tile pattern functions & pattern registry
├── processors/
│   └── __init__.py          # Core rendering logic (apply_perspective_tiles)
├── ml_models/
│   └── __init__.py          # SAM2 model management & initialization
└── sam2/                    # External SAM2 library
```

## Module Descriptions

### 1. **config/** - Configuration Management
- **settings.py**: Centralized configuration constants
  - Max upload size
  - CORS origins
  - Model configuration
  - Default tile/grout parameters
  - Constraint ranges (min/max values)
  
**Benefits**: 
- All configuration in one place
- Easy to adjust parameters
- Environment-specific configuration

### 2. **core/** - Core Helper Functions
- **helpers.py**: Utility functions
  - `hex_to_bgr()` - Convert hex colors to BGR for OpenCV
  - `extract_floor_quad()` - Extract floor corners from mask
  - `estimate_real_depth_cm()` - Estimate 3D depth from perspective

**Benefits**:
- Reusable utility functions
- Clean separation of concerns
- Easy to test and maintain

### 3. **patterns/** - Tile Pattern Generators
- **__init__.py**: Pattern function registry
  - Grid, Brick, Diagonal, Herringbone, Checkerboard, Diagonal Checkerboard
  - `PATTERN_FUNCTIONS` dict for easy pattern lookup
  - `get_pattern()` utility function

**Benefits**:
- Extensible pattern system
- Easy to add new patterns
- Clear pattern interface

### 4. **processors/** - Image Processing & Rendering
- **__init__.py**: Core tile rendering function
  - `apply_perspective_tiles()` - Main homography-based tile renderer
  - Uses helper functions, patterns, and configuration

**Benefits**:
- Complex logic isolated from server
- Single responsibility principle
- Easy to test and optimize

### 5. **ml_models/** - Machine Learning Model Management
- **__init__.py**: SAM2 model initialization
  - `SAM2ModelManager` - Singleton pattern for model lifecycle
  - `get_sam2_predictor()` - Get or create predictor instance

**Benefits**:
- Lazy model loading (only when needed)
- Singleton pattern prevents multiple model instances
- Centralized model management
- Easy to extend for other models

### 6. **server.py** - FastAPI Application
- Clean routes only
- Imports from all modules
- Configuration via config/
- Delegated logic to processors/

**Benefits**:
- Minimal, readable code
- All business logic abstracted
- Only HTTP concerns handled here

## Design Patterns Used

### 1. **Singleton Pattern** (ml_models/)
- Ensures only one instance of SAM2 model
- Lazy initialization on first access

### 2. **Registry Pattern** (patterns/)
- Pattern functions registered in dictionary
- Easy to add new patterns without modifying core code

### 3. **Dependency Injection**
- Configuration settings passed to functions
- Decouples code from hardcoded values

### 4. **Separation of Concerns**
- Configuration isolated from logic
- UI/API separate from processing
- ML models separate from application logic

## Adding New Features

### Adding a New Tile Pattern
1. Add pattern function to `patterns/__init__.py`
2. Add to `PATTERN_FUNCTIONS` dictionary
3. Pattern is automatically available in routes

### Adding Configuration Parameters
1. Add to `config/settings.py`
2. Import where needed using: `from config.settings import PARAM_NAME`

### Adding Helper Functions
1. Create/update in `core/helpers.py`
2. Export from `core/__init__.py`
3. Import in processor: `from core import function_name`

## Benefits of This Architecture

✅ **Modularity**: Each module has a single responsibility
✅ **Maintainability**: Easy to find and update code
✅ **Testability**: Isolated functions are easy to test
✅ **Scalability**: Easy to add new patterns, helpers, or processors
✅ **Reusability**: Utility functions can be reused across modules
✅ **Configuration**: Centralized settings management
✅ **Documentation**: Clear module purposes via docstrings
✅ **Best Practices**: Follows common Python patterns and conventions
