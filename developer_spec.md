# Dynamic Config Manager - Developer Specification

## 1. Introduction

### 1.1. Project Goal
To create a Python package, `dynamic-config-manager`, providing a robust, typed, and file-backed configuration framework. It wraps Pydantic (v2) `BaseSettings` to offer dynamic loading, updating, saving, validation, and management of application configurations, with advanced pre-processing capabilities.

### 1.2. Core Philosophy
*   **Pydantic-centric:** Leverage Pydantic V2 for model definition, type checking, and core validation.
*   **Typed:** Emphasize strong typing for configuration clarity and safety.
*   **User-friendly:** Simple API for common tasks, with powerful customization options.
*   **Explicit over Implicit:** Clear control over persistence, saving, and validation behaviors.
*   **Separation of Concerns:** Auto-fix pre-processes data; Pydantic performs final validation.

### 1.3. Key Features Summary
*   Configuration definition via Pydantic `BaseSettings` models.
*   Singleton `ConfigManager` for centralized management of multiple configurations.
*   Default save directory management with per-config overrides.
*   Opt-in/out persistence for configurations (memory-only or file-backed).
*   Support for JSON (default), YAML, and TOML file formats.
*   Path-based deep access for getting and setting nested configuration values.
*   Automatic validation and (optional) auto-saving on value changes.
*   Restore functionality for individual values or entire configurations to defaults or file-persisted state.
*   `attach_auto_fix` decorator for Pydantic models to enable input pre-processing:
    *   Numeric clamping/rejection based on `ge/gt/le/lt`.
    *   `multiple_of` enforcement (rounding or rejection).
    *   String snapping to nearest option for fields with predefined choices.
    *   `min_length`/`max_length` enforcement (rejection).
    *   Methods to try fitting other field formats, such as range(s), multiple choice, a combination of format requirements.
    *   Safe evaluation of mathematical string expressions for numeric fields.
    *   Configurable policies (`CLAMP`, `NEAREST`, `REJECT`, `BYPASS`) for numeric and options fixing, configurable globally or per-field.
*   Access to Pydantic field metadata, including constraints and `json_schema_extra` for UI hints.

## 2. System Architecture

### 2.1. Overview Diagram
```
+-------------------+      Registers     +-------------------+
|  User Application | -----------------> |   ConfigManager   |
|                   | <----------------- |    (Singleton)    |
| - Defines Models  |   Access Configs   +-------------------+
| - Uses Configs    |                            | Manages
+-------------------+                            |
         | Uses                                  |
         V                                       V
+-------------------+      Loads/Saves      +-----------------+
|  ConfigInstance   | --------------------> |   Filesystem    |
| (Wraps Pydantic   |                       | (JSON/YAML/TOML)|
|  BaseSettings)    |                       +-----------------+
+-------------------+
         | Uses (on value set via new_inst = ModelCls(**data))
         V
+-------------------+      Decorates
| Pydantic Model    | <------------------+
| (BaseSettings)    |                    |
|                   |   +---------------------+
| - Fields          |   | attach_auto_fix     |
| - Validators      |   | (model_validator)   |
+-------------------+   +---------------------+
```

### 2.2. Main Components
*   **2.2.1. Pydantic `BaseSettings` Models (User-defined):** The core structure for defining configurations.
*   **2.2.2. `ConfigManager` (Singleton):** Global registry and service provider for configurations.
*   **2.2.3. `ConfigInstance` (Managed configuration object):** Represents and manages a single, typed configuration.
*   **2.2.4. Validation Subsystem (`attach_auto_fix` and helpers):** Provides pre-processing logic for input values before Pydantic's standard validation.

## 3. Component Deep Dive

### 3.1. Pydantic Configuration Models
*   **3.1.1. Definition:** Users define their configurations by creating classes that inherit from `dynamic_config_manager.BaseSettings` (which is re-exported from `pydantic_settings.BaseSettings`).
    ```python
    from dynamic_config_manager import BaseSettings, Field

    class MyConfig(BaseSettings):
        port: int = Field(8000, ge=1024, le=65535)
        host: str = "localhost"
        feature_flags: Dict[str, bool] = Field(default_factory=dict)
    ```
