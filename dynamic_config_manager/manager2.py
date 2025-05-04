# =============================================================
#  dynamic_config_manager/manager.py
# =============================================================
from __future__ import annotations

import json
import yaml
import os
import tempfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ValidationError, VersionError
from pydantic.json import pydantic_encoder
from pydantic_settings import BaseSettings

__all__ = ["ConfigManager"]

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseSettings)

# --------------------------------------------------------------------------- #
#                           _helpers                                          #
# --------------------------------------------------------------------------- #


def _deep_get(data: Any, keys: List[str]) -> Any:
    """Traverse model / dict / list using a key list."""
    cur = data
    for key in keys:
        if isinstance(cur, BaseModel):
            cur = getattr(cur, key)
        elif isinstance(cur, dict):
            cur = cur[key]
        elif isinstance(cur, list):
            cur = cur[int(key)]
        else:
            raise KeyError(f"Cannot traverse into {type(cur)} with key '{key}'.")
    return cur


def _deep_set(data: Any, keys: List[str], value: Any) -> Any:
    """Return a *new* structure with `value` assigned at path `keys`."""
    if not keys:
        return value
    head, *tail = keys
    if isinstance(data, BaseModel):
        data_dict = data.model_dump(mode="python")
        data_dict[head] = _deep_set(data_dict[head], tail, value)
        return data.__class__(**data_dict)  # re-validate sub-tree
    if isinstance(data, dict):
        data = data.copy()
        data[head] = _deep_set(data[head], tail, value)
        return data
    if isinstance(data, list):
        idx = int(head)
        data = data.copy()
        data[idx] = _deep_set(data[idx], tail, value)
        return data
    raise KeyError(f"Cannot traverse into {type(data)} with key '{head}'.")


def _guess_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".yml", ".yaml"}:
        return "yaml"
    if ext == ".toml":
        return "toml"
    return "json"


def _load_file(path: Path, *, fmt: str | None = None) -> Dict[str, Any]:
    fmt = fmt or _guess_format(path)
    if fmt == "yaml" or fmt == "yml":
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if fmt == "toml":
        import tomllib  # stdlib ≥3.11
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))  # json


def _dump_file(path: Path, data: Dict[str, Any], *, fmt: str | None = None) -> None:
    fmt = fmt or _guess_format(path)
    if fmt == "yaml" or fmt == "yml":
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    elif fmt == "toml":
        import tomli_w
        path.write_text(tomli_w.dumps(data), encoding="utf-8")
    else:  # json (default)
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False, default=pydantic_encoder),
            encoding="utf-8",
        )


# --------------------------------------------------------------------------- #
#                           ConfigInstance                                    #
# --------------------------------------------------------------------------- #


class ConfigInstance:
    """A single *typed* configuration set."""

    def __init__(
        self,
        *,
        name: str,
        model_cls: Type[T],
        save_path: Optional[Path],
        auto_save: bool,
    ) -> None:
        self.name = name
        self._model_cls: Type[T] = model_cls
        self._save_path: Optional[Path] = save_path
        self._auto_save: bool = auto_save

        # cache
        self._defaults: T = self._model_cls()  # from code
        self._active: T = self._load_or_defaults()

    # ------------------------------------------------------------------ #
    #   public surface                                                   #
    # ------------------------------------------------------------------ #

    # read-only property – users should *not* mutate returned object
    @property
    def active(self) -> T:  # noqa: D401
        """Return the current **validated** settings instance."""
        return self._active

    # ----- path API ---------------------------------------------------- #

    def get_value(self, path: str) -> Any:
        """``cfg.get_value('database/host')``"""
        keys = path.split("/")
        return _deep_get(self._active, keys)

    def set_value(self, path: str, value: Any) -> None:
        """Set value → re-validate whole tree → (optional) auto-save."""
        keys = path.split("/")
        try:
            new_instance = _deep_set(self._active, keys, value)
            # editability check (metadata)
            meta = self.get_metadata(path)
            if meta.get("editable") is False:
                raise PermissionError(f"Field '{path}' is marked editable=False.")
            self._active = self._model_cls(**new_instance.model_dump(mode="python"))
        except ValidationError as e:
            raise ValueError(f"Validation error while setting '{path}':\n{e}") from e

        if self._auto_save:
            self.save()

    def restore_value(self, path: str, source: str = "default") -> None:
        """source = 'default' | 'file'"""
        if source == "default":
            val = _deep_get(self._defaults, path.split("/"))
        elif source == "file":
            on_disk = self._load_or_defaults()   # reload once
            val = _deep_get(on_disk, path.split("/"))
        else:
            raise ValueError("source must be 'default' or 'file'")
        self.set_value(path, val)

    # ----- metadata ---------------------------------------------------- #

    def get_metadata(self, path: str) -> Dict[str, Any]:
        """Return consolidated metadata for the field at *path*."""
        keys = path.split("/")
        cur_model: Union[Type[BaseModel], BaseModel] = self._model_cls
        for key in keys:
            if not hasattr(cur_model, "model_fields"):
                raise KeyError(f"Path '{path}' is not a Pydantic model field.")
            field = cur_model.model_fields[key]
            cur_model = field.annotation
        md = field.json_schema_extra or {}
        md.update(
            {
                "type": field.annotation,
                "required": field.is_required(),
                "default": field.default,
                "editable": md.get("editable", True),
                **_extract_constraints(field),
            }
        )
        return md

    # ----- persistence ------------------------------------------------- #

    def save(self) -> bool:
        if not self._save_path:
            log.debug("No save path - nothing persisted.")
            return False
        try:
            self._save_path.parent.mkdir(parents=True, exist_ok=True)
            _dump_file(self._save_path, self._active.model_dump(mode="json"))
            log.info("Config '%s' saved to %s", self.name, self._save_path)
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("Could not save config '%s': %s", self.name, exc, exc_info=True)
            return False

    def restore_defaults(self) -> None:
        self._active = self._defaults.model_copy(deep=True)
        if self._auto_save:
            self.save()

    # ------------------------------------------------------------------ #
    #   internal helpers                                                 #
    # ------------------------------------------------------------------ #

    def _load_or_defaults(self) -> T:
        if self._save_path and self._save_path.exists():
            try:
                data = _load_file(self._save_path)
                return self._model_cls(**data)
            except (ValidationError, ValueError, TypeError) as e:
                log.warning(
                    "Invalid data in %s for '%s' - falling back to defaults.\n%s",
                    self._save_path,
                    self.name,
                    e,
                )
        else:
            if self._save_path:
                # bootstrap file with defaults
                self.save(self._defaults)
        return self._defaults.model_copy(deep=True)

    # allow manual save of arbitrary object (bootstrapping)
    def save(self, obj: Optional[T] = None) -> bool:  # type: ignore[override]
        self._active = obj or self._active
        return self.save()


