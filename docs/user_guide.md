# Dynamic Config Manager – User Guide

This guide explains how to install and use **Dynamic Config Manager** to manage application settings.

## Installation

```bash
pip install dynamic-config-manager
# Install optional YAML, TOML and watching extras
pip install dynamic-config-manager[all]
```

## Defining Configuration Models

Create Pydantic models for your settings. Use `DynamicBaseSettings` together with
`ConfigField` to attach metadata and validation hints.

```python
from dynamic_config_manager import DynamicBaseSettings, ConfigField

class UIConfig(DynamicBaseSettings):
    theme: str = ConfigField("light", options=["light", "dark"])
    font_size: int = ConfigField(12, ge=8, le=32)
```

`ConfigField` wraps `pydantic.Field` and accepts extras such as `options`,
`ui_hint`, `autofix_settings` and `format_spec`.

## Registering a Configuration

Use `ConfigManager.register` to register your model and optionally enable persistence.

```python
from dynamic_config_manager import ConfigManager

cfg = ConfigManager.register(
    "ui", UIConfig, auto_save=True, persistent=True
)
```

- **name** – unique identifier.
- **auto_save** – automatically save after `set_value` or attribute writes.
- **persistent** – if `False`, keep the configuration in memory only.
- **save_path** – custom file location; defaults to `<default_dir>/<name>.json`.

Adjust the global `ConfigManager.default_dir` once early in your application to control where files are written.

## Accessing Values

Values can be accessed by path or attribute. Attribute access works for nested models too.

```python
cfg.active.theme = "dark"       # validated and saved
print(cfg.active.font_size)     # 12

cfg.set_value("font_size", 16)
print(cfg.get_value("font_size"))
```

`cfg.meta` provides metadata describing each field.

```python
info = cfg.meta.theme
print(info["options"])          # ["light", "dark"]
```

## Persistence Helpers

Call `persist()` to write the current values to disk or `save_as()` to export using a chosen format.

```python
cfg.persist()                   # saves as JSON by default
cfg.save_as("ui.yaml", file_format="yaml")
```

Use `restore_value()` or `restore_defaults()` to revert values.

```python
cfg.restore_value("theme", source="file")
cfg.restore_defaults()
```

`ConfigManager.save_all()` and `ConfigManager.restore_all_defaults()` operate on every registered configuration.

## Watching for File Changes

`watch_and_reload` starts a daemon thread that reloads configurations when their backing files are modified.

```python
from dynamic_config_manager import watch_and_reload

thread, stop = watch_and_reload(["ui"], debounce=200)
# ... edit ui.json from another process ...
stop.set()
thread.join()
```

## Command Line Interface

After installation the `dcm-cli` tool can inspect or update configuration files.

```bash
# Display a configuration file
$ dcm-cli show ui.json

# Change a value
$ dcm-cli set ui.json theme dark
```

## Auto‑Fix System

Applying `attach_auto_fix` to a model enables automatic formatting and coercion of inputs before validation.

```python
from dynamic_config_manager import attach_auto_fix

@attach_auto_fix(eval_expressions=True)
class MachineCfg(DynamicBaseSettings):
    speed: int = ConfigField(1000, ge=500, le=2000)
```

Setting `speed` to the string `"10*2"` will evaluate the expression and clamp it
according to the policies. Policies for numerics, options, ranges and more can
be controlled globally when decorating the class or per field through
`autofix_settings`.

## Runtime Model Updates

`ConfigManager.update_model_field` allows updating field definitions at runtime.

```python
from dynamic_config_manager import ConfigField

ConfigManager.update_model_field(
    "ui", "font_size", ConfigField(14, ge=10, le=40)
)
```

The configuration instance is revalidated with the new model so updates are applied immediately.

## Example Workflow

```python
from dynamic_config_manager import (
    ConfigManager, DynamicBaseSettings, ConfigField, watch_and_reload
)

class AppCfg(DynamicBaseSettings):
    theme: str = ConfigField("light", options=["light", "dark"])
    refresh: int = ConfigField(60, ge=15, le=600)

ConfigManager.default_dir = "~/myapp/cfg"
app_cfg = ConfigManager.register("app", AppCfg, auto_save=True)

# Start watching for edits on disk
thread, stop = watch_and_reload(["app"])

# Use configuration safely throughout the app
print(app_cfg.active.theme)
app_cfg.active.refresh = 120

# Shut down watcher before exit
stop.set()
thread.join()
```

This covers the typical lifecycle: model definition, registration, live updates,
persistence and watching for external changes.
