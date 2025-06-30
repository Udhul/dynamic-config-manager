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
