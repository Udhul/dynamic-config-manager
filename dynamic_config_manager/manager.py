# =============================================================
#  dynamic_config_manager/manager.py
# =============================================================
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Generic

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo, PydanticUndefined
from pydantic_core import to_jsonable_python
from pydantic_settings import BaseSettings

__all__ = ["ConfigManager"]

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseSettings)


class _ActiveAccessorProxy(Generic[T]):
    """Attribute style accessor for active values."""

    def __init__(self, inst: "ConfigInstance", prefix: str = ""):
        object.__setattr__(self, "_inst", inst)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, item: str):
        path = f"{self._prefix}.{item}" if self._prefix else item
        val = self._inst.get_value(path)
        if isinstance(val, BaseModel):
            return _ActiveAccessorProxy(self._inst, path)
        return val

    def __setattr__(self, item: str, value: Any):
        path = f"{self._prefix}.{item}" if self._prefix else item
        self._inst.set_value(path, value)


class _MetaAccessorProxy(Generic[T]):
    """Attribute style accessor for field metadata."""

    def __init__(self, inst: "ConfigInstance", prefix: str = ""):
        object.__setattr__(self, "_inst", inst)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, item: str):
        path = f"{self._prefix}.{item}" if self._prefix else item
        meta = self._inst.get_metadata(path)
        if hasattr(meta.get("type"), "model_fields"):
            return _MetaAccessorProxy(self._inst, path)
        return meta


class _DefaultAccessorProxy(Generic[T]):
    """Attribute style accessor for default values (read-only)."""

    def __init__(self, inst: "ConfigInstance", prefix: str = ""):
        object.__setattr__(self, "_inst", inst)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, item: str):
        path = f"{self._prefix}.{item}" if self._prefix else item
        val = _deep_get(self._inst._defaults, path.split("."))
        if isinstance(val, BaseModel):
            return _DefaultAccessorProxy(self._inst, path)
        return val

    def __setattr__(self, item: str, value: Any):
        raise AttributeError("Default values are read-only")


class _SavedAccessorProxy(Generic[T]):
    """Attribute style accessor for values persisted on disk (read-only)."""

    def __init__(self, inst: "ConfigInstance", prefix: str = ""):
        object.__setattr__(self, "_inst", inst)
        object.__setattr__(self, "_prefix", prefix)

    def __getattr__(self, item: str):
        path = f"{self._prefix}.{item}" if self._prefix else item
        val = self._inst._get_saved_value(path)
        if isinstance(val, BaseModel):
            return _SavedAccessorProxy(self._inst, path)
        return val

    def __setattr__(self, item: str, value: Any):
        raise AttributeError("Saved values are read-only")


# --------------------------------------------------------------------------- #
#                              helpers                                         #
# --------------------------------------------------------------------------- #


def _deep_get(data: Any, keys: List[str]) -> Any:
    cur = data
    for key in keys:
        if isinstance(cur, BaseModel):
            cur = getattr(cur, key)
        elif isinstance(cur, dict):
            cur = cur[key]
        elif isinstance(cur, list):
            cur = cur[int(key)]
        else:
            raise KeyError(f"Cannot traverse into {type(cur)} with '{key}'.")
    return cur


def _deep_set(data: Any, keys: List[str], value: Any) -> BaseModel | Any:
    """Return a copy of ``data`` with ``value`` written at ``keys`` path."""

    if not keys:
        return value

    head, *tail = keys

    # normalise None so that intermediate containers can be created
    if data is None:
        data = [] if head.isdigit() else {}

    if isinstance(data, BaseModel):
        copied = data.model_dump(mode="python")
        next_val = copied.get(head)
        copied[head] = _deep_set(next_val, tail, value)
        return data.__class__(**copied)

    if isinstance(data, dict):
        copied = {**data}
        next_val = copied.get(head)
        copied[head] = _deep_set(next_val, tail, value)
        return copied

    if isinstance(data, list):
        idx = int(head)
        copied = list(data)
        while len(copied) <= idx:
            copied.append(None)
        copied[idx] = _deep_set(copied[idx], tail, value)
        return copied

    raise KeyError(f"Cannot traverse into {type(data)} with '{head}'.")


