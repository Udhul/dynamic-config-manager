# Dynamic Config Manager

A singleton manager for handling multiple, strongly-typed configuration sets using [Pydantic](https://docs.pydantic.dev/) and [Pydantic-Settings](https://docs.pydantic.dev/latest/).

## Features

* **Singleton Access** via `ConfigManager`
* **Type Safety & Validation** using Pydantic models
* **Automatic Persistence** to JSON/YAML/TOML
* **Metadata** extraction to power UIs

## Installation

```bash
pip install dynamic-config-manager
# optional file format extras
pip install dynamic-config-manager[yaml,toml]
```

## Quick CLI Example

```bash
dcm-cli show config.json
# update a value
dcm-cli set config.json ui.theme dark
```

## Quick Start

Define your configuration using Pydantic models, register it with the manager and access values safely:

```python
from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField

class UIConfig(DynamicBaseSettings):
    theme: str = ConfigField("light", options=["light", "dark"])

cfg = ConfigManager.register("ui", UIConfig, auto_save=True)
cfg.active.theme = "dark"  # validated and persisted
```

## API Reference

See [developer_spec.md](developer_spec.md) for a detailed specification of all available helpers and manager features.

## Watching for Changes

```python
from dynamic_config_manager import watch_and_reload

thread, stop = watch_and_reload(["ui"], debounce=100)
# ... make changes to ui.json from another process ...
stop.set()  # stop watching
```

