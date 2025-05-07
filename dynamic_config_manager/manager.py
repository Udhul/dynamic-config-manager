# =============================================================
#  dynamic_config_manager/manager.py
# =============================================================
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError
from pydantic.json import pydantic_encoder
from pydantic_settings import BaseSettings

__all__ = ["ConfigManager"]

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseSettings)

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
    if not keys:
        return value
    head, *tail = keys

    if isinstance(data, BaseModel):
        copied = data.model_dump(mode="python")
        copied[head] = _deep_set(copied[head], tail, value)
        return data.__class__(**copied)

    if isinstance(data, dict):
        copied = {**data}
        copied[head] = _deep_set(copied[head], tail, value)
        return copied

    if isinstance(data, list):
        idx = int(head)
        copied = list(data)
        copied[idx] = _deep_set(copied[idx], tail, value)
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
        import yaml
        return yaml.safe_load(text) or {}
    if fmt == "toml":
        import tomli
        return tomli.loads(text)
    return json.loads(text)


def _dump_file(path: Path, data: Dict[str, Any], *, file_format: Optional[str] = None):
    fmt = (file_format or _detect_format(path)).lower()
    if fmt == "yaml":
        import yaml
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    elif fmt == "toml":
        import tomli_w
        path.write_text(tomli_w.dumps(data), encoding="utf-8")
    else:  # json
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False, default=pydantic_encoder),
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
    def active(self) -> T:
        return self._active

    def get_value(self, path: str) -> Any:
        return _deep_get(self._active, path.split("/"))

    def set_value(self, path: str, value: Any):
        meta = self.get_metadata(path)
        if meta.get("editable") is False:
            raise PermissionError(f"Field '{path}' is not editable.")

        try:
            new_inst = _deep_set(self._active, path.split("/"), value)
            self._active = self._model_cls(**new_inst.model_dump(mode="python"))
        except ValidationError as e:
            raise ValueError(f"Validation failed setting '{path}':\n{e}") from e

        if self._auto_save:
            self.persist()

    # ------------ metadata -------------------------------------------- #

    def get_metadata(self, path: str) -> Dict[str, Any]:
        keys = path.split("/")
        cur: Union[Type[BaseModel], BaseModel] = self._model_cls
        for k in keys:
            if not hasattr(cur, "model_fields"):
                raise KeyError(f"'{path}' is not a model field.")
            field = cur.model_fields[k]
            cur = field.annotation

        extra = dict(field.json_schema_extra or {})
        extra.update(
            {
                "type": field.annotation,
                "required": field.is_required(),
                "default": field.default,
                "editable": extra.get("editable", True),
                **_extract_constraints(field),
            }
        )
        return extra

    # ------------ restore helpers ------------------------------------- #

    def restore_value(self, path: str, source: str = "default"):
        if source == "default":
            new_val = _deep_get(self._defaults, path.split("/"))
        elif source == "file":
            disk = self._load_from_disk() or self._defaults
            new_val = _deep_get(disk, path.split("/"))
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

    def save_as(self, path: os.PathLike | str, *, file_format: str | None = None) -> bool:
        path = Path(path).expanduser().resolve()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _dump_file(path, self._active.model_dump(mode="json"), file_format=file_format)
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