def _deep_set_dict(data: Any, keys: List[str], value: Any) -> Any:
    """Return a plain Python structure with ``value`` set at ``keys`` path.

    Similar to :func:`_deep_set` but never instantiates Pydantic models.
    All ``BaseModel`` instances are treated as dictionaries via
    ``model_dump(mode="python")`` so that validation only happens once when the
    full model is reconstructed. This avoids early validation errors before
    any auto-fix logic runs.
    """

    if not keys:
        return value

    head, *tail = keys

    if isinstance(data, BaseModel):
        data = data.model_dump(mode="python")

    if data is None:
        data = [] if head.isdigit() else {}

    if isinstance(data, dict):
        copied = {**data}
        next_val = copied.get(head)
        copied[head] = _deep_set_dict(next_val, tail, value)
        return copied

    if isinstance(data, list):
        idx = int(head)
        copied = list(data)
        while len(copied) <= idx:
            copied.append(None)
        copied[idx] = _deep_set_dict(copied[idx], tail, value)
        return copied

    raise KeyError(f"Cannot traverse into {type(data)} with '{head}'.")


# ---------- file I/O -------------------------------------------------------- #


def _detect_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return {"yml": "yaml", "yaml": "yaml", "toml": "toml"}.get(ext, "json")


def _load_file(path: Path, *, file_format: Optional[str] = None) -> Dict[str, Any]:
    fmt = (file_format or _detect_format(path)).lower()
    text = path.read_text(encoding="utf-8")
    if fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "YAML support requires PyYAML. Install with 'pip install dynamic-config-manager[yaml]'"
            ) from e
        return yaml.safe_load(text) or {}
    if fmt == "toml":
        try:
            import tomli
        except ImportError:
            try:
                import tomllib as tomli
            except ImportError as e:
                raise ImportError(
                    "TOML support requires tomli/tomllib. Install with 'pip install dynamic-config-manager[toml]'"
                ) from e
        return tomli.loads(text)
    return json.loads(text)


def _dump_file(path: Path, data: Dict[str, Any], *, file_format: Optional[str] = None):
    fmt = (file_format or _detect_format(path)).lower()
    if fmt == "yaml":
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "YAML support requires PyYAML. Install with 'pip install dynamic-config-manager[yaml]'"
            ) from e
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    elif fmt == "toml":
        try:
            import tomli_w
        except ImportError as e:
            raise ImportError(
                "TOML write support requires tomli-w. Install with 'pip install dynamic-config-manager[toml]'"
            ) from e
        path.write_text(tomli_w.dumps(data), encoding="utf-8")
    else:  # json
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False, default=to_jsonable_python),
            encoding="utf-8",
        )


# --------------------------------------------------------------------------- #
#                          ConfigInstance                                     #
# --------------------------------------------------------------------------- #