*   **3.1.2. Using `Field`:** Pydantic's `Field` is used for specifying default values, validation constraints (e.g., `ge`, `le`, `min_length`, `max_length`, `pattern`), and `json_schema_extra`.
*   **3.1.3. Role of `json_schema_extra`:**
    *   **UI Hints:** e.g., `{"ui": "SpinBox", "step": 100}`.
    *   **Options:** e.g., `{"options": ["flat", "ball", "vbit"]}` for string fields, used by `attach_auto_fix`.
    *   **Editability:** e.g., `{"editable": False}` to prevent modification via `ConfigInstance.set_value()`.
    *   **Per-field `attach_auto_fix` settings:** e.g., `{"autofix": {"numeric_policy": "bypass", "eval_expressions": True}}`.

### 3.2. `ConfigManager` Singleton
*Instance available as `from dynamic_config_manager import ConfigManager`.*

*   **3.2.1. Purpose and Singleton Nature:** A globally accessible singleton instance of `_ConfigManagerInternal` that manages all registered `ConfigInstance` objects, provides a default save directory, and facilitates bulk operations.
*   **3.2.2. Properties:**
    *   `default_dir: Path`
        *   **Getter:** Returns the current application-wide default directory for configuration files.
        *   **Setter:** Sets the default directory. Accepts `str`, `os.PathLike`, or `None`.
            *   If `None`, a new unique temporary directory is created (e.g., `tempfile.mkdtemp(prefix="dyn_cfg_mgr_")`).
            *   Otherwise, the provided path is expanded, resolved, and created if it doesn't exist.
        *   **Default:** `Path(tempfile.gettempdir()) / "dynamic_config_manager"`. This directory is created upon `ConfigManager`'s first instantiation.
*   **3.2.3. Methods:**
    *   `register(name: str, model_cls: Type[T], *, save_path: Optional[Union[str, os.PathLike]] = None, auto_save: bool = False, persistent: bool = True) -> ConfigInstance[T]` (where `T` is a `BaseSettings` subclass)
        *   Registers a new configuration model with the manager.
        *   `name`: Unique identifier for this configuration. Raises `ValueError` if name is already registered.
        *   `model_cls`: The Pydantic `BaseSettings` class describing the configuration. Raises `TypeError` if not a subclass of `BaseSettings`.
        *   `save_path`: Specific path to save this configuration file. If `None`, uses `<default_dir>/<name>.json`. If relative, it's relative to `default_dir`.
        *   `auto_save`: If `True` and `persistent` is `True`, the configuration is saved to disk automatically after `set_value()` calls.
        *   `persistent`: If `False`, the configuration is memory-only and never saved to disk (`save_path` is ignored).
        *   Returns the created `ConfigInstance`.
    *   `__getitem__(name: str) -> ConfigInstance`: Retrieves a registered `ConfigInstance` by name. Raises `KeyError` if not found.
    *   `__iter__() -> Iterator[ConfigInstance]`: Iterates over all registered `ConfigInstance` objects.
    *   `save_all()`: Calls `persist()` on all registered, persistent `ConfigInstance` objects.
    *   `restore_all_defaults()`: Calls `restore_defaults()` on all registered `ConfigInstance` objects.
*   **3.2.4. Internal State (`_ConfigManagerInternal` class):**
    *   `_instances: Dict[str, ConfigInstance]`
    *   `_default_dir: Path`

### 3.3. `ConfigInstance`
*Returned by `ConfigManager.register()`.*

*   **3.3.1. Purpose:** A wrapper around a Pydantic `BaseSettings` model instance, providing controlled access, persistence, and lifecycle management for a single configuration.
*   **3.3.2. Initialization (internal, via `ConfigManager.register`):**
    *   `name: str`
    *   `model_cls: Type[T]` (where `T` is a `BaseSettings` subclass)
    *   `save_path: Optional[Path]` (fully resolved path or `None`)
    *   `auto_save: bool`
    *   `persistent: bool`
