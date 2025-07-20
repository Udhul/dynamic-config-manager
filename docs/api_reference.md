# Dynamic Config Manager – API Reference

This document summarises the public API of the package. All names are available
from `dynamic_config_manager` after installation.

## ConfigManager

`ConfigManager` is a singleton managing all configurations.

### Attributes

- `default_dir: Path` – directory used when saving configurations without an explicit path.

### Methods

- `register(name, model_cls, *, save_path=None, auto_save=False, persistent=True) -> ConfigInstance`
  Register a configuration model. Returns a `ConfigInstance` for interacting with the configuration.
- `save_all()` – persist all registered configurations.
- `restore_all_defaults()` – restore defaults for all configurations.
- `update_model_field(config_name, field_path, new_field_definition) -> bool`
  Replace a field definition on a registered model at runtime.
- `__getitem__(name) -> ConfigInstance` – access a configuration by name.
- `__iter__()` – iterate over registered `ConfigInstance` objects.

## ConfigInstance

An object wrapping a single Pydantic model instance.

### Properties

- `active` – attribute proxy for reading or writing current values.
- `meta` – attribute proxy returning metadata dictionaries for fields.

### Methods

- `get_value(path)` / `set_value(path, value)` – path based access using `.` as a separator.
- `persist(file_format=None)` – write the configuration to disk. Returns `True` on success.
- `save_as(path, *, file_format=None)` – export configuration to a specific file.
- `restore_value(path, source="default"|"file")` – restore an individual value.
- `restore_defaults()` – replace the active state with defaults and optionally persist.
- `get_metadata(path)` – return metadata describing a field including constraints and active/default/saved values.

## Base Classes and Helpers

- `DynamicBaseSettings` – optional base class for configuration models.
- `ConfigField` – convenience wrapper around `pydantic.Field` adding `json_schema_extra` keys used by the framework.

## Validation Helpers

The decorator `attach_auto_fix` enables preprocessing of inputs according to
policies. It accepts optional keyword arguments such as `mode`,
`numeric_policy`, `options_policy`, `range_policy`, `list_conversion_policy` and
others.

Enum classes exported for policy configuration:

- `NumericPolicy`
- `OptionsPolicy`
- `RangePolicy`
- `MultipleChoicePolicy`
- `ListConversionPolicy`
- `FixStatusEnum`
- `BooleanPolicy`
- `DatetimePolicy`
- `PathPolicy`
- `MultipleRangesPolicy`

See `docs/developer_spec.md` for a detailed description of each policy and fixer behaviour.

## File Watching

`watch_and_reload(names=None, *, debounce=500) -> (Thread, Event)`

Start a daemon thread that monitors configuration files for changes. When a
watched file is modified it is reloaded in memory. The returned event can be set
to stop the watcher.

## Command Line Interface

The package installs the `dcm-cli` script providing simple file based operations:

- `dcm-cli show FILE` – print the contents of a configuration file.
- `dcm-cli set FILE KEY VALUE` – update a value in the file at the given dotted path.

