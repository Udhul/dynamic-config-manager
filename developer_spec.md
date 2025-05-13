# Dynamic Config Manager - Developer Specification (v2)

## 1. Introduction

### 1.1. Project Goal
To create a Python package, `dynamic-config-manager`, providing a robust, typed, and file-backed configuration framework. It wraps Pydantic (v2) `BaseSettings` to offer dynamic loading, updating, saving, validation, and management of application configurations, with advanced pre-processing capabilities for various data formats.

### 1.2. Core Philosophy
*   **Pydantic-centric:** Leverage Pydantic V2 for model definition, type checking, and core validation.
*   **Typed:** Emphasize strong typing for configuration clarity and safety, with enhanced Pylance/LSP support.
*   **User-friendly & Intuitive:** Simple API for common tasks, with powerful customization options, including an optional custom base class and field constructor for easier definition.
*   **Explicit over Implicit:** Clear control over persistence, saving, and validation behaviors.
*   **Separation of Concerns:** `attach_auto_fix` pre-processes data based on defined formats and policies; Pydantic performs final validation against the model's type annotations and constraints.

### 1.3. Key Features Summary
*   Configuration definition via Pydantic `BaseSettings` models, or an optional enhanced `DynamicBaseSettings` with a `ConfigField` helper for convenience.
*   Singleton `ConfigManager` for centralized management of multiple configurations.
*   Default save directory management with per-config overrides.
*   Opt-in/out persistence for configurations (memory-only or file-backed).
*   Support for JSON (default), YAML, and TOML file formats.
*   Path-based deep access (`get_value`, `set_value`) for configuration values.
*   Attribute-based access (`config_instance.active.path.to.value`) for *reading* values with full type hinting. Setting values with full pre-processing and auto-save pipeline is done via `set_value`.
*   Automatic validation and (optional) auto-saving on value changes made through `set_value`.
*   Restore functionality for individual values or entire configurations to defaults or file-persisted state.
*   `attach_auto_fix` decorator for Pydantic models to enable input pre-processing:
    *   **Numeric fields:** Clamping/rejection based on `ge/gt/le/lt`, `multiple_of` enforcement (rounding or rejection). Safe evaluation of mathematical string expressions.
    *   **Options fields (single choice):** Snapping to nearest option or rejection.
    *   **String fields:** `min_length`/`max_length` pre-check (rejection if policy dictates).
    *   **Advanced Formats:**
        *   **Ranges (`Tuple[N,N]`):** Validation of bounds, item types, optional clamping.
        *   **Multiple Choice (`List[T]` from options):** Validation of selected items against options, count limits.
        *   **List Conversion (e.g., CSV string to `List[int]`):** Pre-processing of string inputs into typed lists.
    *   Configurable policies (e.g., `CLAMP`, `NEAREST`, `REJECT`, `BYPASS`, and format-specific policies) for fixing behaviors, configurable globally via decorator or per-field.
*   Handles `None` as a valid value if permitted by the field's type annotation (`Optional[T]`, `Union[T, None]`).
*   Access to Pydantic field metadata, including constraints and structured `json_schema_extra` for UI hints, format specifications, and `autofix` settings.

## 2. System Architecture

### 2.1. Overview Diagram
```
+-------------------+      Registers     +-------------------+
|  User Application | -----------------> |   ConfigManager   |
|                   | <----------------- |    (Singleton)    |
| - Defines Models  |   Access Configs   +-------------------+
|(using BaseSettings|                            | Manages
| or DynamicBaseSet)|                            |
+-------------------+                            V
         | Uses                                  |
         V                                       V
+-------------------+      Loads/Saves      +-----------------+
|  ConfigInstance   | --------------------> |   Filesystem    |
| (Wraps Pydantic   |                       | (JSON/YAML/TOML)|
|  Model)           |                       +-----------------+
+-------------------+
         | Modifies via set_value()
         | Instantiates / Validates
         V
+-------------------+      Decorates
| Pydantic Model    | <------------------+
| (BaseSettings or  |                    |
|  DynamicBaseSet.) |   +---------------------+
|                   |   | attach_auto_fix     |
| - Fields (Fields  |   | (model_validator)   |
|   or ConfigFields)|   +---------------------+
| - Validators      |
+-------------------+
```

### 2.2. Main Components
*   **2.2.1. Pydantic Configuration Models (User-defined):** Core structure. Can be plain `BaseSettings` or the enhanced `DynamicBaseSettings`.
*   **2.2.2. `ConfigManager` (Singleton):** Global registry and service provider.
*   **2.2.3. `ConfigInstance` (Managed configuration object):** Represents and manages a single, typed configuration.
*   **2.2.4. Validation Subsystem (`attach_auto_fix` and helpers):** Provides pre-processing logic.
*   **2.2.5. (Optional) `DynamicBaseSettings` and `ConfigField`:** Convenience tools for defining models.

## 3. Component Deep Dive

### 3.1. Pydantic Configuration Models & `DynamicBaseSettings`
*   **3.1.1. Definition:** Users define configurations by inheriting from `dynamic_config_manager.BaseSettings` or the recommended `dynamic_config_manager.DynamicBaseSettings`.
*   **3.1.2. `DynamicBaseSettings(BaseSettings)`:**
    *   An optional base class that may provide common `model_config` or helper methods in the future. Primarily serves as a clear entry point for using `ConfigField`.
