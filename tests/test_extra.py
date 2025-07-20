import json
import os
import time
from pathlib import Path

import pytest
import tomli
import yaml

from dynamic_config_manager import (
    ConfigManager,
    DynamicBaseSettings,
    ConfigField,
    attach_auto_fix,
    watch_and_reload,
)
from dynamic_config_manager.manager import _deep_get, _deep_set


class ListCfg(DynamicBaseSettings):
    items: list[int] = ConfigField([1, 2])


class ProtectCfg(DynamicBaseSettings):
    secret: int = ConfigField(1, json_schema_extra={"editable": False})


@attach_auto_fix(eval_expressions=True)
class AutoFixCfg(DynamicBaseSettings):
    val: int = ConfigField(0, ge=0, le=10)


def setup_function(_):
    ConfigManager._instances.clear()


def test_deep_helpers_on_list():
    model = ListCfg()
    updated = _deep_set(model, ["items", "1"], 5)
    assert _deep_get(updated, ["items", "1"]) == 5


def test_list_index_and_save_as(tmp_path: Path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("list", ListCfg, auto_save=True)

    inst._active = _deep_set(inst._active, ["items", "2"], 9)
    assert _deep_get(inst._active, ["items", "2"]) == 9
    assert inst._active.items == [1, 2, 9]

    yaml_path = tmp_path / "out.yaml"
    toml_path = tmp_path / "out.toml"
    assert inst.save_as(yaml_path, file_format="yaml")
    assert inst.save_as(toml_path, file_format="toml")
    assert yaml.safe_load(yaml_path.read_text())["items"] == [1, 2, 9]
    assert tomli.loads(toml_path.read_text())["items"] == [1, 2, 9]


def test_permission_error(tmp_path: Path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("prot", ProtectCfg)
    with pytest.raises(PermissionError):
        inst.set_value("secret", 5)


def test_non_persistent(tmp_path: Path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("mem", ListCfg, persistent=False)
    inst.set_value("items", [5])
    assert not inst.persist()
    assert not any(tmp_path.iterdir())


def test_save_restore_all(tmp_path: Path):
    ConfigManager.default_dir = tmp_path
    a = ConfigManager.register("a", ListCfg, auto_save=True)
    b = ConfigManager.register("b", ProtectCfg, auto_save=True)

    a.set_value("items", [3])
    b._active = ProtectCfg(secret=2)
    ConfigManager.save_all()
    for f in (tmp_path / "a.json", tmp_path / "b.json"):
        assert f.exists()

    a.set_value("items", [4])
    ConfigManager.restore_all_defaults()
    assert a.active.items[0] == 1


def test_watch_and_reload_autofix(tmp_path: Path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("auto", AutoFixCfg, auto_save=True)
    inst.persist()

    path = tmp_path / "auto.json"
    thread, stop = watch_and_reload(["auto"], debounce=100)
    data = json.loads(path.read_text())
    data["val"] = "5*2"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    time.sleep(1)
    stop.set()
    thread.join(timeout=1)

    assert inst.active.val == 10
