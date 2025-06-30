from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field
from pydantic.fields import PydanticUndefined
from pydantic_settings import BaseSettings

__all__ = ["DynamicBaseSettings", "ConfigField"]


class DynamicBaseSettings(BaseSettings):
    """Convenience base class used by Dynamic Config Manager."""

    pass


def ConfigField(
    default: Any = PydanticUndefined,
    *,
    ui_hint: Optional[str] = None,
    ui_extra: Optional[Dict[str, Any]] = None,
    options: Optional[List[Any]] = None,
    autofix_settings: Optional[Dict[str, Any]] = None,
    format_spec: Optional[Dict[str, Any]] = None,
    json_schema_extra: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
):
    """Wrapper around :func:`pydantic.Field` building json_schema_extra."""

    extra = dict(json_schema_extra or {})
    if ui_hint is not None:
        extra["ui_hint"] = ui_hint
    if ui_extra is not None:
        extra["ui_extra"] = dict(ui_extra)
    if options is not None:
        extra["options"] = list(options)
    if autofix_settings is not None:
        extra["autofix"] = dict(autofix_settings)
    if format_spec is not None:
        extra["format_spec"] = dict(format_spec)

    return Field(default, json_schema_extra=extra, **kwargs)
