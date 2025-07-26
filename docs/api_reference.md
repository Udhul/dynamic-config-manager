# Dynamic Config Manager – API Reference

All symbols below can be imported from `dynamic_config_manager` after installing the package.

## Module Contents

- `ConfigManager` – singleton managing all registered configuration instances.
- `DynamicBaseSettings` – convenience base class for models.
- `ConfigField()` – helper building `pydantic.Field` with extra metadata.
- `attach_auto_fix()` – decorator adding automatic value fixing.
- Policy enums (`NumericPolicy`, `OptionsPolicy`, `RangePolicy`, `MultipleChoicePolicy`,
  `ListConversionPolicy`, `BooleanPolicy`, `DatetimePolicy`, `PathPolicy`,
  `MultipleRangesPolicy`, `FixStatusEnum`).
- `watch_and_reload()` – background file watcher.
- Command line script `dcm-cli`.
- `__version__` – package version string.

## ConfigManager

`ConfigManager` is a global instance of `_ConfigManagerInternal` used to register
and access configurations.

### Attribute

- `default_dir: Path` – directory used when saving configurations without an
  explicit `save_path`.

### Methods

- `register(name, model_cls, *, save_path=None, auto_save=False, persistent=True) -> ConfigInstance`
  Register `model_cls` under `name`. When `persistent` is `True` the instance
  loads and saves a file located at `save_path` or `<default_dir>/<name>.json`.
- `save_all()` – call `persist()` on every registered persistent instance.
- `restore_all_defaults()` – reset all instances to their default values.
- `update_model_field(config_name, field_path, new_field_definition) -> bool`
  Replace a `Field` definition at `field_path` for the given configuration. The
  current values are revalidated; returns `False` if validation fails.
- `__getitem__(name) -> ConfigInstance` – access a registered configuration.
- `__iter__()` – iterate over `ConfigInstance` objects.

## ConfigInstance

Represents one configuration model and its lifecycle.

### Properties

- `active` – attribute-style access to the current values. Writing triggers
  validation and optional auto-save.
- `default` – read-only access to the model default values.
- `saved` – read-only access to the values loaded from disk (alias: `file`).
- `meta` – attribute-style access returning metadata dictionaries.

### Methods

- `get_value(path)` / `set_value(path, value)` – dotted path access.
- `persist(file_format=None) -> bool` – write the current values to disk;
  returns `True` on success. Alias: `save`.
- `save_as(path, *, file_format=None) -> bool` – export the configuration to
  the given path without changing `save_path`.
- `restore_value(path, source="default"|"file")` – restore one value from the
  defaults or from the saved file.
- `restore_defaults()` – replace the active state with defaults and optionally
  save if `auto_save` was enabled.
- `get_metadata(path)` – return a dictionary describing the field at `path`
  including constraints and the active, default and saved values.

## Base Classes and Helpers

`DynamicBaseSettings` can be used as the base class for models. `ConfigField`
wraps `pydantic.Field` and attaches keys such as `ui_hint`, `options`,
`autofix` settings and `format_spec` used by the framework.

## Validation Helpers

`attach_auto_fix()` adds a model validator which processes incoming values
before/after Pydantic validation. Important keyword arguments:

- `mode="before" | "after"` – when the validator runs relative to Pydantic validation.
- `numeric_policy` – how numeric values outside their bounds are handled.
- `options_policy` – behaviour when a string is not in allowed `options`.
- `range_policy` – handling of two-value ranges.
- `multiple_choice_policy` – handling lists of choices.
- `list_conversion_policy` – behaviour of the list conversion format.
- `boolean_policy`, `datetime_policy`, `path_policy`, `multiple_ranges_policy` –
  specialised policies for their respective formats.
- `eval_expressions` – allow arithmetic expression strings for numeric fields.

### Policy Enums

- `NumericPolicy`: `CLAMP`, `REJECT`, `BYPASS`.
- `OptionsPolicy`: `NEAREST`, `REJECT`, `BYPASS`.
- `RangePolicy`: `CLAMP_ITEMS`, `REJECT`, `REJECT_IF_INVALID_STRUCTURE`,
  `SWAP_IF_REVERSED`, `BYPASS`.
- `MultipleChoicePolicy`: `REMOVE_INVALID`, `REJECT_IF_ANY_INVALID`,
  `REJECT_IF_COUNT_INVALID`, `BYPASS`.
- `ListConversionPolicy`: `CONVERT_OR_REJECT`, `CONVERT_BEST_EFFORT`, `BYPASS`.
- `BooleanPolicy`: `BINARY`, `STRICT`, `BYPASS`.
- `DatetimePolicy`: `PARSE`, `BYPASS`.
- `PathPolicy`: `RESOLVE`, `BYPASS`.
- `MultipleRangesPolicy`: `REJECT`, `BYPASS`.
- `FixStatusEnum`: statuses returned by internal fixers (`PROCESSED_MODIFIED`,
  `PROCESSED_UNMODIFIED`, `BYPASSED`, `REJECTED_BY_POLICY`,
  `FAILED_PREPROCESSING`).

### Format Specifications

The `format_spec` dictionary on a field controls specialised pre-processing.
Supported `type` values include:

- **range** – parse and clamp two numeric values. Options include
  `item_type`, `min_item_value`, `max_item_value`, `input_separator` and others.
- **multiple_choice** – list of allowed selections with limits on counts.
- **list_conversion** – convert strings or mixed lists into a typed list with
  item-level constraints.
- **datetime_string** – parse strings into `datetime`, `date` or `time` objects.
- **boolean_flexible** – parse yes/no or numeric values into booleans.
- **path_string** – normalise path strings with existence and type checks.
- **multiple_ranges** – list of range tuples with aggregate constraints.

See `developer_spec.md` Appendix B for the precise options of each type.

## File Watching

`watch_and_reload(names=None, *, debounce=500) -> (Thread, Event)`

Start a daemon thread that monitors configuration files for changes. When a
watched file is written or replaced it is reloaded in memory. The returned event
can be set to stop the watcher thread.

## Command Line Interface

The package installs the `dcm-cli` tool.

```
$ dcm-cli show FILE          # print configuration file
$ dcm-cli set FILE KEY VALUE # update a dotted path in the file
```