*   **3.3.3. Internal State:**
    *   `name: str`
    *   `_model_cls: Type[T]`
    *   `_defaults: T` (An instance of `model_cls` initialized with its default values, created via `model_cls()`).
    *   `_active: T` (The current, working instance of the configuration model. Initialized by loading from disk if available, otherwise a deep copy of `_defaults`).
    *   `_save_path: Optional[Path]`
    *   `_auto_save: bool` (effective auto_save: `auto_save_param and persistent_param`)
    *   `_persistent: bool`
*   **3.3.4. Properties:**
    *   `active: T` (Read-only property): Returns a reference to the `_active` Pydantic model instance. Direct mutation of this instance bypasses `set_value`'s auto-save and `attach_auto_fix` pre-processing logic that runs on full model re-instantiation. Use `set_value` for modifications to ensure all hooks run.
*   **3.3.5. Value Manipulation:**
    *   `get_value(path: str) -> Any`:
        *   Retrieves a value from the `_active` model using a path string (e.g., `"foo/bar/0/baz"`).
        *   Uses `_deep_get` helper for traversal.
    *   `set_value(path: str, value: Any)`:
        *   Sets a value in the `_active` model using a path string.
        *   First, checks field metadata: if `json_schema_extra.get("editable")` is `False` for the target field, raises `PermissionError`.
        *   Uses `_deep_set` to construct a dictionary representing the new state of the model.
        *   Creates a new model instance: `self._active = self._model_cls(**new_model_dict)`. This step triggers Pydantic validation, including any `attach_auto_fix` `model_validator`.
        *   If Pydantic validation fails, raises `ValueError` wrapping the `ValidationError`.
        *   If successful and `self._auto_save` is `True`, calls `self.persist()`.
*   **3.3.6. Metadata:**
    *   `get_metadata(path: str) -> Dict[str, Any]`:
        *   Retrieves metadata for a field specified by a path string.
        *   Returns a dictionary including: `type` (annotation), `required`, `default`, `editable` (from `json_schema_extra`, defaults to `True`), Pydantic constraints (`ge`, `le`, etc.), and any other `json_schema_extra` content.
*   **3.3.7. Persistence:**
    *   `persist(file_format: Optional[str]=None) -> bool` (alias: `save`):
        *   Saves the `_active.model_dump(mode="json")` to `_save_path`.
        *   If `_save_path` is `None` (non-persistent config), logs a debug message and returns `False`.
        *   Creates parent directories if they don't exist.
        *   `file_format` (e.g., "json", "yaml", "toml") overrides format detection from path extension.
        *   Logs success or failure. Returns `True` on success, `False` on failure.
    *   `save_as(path: Union[str, os.PathLike], file_format: Optional[str]=None) -> bool`:
        *   Saves the `_active` configuration to a specified `path`.
        *   Similar to `persist` but for a custom location. Does not change `_save_path`.
    *   `_load_from_disk() -> Optional[T]`:
        *   Called during `__init__`.
        *   If `_save_path` exists and is a file, loads data from it.
        *   Instantiates `_model_cls` with the loaded data.
        *   If loading or validation fails, logs a warning and returns `None` (leading to use of defaults).
*   **3.3.8. Restore Operations:**
    *   `restore_value(path: str, source: str = "default")`: # source: Literal["default", "file"]
        *   Restores a single value at `path` to its state from the specified `source`.
        *   `source="default"`: Uses value from `_defaults`.
        *   `source="file"`: Reloads from disk (or uses `_defaults` if file load fails) and gets value from there.
        *   Calls `set_value()` with the restored value, so validation and auto-save apply.
    *   `restore_defaults()`:
        *   Resets `_active` to a deep copy of `_defaults`.
        *   If `_auto_save` is `True`, calls `self.persist()`.

### 3.4. Validation Subsystem (`validation.py`)
*Provides the `attach_auto_fix` decorator and helper functions for input pre-processing.*

