# =============================================================
#  dynamic_config_manager/__init__.py
# =============================================================
"""
Dynamic-Config-Manager
----------------------

A *batterie-included* helper around **Pydantic-v2** + **pydantic-settings**.

Example
~~~~~~~
>>> from dynamic_config_manager import ConfigManager, BaseSettings, Field
>>>
>>> class AppCfg(BaseSettings):
...     username: str = Field("guest", json_schema_extra={"editable": False})
...     refresh: int = Field(60, ge=5, le=3600,
...                          json_schema_extra={"ui": "SpinBox", "suffix": "s"})
...
>>> cfg = ConfigManager.register("app", AppCfg, save_path="app.json", auto_save=True)
>>> cfg.get_value("refresh")
60
>>> cfg.set_value("refresh", 120)      # auto-saved + validated
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
# Logging – a library must *never* touch the root logger.
# --------------------------------------------------------------------- #
_logging.getLogger(__name__).addHandler(_logging.NullHandler())

# --------------------------------------------------------------------- #
# Public re-exports
# --------------------------------------------------------------------- #
from pydantic_settings import BaseSettings  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from .manager2 import ConfigManager  # noqa: E402  (singleton instance)

__all__ = [
    "ConfigManager",
    "BaseSettings",
    "BaseModel",
    "Field",
    "ValidationError",
]










# """
# Dynamic Config Manager:
# A singleton manager for handling multiple typed configuration sets
# using Pydantic and Pydantic-Settings.
# """

# # Read version dynamically from package metadata (or define here)
# # This is needed for the dynamic version in pyproject.toml
# __version__ = "0.1.0"

# import logging

# # Configure logging for the library
# # Set default NullHandler to avoid "No handler found" warnings.
# # Application code should configure logging properly.
# logging.getLogger(__name__).addHandler(logging.NullHandler())

# # --- Core Public Interface ---

# # Expose the main manager singleton instance
# from .manager import ConfigManager

# # --- Convenience Re-exports ---
# # Re-export key components from Pydantic and Pydantic-Settings
# # to make defining configuration models easier for users.
# # TODO: Examine needed types

# from pydantic_settings import BaseSettings, SettingsConfigDict
# from pydantic import (
#     Field,
#     SecretStr,
#     EmailStr,
#     HttpUrl,
#     ValidationError,
#     PositiveInt,
#     NegativeInt,
#     PositiveFloat,
#     NegativeFloat,
#     FilePath,
#     DirectoryPath,
#     Json,
#     BaseModel
# )

# __all__ = [
#     # Core manager
#     'ConfigManager',

#     # Base class for models
#     'BaseSettings',
#     'SettingsConfigDict',

#     # Core Pydantic components for defining models
#     'Field',
#     'SecretStr',
#     'ValidationError',

#     # Common Pydantic types
#     'EmailStr',
#     'HttpUrl',
#     'PositiveInt',
#     'NegativeInt',
#     'PositiveFloat',
#     'NegativeFloat',
#     'FilePath',
#     'DirectoryPath',
#     'Json',

#     # BaseModel for nested structures
#     'BaseModel',
# ]