class ConfigInstance:
    """
    One *typed* configuration.

    Parameters
    ----------
    persistent : bool, default True
        If False the instance never touches the disk.
    """

    def __init__(
        self,
        *,
        name: str,
        model_cls: Type[T],
        save_path: Path | None,
        auto_save: bool,
        persistent: bool = True,
    ):
        self.name = name
        self._model_cls: Type[T] = model_cls
        self._save_path: Path | None = save_path if persistent else None
        self._auto_save = auto_save and persistent
        self._persistent = persistent

        self._defaults: T = self._model_cls()
        self._active: T = self._load_from_disk() or self._defaults.model_copy(deep=True)

    # ------------ public (value access) -------------------------------- #

    @property
    def active(self) -> _ActiveAccessorProxy[T]:
        return _ActiveAccessorProxy(self)

    @property
    def meta(self) -> _MetaAccessorProxy[T]:
        return _MetaAccessorProxy(self)

    @property
    def default(self) -> _DefaultAccessorProxy[T]:
        return _DefaultAccessorProxy(self)

    @property
    def saved(self) -> _SavedAccessorProxy[T]:
        return _SavedAccessorProxy(self)

    # alias for convenience
    file = saved

    def get_value(self, path: str, default: Any | None = None) -> Any:
        try:
            return _deep_get(self._active, path.split("."))
        except Exception:
            return default

    # aliases for convenience
    get = get_value
    get_active = get_value

    def get_default(self, path: str, default: Any | None = None) -> Any:
        try:
            return _deep_get(self._defaults, path.split("."))
        except Exception:
            return default

    def get_saved(self, path: str, default: Any | None = None) -> Any:
        val = self._get_saved_value(path)
        return default if val is PydanticUndefined else val

    def set_value(self, path: str, value: Any):
        meta = self.get_metadata(path)
        if meta.get("editable") is False:
            raise PermissionError(f"Field '{path}' is not editable.")

        try:
            low = meta.get("ge") if meta.get("ge") is not None else meta.get("gt")
            high = meta.get("le") if meta.get("le") is not None else meta.get("lt")
            if (low is not None or high is not None) and isinstance(value, (int, float)):
                if low is not None and value < low:
                    value = low
                if high is not None and value > high:
                    value = high

            raw = _deep_set_dict(self._active, path.split("."), value)
            self._active = self._model_cls(**raw)
        except ValidationError as e:
            raise ValueError(f"Validation failed setting '{path}':\n{e}") from e

        if self._auto_save:
            self.persist()

    # ------------ metadata -------------------------------------------- #

    def get_metadata(self, path: str, default: Any | None = None) -> Dict[str, Any] | Any:
        try:
            keys = path.split(".")
            cur_model: Union[Type[BaseModel], BaseModel] = self._model_cls
            for idx, k in enumerate(keys):
                if not hasattr(cur_model, "model_fields"):
                    raise KeyError(path)
                field = cur_model.model_fields.get(k)
                if field is None:
                    raise KeyError(k)
                if idx < len(keys) - 1:
                    cur_model = field.annotation

            active_val = _deep_get(self._active, keys)
            default_val = _deep_get(self._defaults, keys)

            meta = {
                "type": field.annotation,
                "required": field.is_required(),
                "default": field.default,
                "description": field.description,
                "editable": (field.json_schema_extra or {}).get("editable", True),
                **_extract_constraints(field),
                "active_value": active_val,
                "default_value": default_val,
            }

            # Include full json_schema_extra content
            if field.json_schema_extra:
                meta["json_schema_extra"] = field.json_schema_extra.copy()
                
                # Flatten common ConfigField attributes for convenience
                common_attrs = ["ui_hint", "ui_extra", "options", "format_spec"]
                for attr in common_attrs:
                    if attr in field.json_schema_extra:
                        meta[attr] = field.json_schema_extra[attr]
                
                # Handle autofix_settings (stored as "autofix" in json_schema_extra)
                if "autofix" in field.json_schema_extra:
                    meta["autofix_settings"] = field.json_schema_extra["autofix"]

            saved_val = PydanticUndefined
            if self._save_path and self._save_path.exists():
                disk = self._load_from_disk()
                if disk is not None:
                    try:
                        saved_val = _deep_get(disk, keys)
                    except Exception:
                        saved_val = PydanticUndefined

            meta["saved_value"] = saved_val
            return meta
        except Exception:
            return default

    # ------------ restore helpers ------------------------------------- #

    def restore_value(self, path: str, source: str = "default"):
        if source == "default":
            new_val = _deep_get(self._defaults, path.split("."))
        elif source == "file":
            disk = self._load_from_disk() or self._defaults
            new_val = _deep_get(disk, path.split("."))
        else:
            raise ValueError("source must be 'default' or 'file'")
        self.set_value(path, new_val)

    def restore_defaults(self):
        self._active = self._defaults.model_copy(deep=True)
        if self._auto_save:
            self.persist()

    # ------------ persistence ----------------------------------------- #

    def persist(self, *, file_format: str | None = None) -> bool:
        if not self._save_path:
            log.debug("Config '%s' is memory‑only; nothing persisted.", self.name)
            return False
        try:
            self._save_path.parent.mkdir(parents=True, exist_ok=True)
            _dump_file(
                self._save_path,
                self._active.model_dump(mode="json"),
                file_format=file_format,
            )
            log.info("Config '%s' saved to %s", self.name, self._save_path)
            return True
        except Exception as exc:
            log.warning("Could not save '%s': %s", self.name, exc, exc_info=True)
            return False

    save = persist  # alias

    def save_as(
        self, path: os.PathLike | str, *, file_format: str | None = None
    ) -> bool:
        path = Path(path).expanduser().resolve()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _dump_file(
                path, self._active.model_dump(mode="json"), file_format=file_format
            )
            log.info("Config '%s' exported to %s", self.name, path)
            return True
        except Exception as exc:
            log.warning("Export failed: %s", exc, exc_info=True)
            return False

    # ------------ internal ------------------------------------------- #

    def _load_from_disk(self) -> T | None:
        if not (self._save_path and self._save_path.exists()):
            return None
        try:
            data = _load_file(self._save_path)
            return self._model_cls(**data)
        except (ValidationError, json.JSONDecodeError, ValueError, TypeError) as e:
            log.warning(
                "Bad data in %s for '%s'; using defaults.  (%s)",
                self._save_path,
                self.name,
                e,
            )
            return None

    def _get_saved_value(self, path: str) -> Any:
        """Return value from the persisted file or ``PydanticUndefined``."""
        keys = path.split(".")
        if self._save_path and self._save_path.exists():
            disk = self._load_from_disk()
            if disk is not None:
                try:
                    return _deep_get(disk, keys)
                except Exception:
                    pass
        return PydanticUndefined


# ---------- util ----------------------------------------------------------- #