*   **3.1.3. `ConfigField(...)` function:**
    *   A wrapper around Pydantic's `Field` to simplify setting `json_schema_extra` with structured keys for `dynamic-config-manager` features.
    *   **Signature (Conceptual):**
        ```python
        def ConfigField(
            default: Any = PydanticUndefined,
            *,
            # All standard pydantic.Field arguments (description, ge, le, etc.)
            # ...
            # dynamic-config-manager specific arguments:
            ui_hint: Optional[str] = None,
            ui_extra: Optional[Dict[str, Any]] = None, # e.g., {"step": 1, "editable": False}
            options: Optional[List[Any]] = None, # For single-choice or as source for multiple-choice
            autofix_settings: Optional[Dict[str, Union[str, Enum, bool]]] = None, # Per-field override for attach_auto_fix policies
            format_spec: Optional[Dict[str, Any]] = None, # Defines advanced format and its options
            **extra_json_schema_extra: Any,
        ) -> Any: # Returns a Pydantic FieldInfo object
        ```
    *   Internally, `ConfigField` constructs the `json_schema_extra` dictionary with keys like `"ui_hint"`, `"ui_extra"`, `"options"`, `"autofix"`, `"format_spec"`.
*   **3.1.4. Structure of `json_schema_extra` (when using `ConfigField` or manually structured):**
    ```json
    {
      "ui_hint": "Slider", // E.g., "SpinBox", "ComboBox", "FilePath"
      "ui_extra": {"step": 10, "editable": true, "min_val": 0, "max_val": 100}, // Arbitrary UI data
      "options": ["alpha", "beta", "gamma"], // For single-choice or basis for multi-choice
      "autofix": { // Per-field overrides for attach_auto_fix policies
        "numeric_policy": "clamp", // or "reject", "bypass"
        "options_policy": "nearest", // or "reject", "bypass"
        "eval_expressions": true, // bool
        "range_policy": "clamp_items", // specific to "range" format_type
        "multiple_choice_policy": "remove_invalid", // specific to "multiple_choice"
        "list_conversion_policy": "convert_or_reject" // specific to list conversion formats
      },
      "format_spec": { // Defines advanced field formats and their specific options
        "type": "range", // E.g., "multiple_choice", "csv_to_list_int", "datetime_string"
        // Options specific to "type":
        // For "range" (expects field annotation like Tuple[int,int]):
        "item_type": "int", // or "float"
        "min_item_value": 0, // Optional constraint for items in range
        "max_item_value": 100, // Optional constraint for items in range
        "allow_single_value_as_range": false, // If true, input `5` becomes `(5,5)`
        // For "multiple_choice" (expects field annotation like List[str]):
        "min_selections": 0,
        "max_selections": 3,
        // For "csv_to_list_int" (expects List[int]):
        "separator": ",",
        "item_numeric_policy": "clamp", // Policy for individual items if they are numeric
        "item_ge": 0, "item_le": 10 // Constraints for converted list items
      }
    }
    ```
*   **3.1.5. Using Pydantic `Field` Directly:** Users can still use `pydantic.Field` and manually structure `json_schema_extra` as above if not using `ConfigField`. The system will read from these keys.

### 3.2. `ConfigManager` Singleton
*   **Purpose and Singleton Nature:** A globally accessible singleton instance of `_ConfigManagerInternal` that manages all registered `ConfigInstance` objects, provides a default save directory, and facilitates bulk operations.
*   **Properties:**
    *   `default_dir: Path`
        *   **Getter:** Returns the current application-wide default directory for configuration files.
        *   **Setter:** Sets the default directory. Accepts `str`, `os.PathLike`, or `None`.
            *   If `None`, a new unique temporary directory is created (e.g., `tempfile.mkdtemp(prefix="dyn_cfg_mgr_")`).
            *   Otherwise, the provided path is expanded, resolved, and created if it doesn't exist.
        *   **Default:** `Path(tempfile.gettempdir()) / "dynamic_config_manager"`. This directory is created upon `ConfigManager`'s first instantiation.
*   **Methods:**
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
*   **Internal State (`_ConfigManagerInternal` class):**
    *   `_instances: Dict[str, ConfigInstance]`
    *   `_default_dir: Path`

### 3.3. `ConfigInstance`
*   **Purpose:** A wrapper around a Pydantic `BaseSettings` model instance, providing controlled access, persistence, and lifecycle management for a single configuration.
*   **Initialization (internal, via `ConfigManager.register`):**
    *   `name: str`
    *   `model_cls: Type[T]` (where `T` is a `BaseSettings` subclass)
    *   `save_path: Optional[Path]` (fully resolved path or `None`)
    *   `auto_save: bool`
    *   `persistent: bool`
*   **Internal State:**
    *   `name: str`
    *   `_model_cls: Type[T]`
    *   `_defaults: T` (An instance of `model_cls` initialized with its default values, created via `model_cls()`).
    *   `_active: T` (The current, working instance of the configuration model. Initialized by loading from disk if available, otherwise a deep copy of `_defaults`).
    *   `_save_path: Optional[Path]`
    *   `_auto_save: bool` (effective auto_save: `auto_save_param and persistent_param`)
    *   `_persistent: bool`
