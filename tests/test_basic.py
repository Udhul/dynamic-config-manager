import json
from dynamic_config_manager import (
    ConfigManager,
    DynamicBaseSettings,
    ConfigField,
)


class SimpleCfg(DynamicBaseSettings):
    foo: int = ConfigField(1)
    bar: str = ConfigField("x")


def setup_function(_):
    ConfigManager._instances.clear()


def test_attribute_access_and_persist(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("simple", SimpleCfg, auto_save=True)

    inst.active.foo = 5
    assert inst.active.foo == 5
    inst.active.bar = "hello"
    assert inst.get_value("bar") == "hello"

    path = tmp_path / "simple.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["foo"] == 5
    assert data["bar"] == "hello"

    meta = inst.meta.foo
    assert meta["default"] == 1


def test_metadata_and_restore(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("simple", SimpleCfg)

    inst.set_value("foo", 5)
    inst.persist()
    inst.set_value("foo", 7)

    meta = inst.meta.foo
    assert meta["active_value"] == 7
    assert meta["default_value"] == 1
    assert meta["saved_value"] == 5

    inst.restore_value("foo", source="file")
    assert inst.get_value("foo") == 5


def test_update_model_field(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("simple", SimpleCfg)
    inst.set_value("foo", 5)

    ConfigManager.update_model_field(
        "simple", "foo", ConfigField(2, ge=0, le=10)
    )

    meta = inst.meta.foo
    assert meta["default"] == 2
    assert meta["le"] == 10
    assert inst.get_value("foo") == 5


def test_restore_defaults_autosave(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("simple", SimpleCfg, auto_save=True)
    inst.active.foo = 5
    path = tmp_path / "simple.json"
    assert json.loads(path.read_text())["foo"] == 5

    inst.restore_defaults()
    assert inst.active.foo == 1
    assert json.loads(path.read_text())["foo"] == 1
