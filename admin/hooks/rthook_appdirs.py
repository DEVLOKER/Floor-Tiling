"""
Runtime hook — runs before everything else in the frozen exe.

Some versions of setuptools / pkg_resources require 'appdirs' at import
time.  If it wasn't bundled (it is often not installed as a standalone
package on modern setups), the PyInstaller runtime hook pyi_rth_pkgres
crashes with:
    ImportError: The 'appdirs' package is required

We provide a minimal stub so pkg_resources can finish initialising.
"""
import sys
import types

if "appdirs" not in sys.modules:
    try:
        import appdirs  # noqa: F401 — already installed, nothing to do
    except ImportError:
        _stub = types.ModuleType("appdirs")

        def _noop(*args, **kwargs):
            return ""

        _stub.user_cache_dir    = _noop
        _stub.user_data_dir     = _noop
        _stub.user_config_dir   = _noop
        _stub.site_data_dir     = _noop
        _stub.site_config_dir   = _noop
        _stub.user_log_dir      = _noop
        _stub.AppDirs           = type("AppDirs", (), {
            "__init__": lambda self, *a, **kw: None,
            "user_cache_dir":  property(lambda self: ""),
            "user_data_dir":   property(lambda self: ""),
            "user_config_dir": property(lambda self: ""),
            "site_data_dir":   property(lambda self: ""),
        })

        sys.modules["appdirs"] = _stub