*   **Properties:**
    *   `active: T` (Read-only property): Returns a reference to the `_active` Pydantic model instance.
        *   **Important Note on Access:**
            *   **For Reading:** Direct attribute access like `val = config_instance.active.path.to.nested_value` is supported and provides full type hinting via Pylance/LSP.
            *   **For Setting:** To ensure the full `attach_auto_fix` pre-processing, Pydantic validation, and `auto_save` mechanisms are triggered, modifications **must** be made through `config_instance.set_value("path/to/value", new_value)`. Direct assignment (e.g., `config_instance.active.some_field = val`) will modify the Pydantic model in place, triggering only Pydantic's native field validators, bypassing the `attach_auto_fix` `model_validator` and `ConfigInstance`'s auto-save logic for that specific assignment.
*   **Value Manipulation:**
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
*   **Metadata:**
    *   `get_metadata(path: str) -> Dict[str, Any]`:
        *   Retrieves metadata for a field specified by a path string.
        *   Returns a dictionary including: `type` (annotation), `required`, `default`, `editable` (from `json_schema_extra`, defaults to `True`), Pydantic constraints (`ge`, `le`, etc.), and any other `json_schema_extra` content (including `ui_hint`, `ui_extra`, `options`, `autofix` settings, `format_spec`).
*   **Persistence:**
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
*   **Restore Operations:**
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
    *   **Signature (Conceptual - actual policy types will be Enums):**
        ```python
        def attach_auto_fix(
            _cls: Optional[Type[BaseModel]] = None,
            *,
            numeric_policy: str = "clamp",
            options_policy: str = "nearest", # For single-choice string options
            eval_expressions: bool = False,
            # Default policies for new formats:
            range_policy: str = "reject_if_invalid", # e.g. "clamp_items"
            multiple_choice_policy: str = "remove_invalid", # e.g. "reject_if_any_invalid"
            list_conversion_policy: str = "convert_or_reject", # e.g. "convert_best_effort"
            # General fallback behavior for unhandled types or generic issues:
            default_string_policy: str = "bypass", # e.g. strip, lower (if generic string ops added)
        )
        ```
    *   **Mechanism:** Attaches a Pydantic `model_validator(mode="before")` to the decorated class.
    *   **Per-field Override:** The model validator checks `field_info.json_schema_extra.get("autofix", {})` for overrides to these global policies.
*   **3.4.2. Policies (Enums):**
    *   `NumericPolicy(str, Enum)`: `CLAMP`, `REJECT`, `BYPASS`.
    *   `OptionsPolicy(str, Enum)`: `NEAREST`, `REJECT`, `BYPASS` (for single string option matching).
    *   **New Policies (Examples - to be defined):**
        *   `RangePolicy(str, Enum)`: `CLAMP_ITEMS` (clamp items to `item_min/max_value` if specified in `format_spec`), `REJECT_IF_INVALID_STRUCTURE`, `REJECT_IF_ITEMS_INVALID`, `SWAP_IF_MIN_GT_MAX_AND_VALID`.
        *   `MultipleChoicePolicy(str, Enum)`: `REMOVE_INVALID_CHOICES` (keep valid ones), `REJECT_IF_ANY_INVALID`, `REJECT_IF_COUNT_INVALID` (violates `min/max_selections`).
        *   `ListConversionPolicy(str, Enum)`: `CONVERT_OR_REJECT` (entire field rejected if any item fails conversion/validation), `CONVERT_BEST_EFFORT` (convert valid items, discard/replace invalid ones based on sub-policy).
    *   All policy sets should include `REJECT` and `BYPASS` variants.
