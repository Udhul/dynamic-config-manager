"""
General-purpose Pydantic model definitions for common configuration structures.
These serve as examples or base models for users of the dynamic-config-manager.
"""

from typing import List, Dict, Any, Optional, Literal
from typing_extensions import Annotated # Use Annotated for constraints

from pydantic import (
    Field,
    field_validator,
    model_validator,

    HttpUrl,
    SecretStr,
    FilePath,
    DirectoryPath,
    PositiveInt,
    BaseModel, # Use BaseModel for nested structures not needing BaseSettings features
)
from pydantic_settings import *

# --- General Application Settings ---

class GeneralAppSettings(BaseSettings):
    """Basic application settings like name, version, and logging level."""
    app_name: str = Field(
        default="MyApp",
        description="The public name of the application.",
        json_schema_extra={'editable': False} # Typically not user-editable
    )
    version: str = Field(
        default="0.1.0",
        description="Application version.",
        json_schema_extra={'editable': False} # Typically set by build process
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Set the application logging level.",
        json_schema_extra={
            'ui_hint': 'dropdown',
            'ui_choices': ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            'editable': True
        }
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable detailed debug logging and features.",
        json_schema_extra={'ui_hint': 'checkbox', 'editable': True}
    )

    model_config = SettingsConfigDict(
        extra='ignore',
        # Example: Allow loading 'LOG_LEVEL' env var for log_level field
        # env_prefix='MYAPP_' # Optional prefix for environment variables
    )

# --- User Interface Settings ---

class UISettings(BaseSettings):
    """Settings related to the user interface appearance and behavior."""
    theme: Literal["dark", "light", "system"] = Field(
        default="system",
        description="UI color theme.",
        json_schema_extra={
            'ui_hint': 'dropdown',
            'ui_choices': ['dark', 'light', 'system'],
            'editable': True
        }
    )
    font_size: Annotated[int, Field(ge=8, le=24)] = Field(
        default=12,
        description="Base font size for the UI.",
        json_schema_extra={'ui_hint': 'slider', 'step': 1, 'min': 8, 'max': 24, 'editable': True}
    )
    show_tooltips: bool = Field(
        default=True,
        description="Display helpful tooltips on hover.",
        json_schema_extra={'ui_hint': 'checkbox', 'editable': True}
    )

    model_config = SettingsConfigDict(extra='ignore')

# --- Database Connection Settings ---

class DatabaseSettings(BaseSettings):
    """Configuration for connecting to a database."""
    db_url: str = Field( # Or use specific DSN types like PostgresDsn if needed
        default="sqlite:///./default_app.db",
        description="Database connection URL (e.g., postgresql://user:pass@host/db)",
        json_schema_extra={'editable': True}
    )
    username: Optional[str] = Field(
        default=None,
        description="Database username (if not in URL).",
        json_schema_extra={'editable': True}
    )
    password: Optional[SecretStr] = Field( # Use SecretStr for sensitive values
        default=None,
        description="Database password (if not in URL).",
        json_schema_extra={'ui_hint': 'password', 'editable': True}
    )
    pool_size: Annotated[int, Field(ge=1, le=100)] = Field(
        default=5,
        description="Database connection pool size.",
        json_schema_extra={'editable': True}
    )
    echo_sql: bool = Field(
        default=False,
        description="Log SQL statements executed.",
        json_schema_extra={'ui_hint': 'checkbox', 'editable': True}
    )

    model_config = SettingsConfigDict(extra='ignore')

# --- External API Settings ---