*   **3.4.1. `attach_auto_fix` Decorator**
    *   **Signature:** `attach_auto_fix(_cls: Optional[Type[BaseModel]] = None, *, numeric_policy: Union[str, NumericPolicy] = NumericPolicy.CLAMP, options_policy: Union[str, OptionsPolicy] = OptionsPolicy.NEAREST, eval_expressions: bool = False)`
    *   **Application:**
        ```python
        from dynamic_config_manager import attach_auto_fix, BaseSettings, Field

        @attach_auto_fix() # Uses default policies
        class MyConfig(BaseSettings):
            speed: int = Field(100, ge=0, le=200)

        @attach_auto_fix(numeric_policy="reject", eval_expressions=True)
        class AnotherConfig(BaseSettings):
            offset: float = Field(0.0, multiple_of=0.5)
            # Per-field override
            mode: str = Field("auto", json_schema_extra={
                "options": ["auto", "manual", "off"],
                "autofix": {"options_policy": "bypass"} # Field-specific policy
            })
        ```
    *   **Mechanism:** Attaches a Pydantic `model_validator(mode="before")` to the decorated class. This validator (`_auto` internal function) runs before Pydantic's standard field and model validation.
    *   **Per-field Override:** The model validator checks each field's `FieldInfo.json_schema_extra`. If `json_schema_extra` is a dictionary and contains an `"autofix"` key, its value (expected to be a dictionary) is used to override the global `attach_auto_fix` settings for that specific field (e.g., `{"autofix": {"numeric_policy": "reject"}}`).
*   **3.4.2. Policies (Enums):**
    *   `NumericPolicy(str, Enum)`:
        *   `CLAMP`: (Default) Clamps numeric values to `ge/le` bounds. Rounds to `multiple_of` if specified.
        *   `REJECT`: If value is outside `ge/le` or not a multiple of `multiple_of`, the original unprocessed value for the field is passed to Pydantic (which will likely raise a `ValidationError`).
        *   `BYPASS`: Skips numeric auto-fixing for the field. The original value is passed to Pydantic.
    *   `OptionsPolicy(str, Enum)`:
        *   `NEAREST`: (Default) If string value is not in `json_schema_extra["options"]`, attempts to find the closest match. If no suitable match, original value is passed to Pydantic.
        *   `REJECT`: If value is not in `options`, original value is passed to Pydantic.
        *   `BYPASS`: Skips options auto-fixing. Original value is passed to Pydantic.
*   **3.4.3. Core Logic (The `model_validator` function injected by `attach_auto_fix`):**
    *   Receives the raw input data dictionary.
    *   Creates a mutable copy `fixed_data = dict(raw_data)`.
    *   Iterates through fields defined in the model (`cls.model_fields.items()`).
    *   For each field present in `raw_data`:
        1.  Determines the effective `autofix` policies: starts with global policies from decorator, then overrides with field-specific settings from `field_info.json_schema_extra.get("autofix", {})`.
        2.  Retrieves `original_value = raw_data[name]`.
        3.  Applies numeric fixing logic if applicable (field type is numeric or constraints like `ge`, `multiple_of` are present):
            *   Calls internal helper `_run_numeric_autofix(original_value, field_info, effective_numeric_policy, effective_eval_expressions, constraints)`.
            *   This helper performs expression evaluation, type coercion, and policy enforcement. It returns the processed value, or `original_value` if rejected/bypassed/failed.
        4.  Applies options fixing logic if `json_schema_extra["options"]` are present:
            *   Calls internal helper `_run_options_autofix(current_value_from_step3, field_info, effective_options_policy, options_list)`.
            *   This helper performs matching and policy enforcement. It returns the processed value, or `current_value_from_step3` if rejected/bypassed/failed.
        5.  Applies length constraint checks (`min_length`, `max_length`) if applicable:
            *   If value's length is outside bounds, and policy implies rejection (e.g., tied to `REJECT` `numeric_policy`, or a hardcoded reject for length), the value from the previous step is kept (effectively passing the problematic value to Pydantic). This is "REJECT only" for length constraints as per current implementation.
        6.  Updates `fixed_data[name]` with the final processed value from these steps.
    *   Returns `fixed_data` to Pydantic for standard validation.