*   **3.4.3. Core Logic (The `model_validator` function injected by `attach_auto_fix`):**
    *   Receives `raw_data_dict` (input to the model).
    *   Creates `fixed_data = {}`.
    *   Iterates `name, field_info` in `cls.model_fields.items()`:
        1.  `original_value = raw_data_dict.get(name, PydanticUndefined)` (Handle cases where field might not be in input, relying on Pydantic defaults).
        2.  If `original_value is PydanticUndefined` and field has a default or is `Optional`, skip `autofix` for this field unless specific policy dictates otherwise (e.g. "process_defaults"). Generally, `autofix` acts on provided input.
        3.  Determine `effective_autofix_policies` and `format_spec` from global decorator args and `field_info.json_schema_extra`.
        4.  `processed_value = original_value`.
        5.  **Handle `None`:** If `original_value is None` and `field_info.annotation` permits `None` (e.g., `Optional[T]`, `Union[T, None]`), `processed_value` remains `None` and most subsequent auto-fixing steps are bypassed for this value, unless a specific policy targets `None` values (e.g., "replace_none_with_default_if_not_optional").
        6.  **Dispatch based on `format_spec.get("type")` or field type:**
            *   If `format_spec.type == "range"`: `processed_value = _run_range_autofix(processed_value, policies, format_spec, field_info)`.
            *   If `format_spec.type == "multiple_choice"`: `processed_value = _run_multichoice_autofix(...)`.
            *   If `format_spec.type == "csv_to_list_int"` (example): `processed_value = _run_list_conversion_autofix(...)`.
            *   **Else (no specific format_spec or it's a basic type):**
                *   **Numeric Processing:** If field appears numeric (based on annotation or constraints like `ge`/`le`/`multiple_of`):
                    *   Apply expression evaluation if `eval_expressions` is true and `processed_value` is a string. Update `processed_value` with result or keep original string if eval fails.
                    *   Attempt coercion of `processed_value` to the target numeric type (derived from `field_info.annotation`).
                    *   Apply `NumericPolicy` (clamp/reject/bypass) using `ge/le/multiple_of` constraints from `field_info.metadata`.
                *   **Options Processing (single choice):** If `options` are in `json_schema_extra` (and not handled by `multiple_choice` format):
                    *   Apply `OptionsPolicy` (nearest/reject/bypass).
                *   **String Length Processing:** If `processed_value` is a string and `min_length`/`max_length` are defined:
                    *   Apply policy (effectively "REJECT" if `NumericPolicy` (reused for this) is `REJECT` and length constraint violated, otherwise Pydantic handles it).
        7.  **Result Handling from Fixers:** Each `_run_..._autofix` helper should return a tuple: `(status: FixStatusEnum, value: Any)`.
            *   `FixStatusEnum`: `PROCESSED_MODIFIED`, `PROCESSED_UNMODIFIED` (valid as-is), `BYPASSED`, `REJECTED_BY_POLICY`, `FAILED_PREPROCESSING`.
            *   If status is `REJECTED_BY_POLICY` or `FAILED_PREPROCESSING`, then `fixed_data[name] = original_value` (pass the raw input for this field to Pydantic).
            *   Otherwise, `fixed_data[name] = value` (the processed or bypassed value).
    *   Fields from `raw_data_dict` not defined in the model are passed through (Pydantic will handle them, e.g., `model_extra='ignore'/'forbid'`).
    *   Returns `fixed_data` to Pydantic.
*   **3.4.4. Specific Auto-Fix Helper Functions (Conceptual):**
    *   `_run_numeric_autofix(...)`: Includes `_safe_eval`. Handles `None` inputs gracefully if field is `Optional`.
    *   `_run_options_autofix(...)`: For single string choice.
    *   `_run_range_autofix(...)`: Validates tuple/list structure, item types, bounds, applies `RangePolicy`.
    *   `_run_multichoice_autofix(...)`: Validates against `options`, selection counts, applies `MultipleChoicePolicy`.
    *   `_run_list_conversion_autofix(...)`: Parses input (e.g., CSV string), converts items, validates items, applies `ListConversionPolicy`.
*   **3.4.5. `_safe_eval(expr: str, names: dict[str, Any]) -> Optional[Union[float, int]]`**
    *   Safely evaluates arithmetic expressions.
    *   Replaces `^` with `**`.
    *   Allowed variables in `names`: `v`, `x` (current value being evaluated, typically passed by caller), `min`, `max` (bounds of the field, if numeric).
    *   Allowed functions: `abs`, `round`, `sqrt`, `min`, `max`.
    *   Allowed constants: `pi`, `e`.
    *   Allowed AST nodes: `Num`, `Name` (for allowed vars/consts), `BinOp` (for `+,-,*,/,**, %`), `UnaryOp` (`+`,`-`), `Call` (for allowed functions).
    *   Shorthand: If `expr` starts with `+,-,*,/` (e.g., `"/2"`), it's interpreted as `f"v{expr}"`.
    *   Returns the numeric result, or `None` if parsing/evaluation fails due to disallowed operations or syntax errors.
*   **3.4.6. Handling `Union` Types:**
    *   `attach_auto_fix` pre-processes the input value based on its apparent type and the configured rules (e.g., if it's a string and `eval_expressions` is on, it's evaluated).
    *   The (potentially) modified value is then passed to Pydantic.
    *   Pydantic's standard `Union` validation logic then attempts to match the value against each member of the `Union` in the order they are defined.
    *   `dynamic-config-manager` does not attempt to apply different `autofix` rules for different members of a `Union` field during its pre-processing pass. The constraints defined on the `Union` members themselves (e.g., `Union[PositiveInt, constr(min_length=5)]`) are handled by Pydantic after `attach_auto_fix`.

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
        *   Applies expression evaluation, numeric fixing (clamping/rejection/bypass), options fixing (nearest/rejection/bypass), advanced format processing (range, multiple_choice, list_conversion), and length checks according to effective policies (global + per-field overrides).
        *   If a fixer (e.g., `_run_numeric_autofix`) determines a value should be rejected or cannot be processed (returns status `REJECTED_BY_POLICY` or `FAILED_PREPROCESSING`), it passes the original input value for that field to Pydantic. Otherwise, it passes the (potentially) modified value.
        *   The `model_validator` constructs a `fixed_data_dict` where each value is the result from its respective auto-fix processing (or the original value if fixing was rejected/failed).
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
*   `DynamicBaseSettings` (new custom base class)
*   `ConfigField` (new field constructor function)
*   `BaseModel`, `Field`, `ValidationError` (re-exports from `pydantic`)
*   `attach_auto_fix` (from `dynamic_config_manager.validation`)
*   Policy Enums (e.g., `NumericPolicy`, `OptionsPolicy`, `RangePolicy`, `MultipleChoicePolicy`, `ListConversionPolicy`, `FixStatusEnum`)
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
    *   DEBUG: Memory-only config not persisted, auto-fix actions and decisions (e.g., value modified from X to Y by policy Z for field F), expression evaluation results.
    *   WARNING: Failure to load config from disk (falling back to defaults), failure to save/export config, bad data format encountered, auto-fix policy resulted in using original value due to pre-processing failure or rejection.
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

## 10. Quick Start / Usage Example (Illustrative - Updated)

```python
from typing import Optional, Tuple, List
from pydantic import PydanticUndefined # For ConfigField default

from dynamic_config_manager import (
    DynamicBaseSettings, ConfigField, ConfigManager, attach_auto_fix,
    NumericPolicy # Example policy enum
)

# 1. Define your configuration model with auto-fix and new field types
@attach_auto_fix(numeric_policy=NumericPolicy.CLAMP, eval_expressions=True)
class AdvancedConfig(DynamicBaseSettings):
    server_port: int = ConfigField(
        default=8080, ge=1024, le=65535,
        ui_hint="SpinBox"
    )
    log_level: str = ConfigField(
        default="INFO",
        options=["DEBUG", "INFO", "WARNING", "ERROR"], # For single choice
        ui_hint="ComboBox"
    )
    processing_range: Tuple[int, int] = ConfigField(
        default=(10, 90),
        format_spec={
            "type": "range",
            "item_type": "int",
            "min_item_value": 0,
            "max_item_value": 100
        },
        autofix_settings={"range_policy": "clamp_items"} # clamp items within 0-100
    )
    selected_features: List[str] = ConfigField(
        default_factory=list,
        options=["feature_a", "feature_b", "feature_c", "feature_d"], # Source for multi-choice
        format_spec={
            "type": "multiple_choice",
            "max_selections": 2
        },
        autofix_settings={"multiple_choice_policy": "remove_invalid"}
    )
    user_ids_input: List[int] = ConfigField( # Input might be "1,2, 3 , non_int, 5"
        default_factory=list,
        format_spec={
            "type": "csv_to_list", # Assuming 'csv_to_list' handles item_type implicitly or configured
            "item_type": "int",
            "item_numeric_policy": "reject" # Reject non-int items
        },
        autofix_settings={"list_conversion_policy": "convert_best_effort"}
    )
    nullable_value: Optional[int] = ConfigField(default=None, ge=0)

# 2. Set application-wide default config directory (optional)
ConfigManager.default_dir = "~/.my_advanced_app/config"

# 3. Register the configuration
adv_cfg_instance = ConfigManager.register("advanced_settings", AdvancedConfig, auto_save=True)

# Access active config for reading (with type hints)
active_conf = adv_cfg_instance.active
print(f"Current Port: {active_conf.server_port}")
print(f"Nullable initially: {active_conf.nullable_value}") # -> None

# 4. Set values using set_value to trigger full pipeline
adv_cfg_instance.set_value("server_port", "9000-100") # -> 8900 (eval)
adv_cfg_instance.set_value("processing_range", (5, 105)) # -> (5, 100) (range_policy clamps item)
adv_cfg_instance.set_value("selected_features", ["feature_a", "feature_x", "feature_b"]) # -> ["feature_a", "feature_b"]
adv_cfg_instance.set_value("user_ids_input", "1, 2,bad,4") # -> [1, 2, 4] (best effort conversion)
adv_cfg_instance.set_value("nullable_value", 10)
print(f"Nullable now: {adv_cfg_instance.get_value('nullable_value')}") # -> 10
adv_cfg_instance.set_value("nullable_value", None) # Setting back to None is fine
print(f"Nullable again: {adv_cfg_instance.get_value('nullable_value')}") # -> None

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

## Appendix B: Field Formats and `autofix` Behavior

This appendix details each supported `format_spec.type` and its associated `autofix` policies and `format_spec` options. The goal is to provide pre-processing for common complex input patterns before Pydantic's final validation.

---

### B.1. Numeric (Implicit)

*   **Purpose:** Standard numeric value handling with optional expression evaluation and constraint enforcement.
*   **Field Annotation:** `int`, `float`, `Decimal`, `Optional[int]`, etc.
*   **`format_spec.type`:** Not explicitly set. Inferred if numeric Pydantic constraints (`ge`, `le`, `multiple_of`) or a numeric type annotation is present and no other `format_spec.type` is defined.
*   **`format_spec.options`:** N/A (constraints come from Pydantic `Field` args like `ge`, `le`, `multiple_of`).
*   **`autofix_settings`:**
    *   `numeric_policy: NumericPolicy` (Default: `CLAMP`)
        *   `CLAMP`: Clamps to `ge`/`le` bounds. If `multiple_of` is set, rounds to the nearest multiple within bounds.
        *   `REJECT`: If outside `ge`/`le` or not a multiple of `multiple_of`, the original unprocessed value for the field is passed to Pydantic.
        *   `BYPASS`: Skips numeric auto-fixing.
    *   `eval_expressions: bool` (Default: `False`)
        *   If `True` and input is a string, attempts `_safe_eval`.
*   **Behavior:**
    1.  If `eval_expressions` is `True` and input is a string, attempt safe evaluation.
    2.  Attempt coercion to the field's numeric type.
    3.  Apply `NumericPolicy` based on `ge`/`le`/`multiple_of` constraints.
    4.  If field is `Optional` and input is `None`, `None` is preserved and processing stops here.

---

### B.2. Options (Single Choice String - Implicit)

*   **Purpose:** Handling fields where the value must be one of a predefined set of string options.
*   **Field Annotation:** `str`, `Optional[str]`, `Literal["opt1", "opt2"]`.
*   **`format_spec.type`:** Not explicitly set. Inferred if `json_schema_extra.options: List[str]` is present and the field is typically `str`, and not handled by `multiple_choice` format.
*   **`format_spec.options`:** N/A (options come from `json_schema_extra.options`).
*   **`autofix_settings`:**
    *   `options_policy: OptionsPolicy` (Default: `NEAREST`)
        *   `NEAREST`: If input string is not in `options`, attempts `difflib.get_close_matches`. If a good match is found, it's used. Otherwise, original value.
        *   `REJECT`: If input string is not in `options`, original value is passed.
        *   `BYPASS`: Skips options auto-fixing.
*   **Behavior:**
    1.  If input is already in `options`, it's considered valid by this fixer.
    2.  Apply `OptionsPolicy`.
    3.  If field is `Optional` and input is `None`, `None` is preserved.

---

### B.3. Range

*   **Purpose:** Representing a bounded interval with two numeric values (e.g., a min-max pair).
*   **Field Annotation:** `Tuple[N, N]` (e.g., `Tuple[int, int]`, `Tuple[float, float]`).
*   **`format_spec.type`:** `"range"`
*   **`format_spec.options`:**
    *   `item_type: Literal["int", "float"]` (Required): The numeric type of the range's start and end points.
    *   `min_item_value: Optional[Union[int, float]]`: Global minimum constraint for both items in the range.
    *   `max_item_value: Optional[Union[int, float]]`: Global maximum constraint for both items.
    *   `item_multiple_of: Optional[Union[int, float]]`: `multiple_of` constraint for individual items.
    *   `allow_single_value_as_range: bool` (Default: `False`): If `True`, an input like `5` becomes `(5,5)` (or `[5,5]`). If `False`, single value input is rejected by structure check.
    *   `enforce_min_le_max: bool` (Default: `True`): If `True`, ensures `range[0] <= range[1]` after individual item processing.
    *   `input_separator: Optional[str]` (Default: `None`): If provided (e.g. `"-"`, `","`), allows string input like "0-100" to be parsed into `(0, 100)`.
*   **`autofix_settings`:**
    *   `range_policy: RangePolicy` (Enum, e.g., `CLAMP_ITEMS`, `REJECT_IF_INVALID_STRUCTURE`, `REJECT_IF_ITEMS_INVALID`, `SWAP_IF_REVERSED_AND_VALID`, `BYPASS`)
*   **Behavior:**
    1.  **Input Parsing:**
        *   If `input_separator` is defined and input is a string, attempt to split and parse into two numeric values.
        *   If `allow_single_value_as_range` is `True` and input is a single number, convert to `(num, num)`.
    2.  **Structure Validation:** Check if input is a 2-element list/tuple. If not, and not parsed successfully above, apply `REJECT_IF_INVALID_STRUCTURE` or pass.
    3.  **Item Coercion & Validation:** For each item in the pair:
        *   Coerce to `item_type`.
        *   Apply `min_item_value`, `max_item_value`, `item_multiple_of` based on `range_policy` (e.g., clamp or reject individual items).
    4.  **Order Enforcement:** If `enforce_min_le_max` is `True`:
        *   If `range[0] > range[1]`:
            *   If `range_policy` allows swapping (e.g., `SWAP_IF_REVERSED_AND_VALID`), swap them.
            *   Otherwise, mark for rejection or pass original.
    5.  Return the processed tuple or original value based on policy outcomes.
    6.  Handles `Optional[Tuple[N,N]]` if input is `None`.

---

### B.4. Multiple Choice

*   **Purpose:** Allowing selection of zero or more items from a predefined list of options.
*   **Field Annotation:** `List[T]` (e.g., `List[str]`, `List[int]`). `T` should match type of items in `options`.
*   **`json_schema_extra.options: List[T]`** (Required): The pool of available choices.
*   **`format_spec.type`:** `"multiple_choice"`
*   **`format_spec.options`:**
    *   `min_selections: Optional[int]` (Default: 0).
    *   `max_selections: Optional[int]` (Default: `len(options)`).
    *   `allow_duplicates: bool` (Default: `False`): If `False`, duplicate selections are removed (first occurrence kept).
    *   `input_separator: Optional[str]` (Default: `None`): If input is a string (e.g., "apple,banana"), use this to split it into a list of strings before matching against options. Item types in `options` must be string if this is used.
*   **`autofix_settings`:**
    *   `multiple_choice_policy: MultipleChoicePolicy` (Enum, e.g., `REMOVE_INVALID_CHOICES`, `REJECT_IF_ANY_INVALID`, `REJECT_IF_COUNT_INVALID`, `BYPASS`)
*   **Behavior:**
    1.  **Input Normalization:**
        *   If `input_separator` is defined and input is a string, split it.
        *   Ensure input is a list. If not (e.g. single item not in a list), wrap it if policy allows, or reject.
    2.  **Item Validation & Filtering:**
        *   If not `allow_duplicates`, make items unique.
        *   Iterate through input items. Check if each item exists in `json_schema_extra.options`.
        *   Apply `multiple_choice_policy`:
            *   `REMOVE_INVALID_CHOICES`: Build a new list of only valid items.
            *   `REJECT_IF_ANY_INVALID`: If any item is not in `options`, the entire input is marked for rejection.
    3.  **Count Validation:** Check `min_selections` and `max_selections` against the count of valid selected items. If violated, apply policy (e.g., `REJECT_IF_COUNT_INVALID`).
    4.  Return the processed list or original value.
    5.  Handles `Optional[List[T]]` if input is `None`.

---

### B.5. List Conversion (Generic String/List to Typed List)

*   **Purpose:** Converting a string (e.g., CSV) or a list of raw values into a list of a specific, validated type.
*   **Field Annotation:** `List[T]` (e.g., `List[int]`, `List[float]`, `List[str]`, `List[bool]`).
*   **`format_spec.type`:** E.g., `"string_to_list"`, `"list_to_typed_list"`. Could be one versatile `"list_conversion"` type.
*   **`format_spec.options`:**
    *   `input_is_string: bool` (Default: `False`): If `True`, expects string input that needs splitting.
    *   `input_separator: str` (Default: `","`): Used if `input_is_string` is `True`.
    *   `item_type: Literal["int", "float", "str", "bool"]` (Required): Target type for list items.
    *   `strip_items: bool` (Default: `True`): Strip whitespace from split string items before coercion (if `input_is_string`).
    *   **Item-level constraints (applied after coercion to `item_type`):**
        *   If `item_type` is numeric: `item_ge`, `item_le`, `item_multiple_of`.
        *   If `item_type` is string: `item_min_length`, `item_max_length`, `item_pattern`.
        *   `item_options: Optional[List[Any]]` (For items that must be one of specified options).
    *   `min_items: Optional[int]`: Minimum length of the resulting list.
    *   `max_items: Optional[int]`: Maximum length of the resulting list.
    *   `allow_duplicates: bool` (Default: `True`): If `False`, resulting list will have unique items.
*   **`autofix_settings`:**
    *   `list_conversion_policy: ListConversionPolicy` (Enum, e.g., `CONVERT_OR_REJECT`, `CONVERT_BEST_EFFORT`, `BYPASS`)
    *   `item_numeric_policy: NumericPolicy` (If `item_type` is numeric, for `item_ge/le/multiple_of`).
    *   `item_options_policy: OptionsPolicy` (If `item_options` are provided).
*   **Behavior:**
    1.  **Input Preparation:**
        *   If `input_is_string` is `True`: Split string by `input_separator`. If `strip_items`, strip.
        *   Ensure input is now a list.
    2.  **Item Processing Loop:** For each item in the (potentially split) input list:
        *   Coerce to `item_type`. If fails, handle based on `list_conversion_policy` (e.g., discard item for `CONVERT_BEST_EFFORT`, or mark entire list for rejection for `CONVERT_OR_REJECT`).
        *   Apply item-level constraints (`item_ge/le`, `item_min_length`, `item_options`) using associated item-level policies. If an item fails its constraints, handle based on `list_conversion_policy`.
    3.  **List-level Adjustments:**
        *   If not `allow_duplicates`, make the list of successfully processed items unique.
    4.  **List Length Validation:** Check `min_items`/`max_items` against the final processed list. If violated, handle per `list_conversion_policy`.
    5.  Return the fully processed list or original value.
    6.  Handles `Optional[List[T]]` if input is `None`.

---

### B.6. Datetime String

*   **Purpose:** Parsing string inputs into `datetime.datetime`, `datetime.date`, or `datetime.time` objects, with format validation.
*   **Field Annotation:** `datetime.datetime`, `datetime.date`, `datetime.time`, or `Optional` versions.
*   **`format_spec.type`:** `"datetime_string"`
*   **`format_spec.options`:**
    *   `target_type: Literal["datetime", "date", "time"]` (Required, or inferred from field annotation).
    *   `formats: List[str]` (Optional, e.g., `["%Y-%m-%d %H:%M:%S", "%Y/%m/%d"]`): List of `strptime` format codes to try. If not provided, tries common ISO formats or relies on Pydantic's default parsing.
    *   `default_timezone: Optional[str]` (e.g., "UTC", "America/New_York"): If input string is naive, localize to this timezone. Requires `pytz` or `zoneinfo` (Python 3.9+).
    *   `output_timezone: Optional[str]`: Convert parsed datetime to this timezone.
    *   Constraints (applied after successful parsing):
        *   `min_datetime: Optional[str | datetime]` (Parsable datetime string or datetime object).
        *   `max_datetime: Optional[str | datetime]`.
*   **`autofix_settings`:**
    *   `datetime_policy: DatetimePolicy` (Enum, e.g., `PARSE_FIRST_SUCCESSFUL_FORMAT`, `REJECT_IF_NO_FORMAT_MATCHES`, `REJECT_IF_CONSTRAINTS_VIOLATED`, `CLAMP_TO_CONSTRAINTS` (if sensible), `BYPASS`)
*   **Behavior:**
    1.  If input is already a `datetime` object of the correct type, may apply constraints or bypass.
    2.  If input is a string:
        *   Try parsing with each format in `formats`. If `formats` is empty, use a default set of parsers (e.g., ISO).
        *   If parsing succeeds:
            *   Apply `default_timezone` if datetime is naive.
            *   Apply `min_datetime`/`max_datetime` constraints based on `datetime_policy`.
            *   Apply `output_timezone` conversion.
            *   Return the `datetime` object.
    3.  If parsing fails for all formats, or constraints are violated and policy is `REJECT`, mark for rejection.
    4.  Handles `Optional` field if input is `None`.

---

### B.7. Multiple Ranges (List of Ranges)

*   **Purpose:** Representing a list of range intervals.
*   **Field Annotation:** `List[Tuple[N, N]]` (e.g., `List[Tuple[int, int]]`).
*   **`format_spec.type`:** `"multiple_ranges"`
*   **`format_spec.options`:**
    *   All options from **B.3. Range** prefixed with `item_range_` (e.g., `item_range_item_type`, `item_range_min_item_value`, `item_range_enforce_min_le_max`).
    *   `min_ranges: Optional[int]`: Minimum number of range tuples in the list.
    *   `max_ranges: Optional[int]`: Maximum number of range tuples.
    *   `allow_overlapping_ranges: bool` (Default: `True`). If `False`, validates that ranges in the list do not overlap.
    *   `sort_ranges: bool` (Default: `False`): If `True`, sorts the list of ranges by their start points.
    *   `input_separator_list: str` (Default: `;` or `|`): Separator for string input representing multiple ranges (e.g., "0-10;20-30").
    *   `input_separator_range: str` (Default: `-`): Separator within each range string (passed to individual range parser).
*   **`autofix_settings`:**
    *   `multiple_ranges_policy: MultipleRangesPolicy` (Enum, e.g., `PROCESS_ITEMS_BEST_EFFORT`, `REJECT_IF_ANY_ITEM_INVALID`, `REJECT_IF_LIST_CONSTRAINTS_VIOLATED`, `BYPASS`)
    *   `item_range_policy: RangePolicy` (Policy to apply to each individual range tuple, see B.3).
*   **Behavior:**
    1.  **Input Parsing:** If input is a string, split by `input_separator_list`. Each part is then parsed as an individual range (using `input_separator_range` and `item_range_*` options).
    2.  **Individual Range Processing:** For each potential range in the list:
        *   Apply the logic from **B.3. Range** using `item_range_*` options and `item_range_policy`.
        *   Collect successfully processed ranges. Handle failures based on `multiple_ranges_policy`.
    3.  **List-level Validation:**
        *   Apply `min_ranges`/`max_ranges`.
        *   If `sort_ranges`, sort the list.
        *   If not `allow_overlapping_ranges`, check for overlaps.
    4.  Return the processed list of range tuples or original value.
    5.  Handles `Optional[List[Tuple[N,N]]]` if input is `None`.

---

### B.8. Boolean String/Numeric

*   **Purpose:** Flexible parsing of boolean values from strings (e.g., "yes", "True", "1") or numbers (0, 1).
*   **Field Annotation:** `bool`, `Optional[bool]`.
*   **`format_spec.type`:** `"boolean_flexible"`
*   **`format_spec.options`:**
    *   `true_values: List[Union[str, int, float]]` (Default: `["true", "yes", "on", "1", 1, 1.0]`). Case-insensitive for strings.
    *   `false_values: List[Union[str, int, float]]` (Default: `["false", "no", "off", "0", 0, 0.0]`). Case-insensitive for strings.
*   **`autofix_settings`:**
    *   `boolean_policy: BooleanPolicy` (Enum, e.g., `STRICT_MATCH`, `REJECT_IF_UNRECOGNIZED`, `BYPASS`)
*   **Behavior:**
    1.  If input is already a Python `bool`, it's used directly.
    2.  Convert input to lowercase if string.
    3.  Check if input is in `true_values`. If yes, result is `True`.
    4.  Check if input is in `false_values`. If yes, result is `False`.
    5.  If not found in either and policy is `REJECT_IF_UNRECOGNIZED`, mark for rejection.
    6.  Handles `Optional[bool]` if input is `None`.

---

### B.9. File/Directory Path

*   **Purpose:** Validating strings as file or directory paths with existence/type checks.
*   **Field Annotation:** `pathlib.Path`, `str`, `Optional[...]`.
*   **`format_spec.type`:** `"path_string"`
*   **`format_spec.options`:**
    *   `path_type: Literal["file", "dir", "any"]` (Default: `"any"`).
    *   `must_exist: bool` (Default: `False`).
    *   `resolve_path: bool` (Default: `True`): If `True`, converts to an absolute path.
    *   `expand_user: bool` (Default: `True`): If `True`, expands `~`.
    *   `allowed_extensions: Optional[List[str]]` (e.g., `[".txt", ".csv"]`). Case-insensitive. Only if `path_type` is `"file"`.
    *   `base_path: Optional[str | Path]` (Default: `None`): If provided, relative paths are resolved against this base.
*   **`autofix_settings`:**
    *   `path_policy: PathPolicy` (Enum, e.g., `VALIDATE_ONLY`, `REJECT_IF_INVALID`, `BYPASS`)
*   **Behavior:**
    1.  If input is already a `Path` object, use it. If string, convert to `Path`.
    2.  If `expand_user`, expand it.
    3.  If `base_path` is given and path is relative, join with base.
    4.  If `resolve_path`, resolve it (makes absolute, resolves symlinks).
    5.  If `must_exist`:
        *   Check `path.exists()`.
        *   If `path_type == "file"`, check `path.is_file()`.
        *   If `path_type == "dir"`, check `path.is_dir()`.
        *   If checks fail, mark for rejection based on policy.
    6.  If `path_type == "file"` and `allowed_extensions` are provided, check suffix. If no match, mark for rejection.
    7.  Return `Path` object (or string if original annotation was string and policy allows) or original value.
    8.  Handles `Optional` field if input is `None`.

---
**(General Note on all format fixers):** Each fixer should be designed to gracefully handle `None` input if the field's Pydantic annotation is `Optional`. Typically, if `None` is received for an optional field, the fixer should return `(FixStatusEnum.PROCESSED_UNMODIFIED, None)` or `(FixStatusEnum.BYPASSED, None)` without further processing, unless the format specifically targets `None` values. The `PydanticUndefined` value from `raw_data_dict.get()` should also be handled to ensure defaults are respected.