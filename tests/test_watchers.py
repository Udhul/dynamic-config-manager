import json
import time
from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField, watch_and_reload

class SimpleCfg(DynamicBaseSettings):
    foo: int = ConfigField(1)


def setup_function(_):
    ConfigManager._instances.clear()


def test_watch_and_reload(tmp_path):
    ConfigManager.default_dir = tmp_path
    inst = ConfigManager.register("simple", SimpleCfg, auto_save=True)
    inst.persist()
    thread, stop = watch_and_reload(["simple"], debounce=100)

    path = tmp_path / "simple.json"
    data = json.loads(path.read_text())
    data["foo"] = 9
    path.write_text(json.dumps(data))

    time.sleep(0.3)
    stop.set()
    thread.join(timeout=1)

    assert inst.active.foo == 9