def _extract_constraints(field) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for meta in getattr(field, "metadata", ()):
        for attr in (
            "ge",
            "gt",
            "le",
            "lt",
            "min_length",
            "max_length",
            "pattern",
            "multiple_of",
        ):
            if (val := getattr(meta, attr, None)) is not None:
                out[attr] = val
    return out


# --------------------------------------------------------------------------- #
#                           Manager (singleton)                               #
# --------------------------------------------------------------------------- #


class _ConfigManagerInternal:
    """
    Global registry & default‑path resolver.

    * The *initial* default directory is **tempfile.gettempdir()/dynamic_config_manager**.
    * Set ``ConfigManager.default_dir = "/your/project/cfg"`` once early in your app
      to persist every *subsequent* config there (unless it passes its own ``save_path``).
    """

    def __init__(self):
        self._instances: Dict[str, ConfigInstance] = {}
        self._default_dir: Path = Path(tempfile.gettempdir()) / "dynamic_config_manager"
        self._default_dir.mkdir(parents=True, exist_ok=True)

    # ---------- registration ------------------------------------------ #

    def register(
        self,
        name: str,
        model_cls: Type[T],
        *,
        save_path: str | os.PathLike | None = None,
        auto_save: bool = False,
        persistent: bool = True,
    ) -> ConfigInstance:
        if name in self._instances:
            raise ValueError(f"Config '{name}' already registered.")
        if not issubclass(model_cls, BaseSettings):
            raise TypeError("model_cls must subclass pydantic_settings.BaseSettings")

        resolved_path = self._resolve_save_path(name, save_path, persistent)
        inst = ConfigInstance(
            name=name,
            model_cls=model_cls,
            save_path=resolved_path,
            auto_save=auto_save,
            persistent=persistent,
        )
        self._instances[name] = inst
        return inst

    # ---------- default dir ------------------------------------------- #

    @property
    def default_dir(self) -> Path:
        return self._default_dir

    @default_dir.setter
    def default_dir(self, path: str | os.PathLike | None):
        if path is None:
            self._default_dir = Path(tempfile.mkdtemp(prefix="dyn_cfg_mgr_"))
        else:
            self._default_dir = Path(path).expanduser().resolve()
            self._default_dir.mkdir(parents=True, exist_ok=True)

    # ---------- convenience ------------------------------------------- #

    def __getitem__(self, name: str) -> ConfigInstance:
        return self._instances[name]

    def __iter__(self):
        return iter(self._instances.values())

    def save_all(self):
        for inst in self._instances.values():
            inst.persist()

    def restore_all_defaults(self):
        for inst in self._instances.values():
            inst.restore_defaults()

    def update_model_field(
        self,
        config_name: str,
        field_path: str,
        new_field_definition: "FieldInfo",
    ) -> bool:
        """Dynamically update a field definition on a registered model."""

        from pydantic import create_model
        from pydantic.fields import FieldInfo

        inst = self._instances[config_name]
        parts = field_path.split(".")

        def _rebuild(model_cls: Type[BaseModel], keys: List[str]) -> Type[BaseModel]:
            name = keys[0]
            field = model_cls.model_fields[name]
            if len(keys) == 1:
                fields = {
                    n: (f.annotation, new_field_definition if n == name else f)
                    for n, f in model_cls.model_fields.items()
                }
                New = create_model(model_cls.__name__, __base__=model_cls.__bases__[0], **fields)
                New.model_rebuild(force=True)
                return New
            else:
                nested = _rebuild(field.annotation, keys[1:])
                fields = {
                    n: (
                        nested if n == name else f.annotation,
                        f,
                    )
                    for n, f in model_cls.model_fields.items()
                }
                New = create_model(model_cls.__name__, __base__=model_cls.__bases__[0], **fields)
                New.model_rebuild(force=True)
                return New

        candidate_cls = _rebuild(inst._model_cls, parts)

        try:
            new_active = candidate_cls(**inst._active.model_dump(mode="python"))
        except ValidationError as exc:
            log.error("Model update failed: %s", exc)
            return False

        inst._model_cls = candidate_cls
        inst._active = new_active
        inst._defaults = candidate_cls()
        return True

    # ---------- helpers ----------------------------------------------- #

    def _resolve_save_path(
        self, name: str, save_path: str | os.PathLike | None, persistent: bool
    ) -> Path | None:
        if not persistent:
            return None
        if save_path is None:
            return self._default_dir / f"{name}.json"
        p = Path(save_path).expanduser()
        return p if p.is_absolute() else self._default_dir / p


# --------------------------------------------------------------------------- #
#                                public handle                                #
# --------------------------------------------------------------------------- #

ConfigManager: _ConfigManagerInternal = _ConfigManagerInternal()
