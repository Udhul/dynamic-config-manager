"""
Dynamic Config Manager:
A singleton manager for handling multiple typed configuration sets
using Pydantic and Pydantic-Settings.
"""

# Read version dynamically from package metadata (or define here)
# This is needed for the dynamic version in pyproject.toml
__version__ = "0.1.0"

import logging

# Configure logging for the library
# Set default NullHandler to avoid "No handler found" warnings.
# Application code should configure logging properly.
logging.getLogger(__name__).addHandler(logging.NullHandler())

# --- Core Public Interface ---

# Expose the main manager singleton instance
from .manager import ConfigManager

# --- Convenience Re-exports ---
# Re-export key components from Pydantic and Pydantic-Settings
# to make defining configuration models easier for users.
from pydantic_settings import BaseSettings
from pydantic import (
    Field,
    SecretStr,
    EmailStr,
    HttpUrl,
    ValidationError,
    PositiveInt,
    NegativeInt,
    PositiveFloat,
    NegativeFloat,
    FilePath,
    DirectoryPath,
    Json,
)

__all__ = [
    # Core manager
    'ConfigManager',

    # Base class for models
    'BaseSettings',

    # Core Pydantic components for defining models
    'Field',
    'SecretStr',
    'ValidationError',

    # Common Pydantic types (examples)
    'EmailStr',
    'HttpUrl',
    'PositiveInt',
    'NegativeInt',
    'PositiveFloat',
    'NegativeFloat',
    'FilePath',
    'DirectoryPath',
    'Json',
]