*   **3.4.4. `_run_numeric_autofix` (Conceptual private helper):**
    *   **Input:** `original_value`, `field_info`, `numeric_policy`, `eval_allowed`, `constraints` (derived from `field_info`).
    *   **Output:** `processed_value` (which might be `original_value`).
    *   **Steps:**
        1.  `current_val = original_value`.
        2.  **Expression Evaluation:** If `eval_allowed` and `current_val` is a string, call `_safe_eval(current_val, names={"v": current_val, "x": current_val, "min": ge_val, "max": le_val})`. If successful, `current_val` becomes the evaluated number. If `_safe_eval` returns `None` (error), `current_val` remains the original string.
        3.  **Type Coercion:** Attempt to coerce `current_val` to the field's annotation type (e.g., `int`, `float`) using `field_info.annotation(current_val)`. If coercion fails (raises exception):
            *   Return `original_value`. (Pydantic will then handle the type error).
        4.  Let coerced value be `coerced_val`.
        5.  **Policy Application:**
            *   If `numeric_policy == NumericPolicy.BYPASS`: Return `coerced_val`.
            *   Check `ge/gt/le/lt` constraints against `coerced_val`.
            *   Check `multiple_of` constraint against `coerced_val`.
            *   If `numeric_policy == NumericPolicy.CLAMP`:
                *   If `coerced_val` violates `ge/le`, clamp it.
                *   If `multiple_of` is set and clamped value is not a multiple, round it to the nearest multiple.
                *   Return the clamped/rounded value.
            *   If `numeric_policy == NumericPolicy.REJECT`:
                *   If `coerced_val` violates `ge/le` or `multiple_of`, return `original_value`.
                *   Otherwise, return `coerced_val`.
        6.  Return `coerced_val` (if no early return).