def _extract_constraints(field) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for meta in getattr(field, "metadata", ()):
        for attr in ("ge", "gt", "le", "lt", "min_length", "max_length", "pattern"):
            if getattr(meta, attr, None) is not None:
                out[attr] = getattr(meta, attr)
    return out


# --------------------------------------------------------------------------- #
#                           Manager (singleton)                               #
# --------------------------------------------------------------------------- #


class _ConfigManagerInternal:
    """The one & only manager instance."""

    def __init__(self) -> None:
        self._instances: Dict[str, ConfigInstance] = {}
        # ~/.cache/<app> if possible, else tmp
        self._default_dir: Path = Path(
            os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
        ).joinpath("dynamic_config_manager")
        self._default_dir.mkdir(parents=True, exist_ok=True)

    # ------------- registration ---------------------------------------- #

    def register(
        self,
        name: str,
        model_cls: Type[T],
        *,
        save_path: str | os.PathLike | None = None,
        auto_save: bool = False,
    ) -> ConfigInstance:
        """Create & register a **ConfigInstance**.

        * If *save_path* is relative it is placed below the manager's
          ``default_dir``.  ``None`` disables persistence.
        * Raises ``ValueError`` on duplicates or invalid model types.
        """
        if name in self._instances:
            raise ValueError(f"Config '{name}' is already registered.")
        if not issubclass(model_cls, BaseSettings):
            raise TypeError("model_cls must subclass pydantic_settings.BaseSettings")

        save_path = (
            None
            if save_path is None
            else Path(save_path)
            if os.path.isabs(str(save_path))
            else self._default_dir / save_path
        )
        instance = ConfigInstance(
            name=name,
            model_cls=model_cls,
            save_path=save_path,
            auto_save=auto_save,
        )
        self._instances[name] = instance
        return instance

    # ------------- access helpers -------------------------------------- #

    def get(self, name: str) -> ConfigInstance:
        return self._instances[name]

    __getitem__ = get  # cfg = ConfigManager['app']

    # ------------- book-keeping ---------------------------------------- #

    @property
    def default_dir(self) -> Path:  # read-write
        return self._default_dir

    @default_dir.setter
    def default_dir(self, path: str | os.PathLike) -> None:
        self._default_dir = Path(path).expanduser().resolve()
        self._default_dir.mkdir(parents=True, exist_ok=True)

    # ------------- convenience ----------------------------------------- #

    def save_all(self) -> None:
        for inst in self._instances.values():
            inst.save()

    def restore_all_defaults(self) -> None:
        for inst in self._instances.values():
            inst.restore_defaults()

    # ------------- dunder sugar ---------------------------------------- #

    def __iter__(self):
        return iter(self._instances.values())

    def __len__(self) -> int:
        return len(self._instances)

    def __contains__(self, item: str) -> bool:
        return item in self._instances


# --------------------------------------------------------------------------- #
#                                public handle                                #
# --------------------------------------------------------------------------- #

ConfigManager: _ConfigManagerInternal = _ConfigManagerInternal()