class APISettings(BaseSettings):
    """Settings for interacting with an external API."""
    base_url: HttpUrl = Field(
        default="https://api.example.com", # type: ignore[assignment]
        description="Base URL for the external API.",
        json_schema_extra={'editable': True}
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API Key for authentication.",
        json_schema_extra={'ui_hint': 'password', 'editable': True}
    )
    timeout_seconds: Annotated[float, Field(gt=0, le=300)] = Field(
        default=30.0,
        description="Request timeout in seconds.",
        json_schema_extra={'ui_hint': 'spinbox', 'step': 0.5, 'decimals': 1, 'editable': True}
    )
    retry_attempts: Annotated[int, Field(ge=0, le=10)] = Field(
        default=3,
        description="Number of retry attempts on failure.",
        json_schema_extra={'ui_hint': 'spinbox', 'step': 1, 'editable': True}
    )

    model_config = SettingsConfigDict(extra='ignore')

# --- File Path Settings ---

class PathSettings(BaseSettings):
    """Configuration for commonly used file paths or directories."""
    input_directory: Optional[DirectoryPath] = Field(
        default=None,
        description="Default directory for input files.",
        json_schema_extra={'ui_hint': 'directory_chooser', 'editable': True}
    )
    output_directory: Optional[DirectoryPath] = Field(
        default=None,
        description="Default directory for output files.",
        json_schema_extra={'ui_hint': 'directory_chooser', 'editable': True}
    )
    template_file: Optional[FilePath] = Field(
        default=None,
        description="Path to a template file.",
        json_schema_extra={'ui_hint': 'file_chooser', 'editable': True}
    )

    # Pydantic Path types perform validation (existence check) by default.
    # Make validation optional if paths might not exist yet:
    # model_config = SettingsConfigDict(extra='ignore', validate_assignment=False)
    # Or handle validation errors in the app.
    model_config = SettingsConfigDict(extra='ignore')

    # Example validator to ensure output dir exists or can be created
    @model_validator(mode='after')
    def check_output_dir(self) -> 'PathSettings':
        if self.output_directory and not self.output_directory.exists():
            try:
                self.output_directory.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                 raise ValueError(f"Output directory '{self.output_directory}' does not exist and cannot be created: {e}") from e
        return self


# --- File Logging Settings ---

class FileLoggingSettings(BaseSettings):
    """Specific settings for logging to a file."""
    enable_file_logging: bool = Field(
        default=False,
        description="Enable writing logs to a file.",
        json_schema_extra={'editable': True}
    )
    log_file: Optional[FilePath] = Field(
        default=None, # Example: "app_log.log" - Needs careful path handling
        description="Path to the log file. If relative, usually relative to app start dir.",
        json_schema_extra={'ui_hint': 'file_save_chooser', 'editable': True}
    )
    max_bytes: PositiveInt = Field(
        default=10*1024*1024, # 10 MB
        description="Maximum size of the log file before rotation (in bytes).",
        json_schema_extra={'editable': True}
    )
    backup_count: Annotated[int, Field(ge=0)] = Field(
        default=5,
        description="Number of backup log files to keep.",
        json_schema_extra={'editable': True}
    )
    log_format: str = Field(
        default='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        description="Format string for log messages (Python logging style).",
        json_schema_extra={'ui_hint': 'textarea', 'editable': True}
    )

    model_config = SettingsConfigDict(extra='ignore')


# --- Feature Flag Settings ---

class FeatureFlagSettings(BaseSettings):
    """A collection of boolean feature flags."""
    # Example: Use a dictionary for flags
    flags: Dict[str, bool] = Field(
        default={
            "new_dashboard": False,
            "experimental_import": False,
            "cloud_sync": True,
        },
        description="Enable/disable application features.",
        json_schema_extra={'ui_hint': 'dict_editor', 'editable': True} # Requires custom UI widget
    )
    # Alternatively, define each flag explicitly if the set is fixed:
    # enable_new_dashboard: bool = Field(default=False, description="...")
    # enable_experimental_import: bool = Field(default=False, description="...")

    model_config = SettingsConfigDict(extra='ignore')

# --- Add more general-purpose models as needed ---
# E.g., UserProfileSettings, PluginSettings, ThemeCustomizationSettings, etc.
