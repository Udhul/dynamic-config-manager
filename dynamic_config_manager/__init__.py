# =============================================================
#  dynamic_config_manager/__init__.py
# =============================================================
"""
Dynamic-Config-Manager
======================

A *typed*, file-backed configuration framework that wraps **Pydantic-Settings v2**.

Main ideas
~~~~~~~~~~
* Each configuration is described by a **Pydantic BaseSettings** model - so
  **all** type-checking, defaulting, clamping, “nearest match” logic, UI hints,
  etc. live in the model itself (validators + `Field(json_schema_extra=…)`).
* A small **manager singleton** keeps track of many configurations, gives them a
  common *default* save directory, and makes bulk actions (`save_all`,
  `restore_all_defaults`) trivial.
* Per-config persistence is *opt-in* or *opt-out*:

  * do nothing → file is saved to
    `<default_dir>/<name>.json` **(default_dir is a stable folder inside
    `tempfile.gettempdir()` unless you override it once early in your app)**;
  * pass `save_path=` to push the file somewhere else;  
  * pass `persistent=False` for memory-only configs.

Quick example
~~~~~~~~~~~~~
```python
from dynamic_config_manager import BaseSettings, Field, ConfigManager

class CamCfg(BaseSettings):
    spindle_speed: int = Field(
        24_000, ge=4_000, le=24_000,
        json_schema_extra={"step": 1_000, "ui": "SpinBox"}
    )
    tool: str = Field(
        "flat",
        json_schema_extra={
            "options": ["flat", "ball", "vbit"],
            "editable": True,
            "ui": "ComboBox"
        }
    )

# 1) Use app-wide directory once
ConfigManager.default_dir = "~/my_project/config"

# 2) Register the config; nothing else to remember
cam_cfg = ConfigManager.register("cam", CamCfg, auto_save=True)

# 3) Safe path-based access
cam_cfg.set_value("spindle_speed", 18_000)   # validated + auto-saved
print(cam_cfg.get_value("tool"))             # → "flat"

# 4) Restore a single value or the whole file
cam_cfg.restore_value("spindle_speed", source="default")
# cam_cfg.restore_defaults()
"""

from __future__ import annotations

from importlib import metadata as _meta
import logging as _logging

# --------------------------------------------------------------------- #
# Version
# --------------------------------------------------------------------- #
try:  # When installed (pip/poetry)
    __version__: str = _meta.version("dynamic_config_manager")
except _meta.PackageNotFoundError:  # Editable checkout / source tree
    __version__ = "0.2.0"

# --------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------- #
_logging.getLogger(__name__).addHandler(_logging.NullHandler()) # *never* touch the root logger.

# --------------------------------------------------------------------- #
# Public re-exports
# --------------------------------------------------------------------- #
from pydantic_settings import BaseSettings  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from .manager import ConfigManager  # noqa: E402  (singleton instance)

__all__ = [
    "ConfigManager",
    "BaseSettings",
    "BaseModel",
    "Field",
    "ValidationError",
]