*   **3.4.5. `_run_options_autofix` (Conceptual private helper):**
    *   **Input:** `original_value`, `field_info`, `options_policy`, `options_list` (from `json_schema_extra`).
    *   **Output:** `processed_value` (which might be `original_value`).
    *   **Steps:**
        1.  If `original_value` is already in `options_list`, return `original_value`.
        2.  If `options_policy == OptionsPolicy.BYPASS`: Return `original_value`.
        3.  If `options_policy == OptionsPolicy.NEAREST`:
            *   If `original_value` is a string, use `difflib.get_close_matches(original_value, [str(o) for o in options_list], n=1, cutoff=0.3)`.
            *   If a match is found, convert it back to the type of the option in `options_list` (if options are not all strings) and return it.
            *   If no match, return `original_value`.
        4.  If `options_policy == OptionsPolicy.REJECT`: Return `original_value` (as it's not in `options_list`).
        5.  Return `original_value` (default fallback).
*   **3.4.6. Length Constraint Handling (within main model validator loop):**
    *   Applies to string/list/dict fields with `min_length` or `max_length`.
    *   This is a "REJECT-only" mechanism. If the length of the (potentially already processed by numeric/options fixers) value violates these constraints, the value is *not modified further by this check*. Pydantic will then validate this value against `min_length`/`max_length` and raise an error if it fails. This ensures the original problematic value (or auto-fixed value that is still too long/short) is seen by Pydantic.
*   **3.4.7. `_safe_eval(expr: str, names: dict[str, Any]) -> Optional[Union[float, int]]`**
    *   Safely evaluates arithmetic expressions.
    *   Replaces `^` with `**`.
    *   Allowed variables in `names`: `v`, `x` (current value being evaluated, typically passed by caller), `min`, `max` (bounds of the field, if numeric).
    *   Allowed functions: `abs`, `round`, `sqrt`, `min`, `max`.
    *   Allowed constants: `pi`, `e`.
    *   Allowed AST nodes: `Num`, `Name` (for allowed vars/consts), `BinOp` (for `+,-,*,/,**, %`), `UnaryOp` (`+`,`-`), `Call` (for allowed functions).
    *   Shorthand: If `expr` starts with `+,-,*,/` (e.g., `"/2"`), it's interpreted as `f"v{expr}"`.
    *   Returns the numeric result, or `None` if parsing/evaluation fails due to disallowed operations or syntax errors.

## 4. File I/O

*   **4.1. Supported Formats:** JSON (default), YAML, TOML.
*   **4.2. Format Detection:** Primarily based on file extension (`.json`, `.yml`, `.yaml`, `.toml`) via `_detect_format(path)`. Can be overridden by passing `file_format` argument to save/load methods.
*   **4.3. Helper Functions (private, in `manager.py`):**
    *   `_detect_format(path: Path) -> str`: Returns "json", "yaml", or "toml".
    *   `_load_file(path: Path, *, file_format: Optional[str] = None) -> Dict[str, Any]`: Reads and parses the file.
    *   `_dump_file(path: Path, data: Dict[str, Any], *, file_format: Optional[str] = None)`: Dumps data to the file, pretty-printed for JSON/YAML.
*   **4.4. Dependencies for File Formats:**
    *   YAML: `PyYAML` (`pip install pyyaml`)
    *   TOML Read: `tomli` (`pip install tomli`) - for Python < 3.11
    *   TOML Write: `tomli-w` (`pip install tomli-w`)
    *   These should be optional dependencies (extras syntax in `pyproject.toml`, e.g., `dynamic-config-manager[yaml,toml]`).

## 5. Data Flow and Validation Sequence for `ConfigInstance.set_value()`

1.  Application calls `config_instance.set_value("some/path", new_value)`.
2.  `ConfigInstance` checks if field at "some/path" is editable via `get_metadata()`. Raises `PermissionError` if not.
3.  `_deep_set(config_instance._active, "some/path".split("/"), new_value)` is called. This returns a new Pydantic model instance (or dict/list for nested structures) with the proposed change.
4.  The result from `_deep_set` is dumped to a dictionary: `raw_data_dict = new_inst_or_dict.model_dump(mode="python")`.
5.  `config_instance._active = config_instance._model_cls(**raw_data_dict)` is called. This triggers full Pydantic model instantiation.
    *   **5.a. `attach_auto_fix` Pre-processing:** The `model_validator(mode="before")` (defined by `attach_auto_fix`) runs first.
        *   It iterates through fields in `raw_data_dict`.
        *   Applies expression evaluation, numeric fixing (clamping/rejection/bypass), options fixing (nearest/rejection/bypass), and length checks according to effective policies (global + per-field overrides).
        *   If a fixer (e.g., `_run_numeric_autofix`) determines a value should be rejected or cannot be processed, it returns the original value it received for that field. Otherwise, it returns the modified value.
        *   The `model_validator` constructs a `fixed_data_dict` where each value is the result from its respective auto-fix processing.
        *   This `fixed_data_dict` is returned to Pydantic.
    *   **5.b. Pydantic Standard Validation:** Pydantic processes `fixed_data_dict`.
        *   Performs type coercion/validation for each field.
        *   Checks standard Pydantic constraints (`ge`, `pattern`, `min_length`, user-defined validators, etc.).
        *   If any validation fails, Pydantic raises `ValidationError`.
6.  If Pydantic validation succeeds, the new model instance is assigned to `config_instance._active`.
7.  If `config_instance._auto_save` is `True`, `config_instance.persist()` is called.
8.  If `ValidationError` was raised at step 5.b, `ConfigInstance.set_value()` catches it and re-raises it wrapped in a `ValueError` with more context.

## 6. Public API Summary (`__init__.py`)
The `dynamic_config_manager/__init__.py` should expose:
*   `ConfigManager` (the singleton instance)
*   `BaseSettings` (re-export from `pydantic_settings`)
*   `BaseModel`, `Field`, `ValidationError` (re-exports from `pydantic`)
*   `attach_auto_fix` (from `dynamic_config_manager.validation`)
*   `__version__`

## 7. Error Handling Strategy
*   **Pydantic `ValidationError`:** Raised (possibly wrapped) when input data fails model validation after `attach_auto_fix` pre-processing.
*   **`ValueError`:** For invalid arguments or operations (e.g., registering duplicate config name, bad `source` in `restore_value`).
*   **`KeyError`:** Accessing non-existent config name in `ConfigManager` or non-existent path in `_deep_get`.
*   **`PermissionError`:** Attempting to set a non-editable field via `ConfigInstance.set_value()`.
*   **`TypeError`:** Incorrect type for `model_cls` during registration.
*   **File I/O Errors:** Logged warnings for non-critical issues (e.g., `_load_from_disk` failing leads to using defaults, `persist` failing is logged but doesn't crash app). Exceptions may propagate for critical failures if not handled by Pydantic or file helpers.

## 8. Logging
*   Use Python's standard `logging` module.
*   The library's root logger (`logging.getLogger("dynamic_config_manager")`) should have a `logging.NullHandler()` attached by default to prevent log messages if the application doesn't configure logging.
*   **Log Events:**
    *   INFO: Config registration, successful save/export.
    *   DEBUG: Memory-only config not persisted, auto-fix actions (optional, can be verbose).
    *   WARNING: Failure to load config from disk (falling back to defaults), failure to save/export config, bad data format encountered.
    *   ERROR: Critical internal errors (should be rare).

## 9. Dependencies and Installation
*   **Core:**
    *   `pydantic>=2.0`
    *   `pydantic-settings>=2.0`
*   **Optional (for file formats):**
    *   `PyYAML>=5.0` (for YAML)
    *   `tomli>=1.0.0` (for TOML read, if Python < 3.11)
    *   `tomli-w>=0.4.0` (for TOML write)
*   **Installation:**
    *   Standard: `pip install dynamic-config-manager`
    *   With extras: `pip install dynamic-config-manager[yaml,toml]`
    *   The `pyproject.toml` should define these extras.

## 10. Quick Start / Usage Example (Illustrative)

```python
from dynamic_config_manager import BaseSettings, Field, ConfigManager, attach_auto_fix

# 1. Define your configuration model with auto-fix enabled
@attach_auto_fix(numeric_policy="clamp", eval_expressions=True)
class AppConfig(BaseSettings):
    server_port: int = Field(8080, ge=1024, le=65535, json_schema_extra={"ui": "SpinBox"})
    log_level: str = Field("INFO", json_schema_extra={"options": ["DEBUG", "INFO", "WARNING", "ERROR"]})
    retry_attempts: int = Field(3, ge=0, le=5, json_schema_extra={"autofix": {"numeric_policy": "reject"}}) # Override global
    feature_x_threshold: float = Field(0.5, ge=0, le=1.0)

# 2. Set application-wide default config directory (optional, recommended)
ConfigManager.default_dir = "~/.my_app/config" # Expands and creates directory

# 3. Register the configuration
app_cfg_instance = ConfigManager.register("app_settings", AppConfig, auto_save=True)

# Access the active configuration model (Pydantic instance)
active_config = app_cfg_instance.active
print(f"Initial Port: {active_config.server_port}") # -> 8080 (or loaded value)

# 4. Set values (validation and auto-fix run automatically)
try:
    app_cfg_instance.set_value("server_port", "8000+100") # Uses eval_expressions -> 8100
    app_cfg_instance.set_value("log_level", "debug") # Uses options_policy (nearest) -> "DEBUG"
    app_cfg_instance.set_value("retry_attempts", 10) # numeric_policy="reject" for this field
except ValueError as e:
    print(f"Failed to set retry_attempts: {e}") # Pydantic validation error for retry_attempts > 5

print(f"New Port: {app_cfg_instance.get_value('server_port')}") # -> 8100
print(f"Log Level: {app_cfg_instance.get_value('log_level')}") # -> "DEBUG"

# 5. Restore defaults or individual values
app_cfg_instance.restore_value("server_port", source="default")
# app_cfg_instance.restore_defaults() # Restore all to model defaults

# 6. Save all managed configs (if not auto-saved)
# ConfigManager.save_all()
```

## Appendix A: Helper function details (`manager.py`)

*   **`_deep_get(data: Any, keys: List[str]) -> Any`**:
    Traverses nested Pydantic models, dictionaries, and lists using a list of string keys. Handles attribute access for models and item access for dicts/lists (converting numeric string keys to int for lists). Raises `KeyError` or `AttributeError` or `IndexError` on failure.

*   **`_deep_set(data: Any, keys: List[str], value: Any) -> BaseModel | Any`**:
    Recursively creates a *copy* of the nested structure `data` with the `value` set at the path specified by `keys`.
    If `data` is a Pydantic `BaseModel`, it performs `model_dump()`, sets the nested value in the dictionary, and returns a *new instance* of the model class initialized with the modified dictionary: `data.__class__(**copied_dict)`.
    If `data` is a `dict` or `list`, it returns a shallow copy with the nested value set.
    This ensures that modifications trigger Pydantic's re-validation when the `ConfigInstance` uses the result to update its `_active` model.
