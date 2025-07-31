# Dynamic Config Manager - Developer Specification (v2.2)

## 1. Introduction

### 1.1. Project Goal
To create a Python package, `dynamic-config-manager`, providing a robust, typed, and file-backed configuration framework. It wraps Pydantic (v2) `BaseSettings` to offer dynamic loading, updating, saving, validation, and management of application configurations, with advanced pre-processing capabilities for various data formats.

### 1.2. Core Philosophy
*   **Pydantic-centric:** Leverage Pydantic V2 for model definition, type checking, and core validation.
*   **Typed:** Emphasize strong typing for configuration clarity and safety, with enhanced Pylance/LSP support.
*   **User-friendly & Intuitive:** Simple API for common tasks, with powerful customization options, including an optional custom base class and field constructor for easier definition and attribute-based access.
*   **Explicit over Implicit:** Clear control over persistence, saving, and validation behaviors.
*   **Separation of Concerns:** `attach_auto_fix` pre-processes data based on defined formats and policies; Pydantic performs final validation against the model's type annotations and constraints.

### 1.3. Key Features Summary
*   Configuration definition via Pydantic `BaseSettings` models, or an optional enhanced `DynamicBaseSettings` with a `ConfigField` helper for convenience.
*   Singleton `ConfigManager` for centralized management of multiple configurations.
*   Default save directory management with per-config overrides.
*   Opt-in/out persistence for configurations (memory-only or file-backed).
*   Support for JSON (default), YAML, and TOML file formats.
*   **Enhanced Access Methods:**
    *   Path-based deep access (`get_value("path.to.value")`, `set_value("path.to.value", ...)`) for configuration values, using `.` as a delimiter.
    *   Attribute-style access via `config_instance.active.path.to.value` for both getting (triggers `get_value`) and setting (triggers `set_value`) values, ensuring full validation and auto-save pipeline.
    *   Easy metadata retrieval for any field via `config_instance.meta.path.to.value` (or `get_metadata("path.to.value")`) returning a comprehensive metadata object.
*   Automatic validation and (optional) auto-saving on value changes made through `set_value` or attribute-style assignment.
*   Restore functionality for individual values or entire configurations to defaults or file-persisted state.
*   `attach_auto_fix` decorator for Pydantic models to enable input pre-processing for various data formats (numeric, options, ranges, multiple choice, list conversions, etc.):
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
*   **Runtime Model Updates:** Support for programmatically updating field definitions (e.g., constraints, defaults) of a registered configuration model at runtime.

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
|  Model; Provides  |                       +-----------------+
|  Access Wrappers) |
+-------------------+
         | Modifies via set_value() / active proxy
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
*   **2.2.3. `ConfigInstance` (Managed configuration object):** Represents and manages a single, typed configuration, and provides enhanced access wrappers (`.active`, `.meta`).
*   **2.2.4. Validation Subsystem (`attach_auto_fix` and helpers):** Provides pre-processing logic.
*   **2.2.5. (Optional) `DynamicBaseSettings` and `ConfigField`:** Convenience tools for defining models.
*   **2.2.6. Accessor Proxies (within `ConfigInstance`):** Internal generic classes to enable type-hinted attribute-style get/set and metadata access.

## 3. Component Deep Dive

### 3.1. Pydantic Configuration Models & `DynamicBaseSettings`
*   **3.1.1. Definition:** Users define configurations by inheriting from `dynamic_config_manager.BaseSettings` or the recommended `dynamic_config_manager.DynamicBaseSettings`.
*   **3.1.2. `DynamicBaseSettings(BaseSettings)`:**
    *   An optional base class. May provide common `model_config` or helper methods. Serves as a clear entry point for using `ConfigField`.
*   **3.1.3. `ConfigField(...)` function:**
    *   A wrapper around Pydantic's `Field` to simplify setting `json_schema_extra` with structured keys for `dynamic-config-manager` features. Uses `pydantic.PydanticUndefined` for default values not explicitly provided.
    *   **Signature (Conceptual):**
        ```python
        from typing import Any, Optional, List, Dict, Union, TypeVar, Generic
        from enum import Enum
        from pydantic import PydanticUndefined # For ConfigField default

        def ConfigField(
            default: Any = PydanticUndefined,
            *,
            # All standard pydantic.Field arguments (description, ge, le, etc.)
            # ... (e.g., title, examples, frozen, validate_default, repr, init_var, kw_only)
            description: Optional[str] = None,
            ge: Optional[float] = None,
            le: Optional[float] = None,
            gt: Optional[float] = None,
            lt: Optional[float] = None,
            multiple_of: Optional[float] = None,
            min_length: Optional[int] = None,
            max_length: Optional[int] = None,
            pattern: Optional[str] = None,
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
    *   `update_model_field(config_name: str, field_path: str, new_field_definition: FieldInfo)`:
        *   Allows runtime modification of a field within a registered model.
        *   `config_name`: Name of the `ConfigInstance`.
        *   `field_path`: Dot-separated path to the field (e.g., "parent.child.field_name").
        *   `new_field_definition`: A Pydantic `FieldInfo` object representing the new field definition (could be created using `pydantic.Field` or our `ConfigField`).
        *   **Mechanism:**
            1.  Retrieves the `ConfigInstance` and its current `_model_cls`.
            2.  To update a field in potentially nested models, recursively traverse the `_model_cls` structure based on `field_path` to find the target model class and field name.
            3.  Create a *candidate* new model class:
                *   Make a copy of the target model class's `model_fields`.
                *   Replace the specific field's `FieldInfo` in this copied dictionary with `new_field_definition`.
                *   Use `pydantic.create_model` or similar dynamic model creation techniques to generate a new model type with the updated fields, ensuring it inherits from the same base as the original target model class. If the target is the top-level model, this is more straightforward. If nested, the parent model's field annotation for this nested model needs to be updated to this new candidate type. This implies rebuilding the parent model class as well, potentially up to the `_model_cls` of the `ConfigInstance`.
            4.  Call `model_rebuild(force=True)` on the (potentially new top-level) candidate model class.
            5.  **Validation & Atomicity:**
                *   Attempt to instantiate the candidate model with `ConfigInstance._active.model_dump()`. If this raises `ValidationError`, the update is considered failed, and the `ConfigInstance`'s `_model_cls`, `_active`, and `_defaults` remain unchanged. Log an error.
                *   If successful, create a new `_defaults` instance using the (potentially new top-level) candidate model.
                *   Atomically update `ConfigInstance._model_cls` to the candidate model class, `ConfigInstance._active` to the re-validated instance, and `ConfigInstance._defaults` to the new defaults.
            6.  This is an advanced operation. If it fails at any validation step, the `ConfigInstance` state must remain consistent with the pre-update state.
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
*   **Accessor Proxies (Internal):**
    *   `_ActiveAccessorProxy(Generic[T_Model])`: Returned by `ConfigInstance.active`. Intercepts `__getattr__` and `__setattr__`. It holds a reference to the parent `ConfigInstance` and the current path prefix.
    *   `_MetaAccessorProxy(Generic[T_Model])`: Returned by `ConfigInstance.meta`. Intercepts `__getattr__`. It holds a reference to the parent `ConfigInstance` and the current path prefix.
*   **Properties:**
    *   `active: _ActiveAccessorProxy[T]`: (Where `T` is `self._model_cls`)
        *   Returns an instance of `_ActiveAccessorProxy` bound to this `ConfigInstance`, initialized with an empty path prefix.
        *   **Getting Values:** `val = config_instance.active.path.to.value` internally calls `self.get_value("path.to.value")`. For nested models (e.g., `config_instance.active.parent`), `__getattr__` on the proxy returns another `_ActiveAccessorProxy` instance, appending "parent" to its internal path prefix, effectively scoping it to that parent model.
        *   **Setting Values:** `config_instance.active.path.to.value = new_val` internally calls `self.set_value("path.to.value", new_val)`.
        *   Provides type hinting by proxying the underlying Pydantic model `T`. The type hinting will rely on Pydantic's model structure.
    *   `meta: _MetaAccessorProxy[T]`:
        *   Returns an instance of `_MetaAccessorProxy` bound to this `ConfigInstance`, initialized with an empty path prefix.
        *   `metadata_dict = config_instance.meta.path.to.value` internally calls `self.get_metadata("path.to.value")`. Similar to `_ActiveAccessorProxy`, `__getattr__` on `_MetaAccessorProxy` for nested paths returns new proxy instances with updated path prefixes.
*   **Value Manipulation:**
    *   `get_value(path: str) -> Any`: Path uses `.` as delimiter (e.g., `"foo.bar.0.baz"`).
        *   Retrieves a value from the `_active` model using a path string.
        *   Uses `_deep_get` helper for traversal.
    *   `set_value(path: str, value: Any)`: Path uses `.` as delimiter.
        *   Sets a value in the `_active` model using a path string.
        *   First, checks field metadata (using `get_metadata(path)`): if `json_schema_extra.get("editable")` is `False` for the target field, raises `PermissionError`.
        *   Uses `_deep_set` to construct a data structure representing the new state of the model.
        *   Creates a new model instance: `self._active = self._model_cls(**new_model_data_structure)`. This step triggers Pydantic validation, including any `attach_auto_fix` `model_validator`.
        *   If Pydantic validation fails, raises `ValueError` wrapping the `ValidationError`.
        *   If successful and `self._auto_save` is `True`, calls `self.persist()`.
*   **Helper: `_deep_get` and `_deep_set` (Internal to `manager.py`):**
    *   These internal helpers must use `.` as the key separator for splitting the path string into a list of keys.
    *   They should robustly handle numeric strings in paths (e.g., "items.0.name") as list indices when traversing.
*   **Metadata:**
    *   `get_metadata(path: str) -> Dict[str, Any]`: Path uses `.` as delimiter.
        *   Retrieves comprehensive metadata for a field specified by a path string.
        *   The process involves introspecting `self._model_cls` down the `path` segments.
        *   **Enhanced in v1.1+** to return a dictionary including:
            *   `type` (annotation), `required`, `default` (from `FieldInfo`)
            *   `description` (field description from `FieldInfo.description`)
            *   `editable` (from `json_schema_extra`, defaults to `True`)
            *   `json_schema_extra` (complete field metadata dictionary copy)
            *   **Flattened common attributes** for convenience access:
                *   `ui_hint`, `ui_extra`, `options`, `format_spec` (from `json_schema_extra`)
                *   `autofix_settings` (mapped from `json_schema_extra["autofix"]`)
            *   Pydantic constraints (`ge`, `le`, etc.) extracted via `_extract_constraints`
    *   **Enhancement:** The dictionary returned by `get_metadata(path)` will also include:
        *   `active_value: Any` (current value from `_active` at `path`, obtained via `_deep_get(self._active, path.split('.'))`).
        *   `default_value: Any` (value from `_defaults` at `path`, obtained via `_deep_get(self._defaults, path.split('.'))`).
        *   `saved_value: Any` (Value loaded from the persisted file for this specific path. This might involve loading the file if not recently cached, then using `_deep_get`. Could be a sentinel like `PydanticUndefined` if the file doesn't exist or the path is not in the file).
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
        *   If `_save_path` exists and is a file, loads data from it using `_load_file`.
        *   Instantiates `_model_cls` with the loaded data.
        *   If loading or validation fails (e.g. `ValidationError`, `JSONDecodeError`), logs a warning and returns `None` (leading to use of defaults).
*   **Restore Operations:**
    *   `restore_value(path: str, source: str = "default")`: # path uses `.` delimiter, source: Literal["default", "file"]
        *   Restores a single value at `path` to its state from the specified `source`.
        *   `source="default"`: Uses value from `_defaults` (via `_deep_get(self._defaults, path.split('.'))`).
        *   `source="file"`: Reloads from disk (or uses `_defaults` if file load fails) and gets value from there (via `_deep_get`).
        *   Calls `set_value()` with the restored value, so validation and auto-save apply.
    *   `restore_defaults()`:
        *   Resets `_active` to a deep copy of `_defaults` (`self._defaults.model_copy(deep=True)`).
        *   If `_auto_save` is `True`, calls `self.persist()`.

### 3.4. Validation Subsystem (`validation.py`)
*Provides the `attach_auto_fix` decorator and helper functions for input pre-processing.*

*   **3.4.1. `attach_auto_fix` Decorator**
    *   **Signature (Conceptual - actual policy types will be Enums):**
        ```python
        from typing import Type, TypeVar, Optional, Union, Literal
        from enum import Enum
        from pydantic import BaseModel

        T_Model = TypeVar("T_Model", bound=BaseModel)

        def attach_auto_fix(
            _cls: Optional[Type[T_Model]] = None,
            *,
            numeric_policy: Union[str, NumericPolicy] = "clamp", # type: ignore
            options_policy: Union[str, OptionsPolicy] = "nearest", # type: ignore # For single-choice string options
            eval_expressions: bool = False,
            # Default policies for new formats:
            range_policy: Union[str, RangePolicy] = "reject_if_invalid", # type: ignore # e.g. "clamp_items"
            multiple_choice_policy: Union[str, MultipleChoicePolicy] = "remove_invalid", # type: ignore # e.g. "reject_if_any_invalid"
            list_conversion_policy: Union[str, ListConversionPolicy] = "convert_or_reject", # type: ignore # e.g. "convert_best_effort"
            # General fallback behavior for unhandled types or generic issues:
            default_string_policy: str = "bypass", # e.g. strip, lower (if generic string ops added)
        ) -> Union[Callable[[Type[T_Model]], Type[T_Model]], Type[T_Model]]: # type: ignore
        ```
    *   **Mechanism:** Attaches a Pydantic `model_validator(mode="before")` to the decorated class.
    *   **Per-field Override:** The model validator checks `field_info.json_schema_extra.get("autofix", {})` for overrides to these global policies.
*   **3.4.2. Policies (Enums):**
    *   `NumericPolicy(str, Enum)`: `CLAMP`, `REJECT`, `BYPASS`.
    *   `OptionsPolicy(str, Enum)`: `NEAREST`, `REJECT`, `BYPASS` (for single string option matching).
    *   **New Policies (Examples - to be defined):**
        *   `RangePolicy(str, Enum)`: `CLAMP_ITEMS` (clamp items to `item_min/max_value` if specified in `format_spec`), `REJECT_IF_INVALID_STRUCTURE`, `REJECT_IF_ITEMS_INVALID`, `SWAP_IF_MIN_GT_MAX_AND_VALID`, `BYPASS`.
        *   `MultipleChoicePolicy(str, Enum)`: `REMOVE_INVALID_CHOICES` (keep valid ones), `REJECT_IF_ANY_INVALID`, `REJECT_IF_COUNT_INVALID` (violates `min/max_selections`), `BYPASS`.
        *   `ListConversionPolicy(str, Enum)`: `CONVERT_OR_REJECT` (entire field rejected if any item fails conversion/validation), `CONVERT_BEST_EFFORT` (convert valid items, discard/replace invalid ones based on sub-policy), `BYPASS`.
    *   `FixStatusEnum(Enum)`: `PROCESSED_MODIFIED`, `PROCESSED_UNMODIFIED`, `BYPASSED`, `REJECTED_BY_POLICY`, `FAILED_PREPROCESSING`.
    *   All policy sets should include `REJECT` and `BYPASS` variants where applicable.
*   **3.4.3. Core Logic (The `model_validator` function injected by `attach_auto_fix`):**
    *   Receives `raw_data_dict` (input to the model).
    *   Creates `fixed_data = {}`.
    *   Iterates `name, field_info` in `cls.model_fields.items()`:
        1.  `original_value = raw_data_dict.get(name, PydanticUndefined)` (Handle cases where field might not be in input, relying on Pydantic defaults).
        2.  If `original_value is PydanticUndefined` and field has a default or is `Optional`, skip `autofix` for this field unless specific policy dictates otherwise (e.g. "process_defaults"). Generally, `autofix` acts on provided input. If `original_value is PydanticUndefined` and field is required without default, Pydantic will handle this.
        3.  Determine `effective_autofix_policies` and `format_spec` from global decorator args and `field_info.json_schema_extra`.
        4.  `processed_value = original_value`.
        5.  **Handle `None`:** If `original_value is None` and `field_info.annotation` permits `None` (e.g., `Optional[T]`, `Union[T, None]`), `processed_value` remains `None` and most subsequent auto-fixing steps are bypassed for this value, unless a specific policy targets `None` values (e.g., "replace_none_with_default_if_not_optional"). The status returned by fixers should reflect this (e.g., `PROCESSED_UNMODIFIED`).
        6.  **Dispatch based on `format_spec.get("type")` or field type:**
            *   If `format_spec.type == "range"`: Call `_run_range_autofix(processed_value, policies, format_spec, field_info)`.
            *   If `format_spec.type == "multiple_choice"`: Call `_run_multichoice_autofix(...)`.
            *   If `format_spec.type == "csv_to_list_int"` (example, or generic list converter): Call `_run_list_conversion_autofix(...)`.
            *   (Other `format_spec` types...)
            *   **Else (no specific format_spec or it's a basic type):**
                *   **Numeric Processing:** If field appears numeric (based on annotation or constraints like `ge`/`le`/`multiple_of`):
                    *   Apply expression evaluation if `eval_expressions` is true and `processed_value` is a string. Update `processed_value` with result or keep original string if eval fails.
                    *   Attempt coercion of `processed_value` to the target numeric type (derived from `field_info.annotation`).
                    *   Apply `NumericPolicy` (clamp/reject/bypass) using `ge/le/multiple_of` constraints from `field_info.metadata`.
                *   **Options Processing (single choice):** If `options` are in `json_schema_extra` (and not handled by `multiple_choice` format):
                    *   Apply `OptionsPolicy` (nearest/reject/bypass).
                *   **String Length Processing:** If `processed_value` is a string and `min_length`/`max_length` are defined from `field_info.metadata`:
                    *   This is primarily a Pydantic concern. `attach_auto_fix` might offer a pre-check. If `numeric_policy` (repurposed for this context or a new `length_policy`) is `REJECT` and length constraints are violated, this step could flag it. Otherwise, Pydantic handles length validation.
        7.  **Result Handling from Fixers:** Each `_run_..._autofix` helper (or inline logic) should conceptually yield `(status: FixStatusEnum, value: Any)`.
            *   If status is `REJECTED_BY_POLICY` or `FAILED_PREPROCESSING`, then `fixed_data[name] = original_value` (pass the raw input for this field to Pydantic for its validation).
            *   Otherwise, `fixed_data[name] = value` (the processed or bypassed value).
    *   Fields from `raw_data_dict` that are not part of `cls.model_fields` are passed through (Pydantic will handle them based on `model_config`, e.g., `extra='ignore'/'forbid'`).
    *   Returns `fixed_data` to Pydantic.
*   **3.4.4. Specific Auto-Fix Helper Functions (Conceptual):**
    *   `_run_numeric_autofix(...)`: Includes `_safe_eval`. Handles `None` inputs gracefully if field is `Optional`.
    *   `_run_options_autofix(...)`: For single string choice.
    *   `_run_range_autofix(...)`: Validates tuple/list structure, item types, bounds, applies `RangePolicy`.
    *   `_run_multichoice_autofix(...)`: Validates against `options`, selection counts, applies `MultipleChoicePolicy`.
    *   `_run_list_conversion_autofix(...)`: Parses input (e.g., CSV string), converts items, validates items, applies `ListConversionPolicy`.
    *   (Other helpers for formats in Appendix B)
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
    *   `_load_file(path: Path, *, file_format: Optional[str] = None) -> Dict[str, Any]`: Reads and parses the file. Handles potential `ImportError` if optional dependencies (PyYAML, tomli) are not installed for the requested format.
    *   `_dump_file(path: Path, data: Dict[str, Any], *, file_format: Optional[str] = None)`: Dumps data to the file, pretty-printed for JSON/YAML. Handles potential `ImportError` for optional dependencies (PyYAML, tomli-w).
*   **4.4. Dependencies for File Formats:**
    *   YAML: `PyYAML` (`pip install pyyaml`)
    *   TOML Read: `tomli` (`pip install tomli`) - for Python < 3.11 (Python 3.11+ has `tomllib` in stdlib)
    *   TOML Write: `tomli-w` (`pip install tomli-w`)
    *   These should be optional dependencies (extras syntax in `pyproject.toml`, e.g., `dynamic-config-manager[yaml,toml]`). The file I/O helpers should gracefully handle `ImportError` and raise an informative error if a format is requested but its dependency is missing.

## 5. Data Flow and Validation Sequence
*   **For `ConfigInstance.set_value("path.to.value", new_val)`:**
    1.  Application calls `config_instance.set_value("path.to.value", new_val)`.
    2.  Path is split by `.` for `_deep_set`.
    3.  `ConfigInstance` checks if field at `path` is editable via `get_metadata()`. Raises `PermissionError` if not.
    4.  `_deep_set(config_instance._active, path.split("."), new_value)` is called. This returns a new data structure (often a Pydantic model instance if top-level, or dict/list for nested parts) with the proposed change.
    5.  The result from `_deep_set` is effectively used to construct the `raw_data_dict` for model re-instantiation. If `_deep_set` returns a model, `model_dump(mode="python")` is used.
    6.  `config_instance._active = config_instance._model_cls(**raw_data_dict)` is called. This triggers full Pydantic model instantiation.
        *   **6.a. `attach_auto_fix` Pre-processing:** The `model_validator(mode="before")` (defined by `attach_auto_fix`) runs first on `raw_data_dict`.
            *   It iterates through fields.
            *   Applies relevant fixing logic (expression evaluation, numeric, options, advanced formats, length checks) based on policies.
            *   If a fixer determines a value should be rejected or cannot be processed (status `REJECTED_BY_POLICY` or `FAILED_PREPROCESSING`), it passes the original input value for that field to Pydantic. Otherwise, it passes the (potentially) modified value.
            *   The `model_validator` constructs a `fixed_data_dict`.
            *   This `fixed_data_dict` is returned to Pydantic.
        *   **6.b. Pydantic Standard Validation:** Pydantic processes `fixed_data_dict`.
            *   Performs type coercion/validation for each field.
            *   Checks standard Pydantic constraints.
            *   If any validation fails, Pydantic raises `ValidationError`.
    7.  If Pydantic validation succeeds, the new model instance is assigned to `config_instance._active`.
    8.  If `config_instance._auto_save` is `True`, `config_instance.persist()` is called.
    9.  If `ValidationError` was raised at step 6.b, `ConfigInstance.set_value()` catches it and re-raises it wrapped in a `ValueError` with more context.
*   **For `config_instance.active.path.to.value = new_val` (Attribute Set):**
    1.  The `_ActiveAccessorProxy`'s `__setattr__` (or nested equivalent for `path.to.value`) is invoked.
    2.  It reconstructs the full dot-separated path string (e.g., "path.to.value").
    3.  It calls `self._config_instance_ref.set_value(full_path_string, new_val)`.
    4.  The flow then follows the `ConfigInstance.set_value()` sequence above.
*   **For `val = config_instance.active.path.to.value` (Attribute Get):**
    1.  The `_ActiveAccessorProxy`'s `__getattr__` is invoked.
    2.  It reconstructs the full dot-separated path string.
    3.  It calls `self._config_instance_ref.get_value(full_path_string)`.
    4.  The value is returned. If the attribute itself represents a nested Pydantic model (i.e., `get_value` returns a `BaseModel` instance), a new `_ActiveAccessorProxy` scoped to that nested model and updated path is returned.
*   **For `metadata = config_instance.meta.path.to.value` (Metadata Get):**
    1.  The `_MetaAccessorProxy`'s `__getattr__` is invoked.
    2.  It reconstructs the full dot-separated path string.
    3.  It calls `self._config_instance_ref.get_metadata(full_path_string)`.
    4.  The metadata dictionary is returned. If the attribute represents a nested model, a new `_MetaAccessorProxy` scoped to that nested model and updated path is returned.

## 6. Public API Summary (`__init__.py`)
The `dynamic_config_manager/__init__.py` should expose:
*   `ConfigManager` (the singleton instance)
*   `BaseSettings` (re-export from `pydantic_settings`)
*   `DynamicBaseSettings` (custom base class)
*   `ConfigField` (new field constructor function)
*   `BaseModel`, `Field`, `ValidationError` (re-exports from `pydantic`)
*   `attach_auto_fix` (from `dynamic_config_manager.validation`)
*   Policy Enums (e.g., `NumericPolicy`, `OptionsPolicy`, `RangePolicy`, `MultipleChoicePolicy`, `ListConversionPolicy`, `FixStatusEnum`, `BooleanPolicy`, `DatetimePolicy`, `PathPolicy`, `MultipleRangesPolicy`)
*   `__version__`

## 7. Error Handling Strategy
*   **Pydantic `ValidationError`:** Raised (possibly wrapped) when input data fails model validation after `attach_auto_fix` pre-processing.
*   **`ValueError`:** For invalid arguments or operations (e.g., registering duplicate config name, bad `source` in `restore_value`, invalid path format if not caught earlier).
*   **`KeyError`:** Accessing non-existent config name in `ConfigManager` or non-existent path segment in `_deep_get` (if data structure doesn't support it).
*   **`AttributeError`:** Accessing non-existent attribute via proxy if path corresponds to a non-field or `_deep_get` fails with `AttributeError`.
*   **`PermissionError`:** Attempting to set a non-editable field via `ConfigInstance.set_value()`.
*   **`TypeError`:** Incorrect type for `model_cls` during registration, or type mismatch during data processing not caught by Pydantic/autofix.
*   **File I/O Errors:** Logged warnings for non-critical issues (e.g., `_load_from_disk` failing leads to using defaults, `persist` failing is logged but doesn't crash app). Critical file system errors (e.g., permission denied on directory creation) may propagate. `ImportError` if optional I/O dependencies are missing for a requested format.

## 8. Logging
*   Use Python's standard `logging` module.
*   The library's root logger (`logging.getLogger("dynamic_config_manager")`) should have a `logging.NullHandler()` attached by default to prevent log messages if the application doesn't configure logging.
*   **Log Events:**
    *   INFO: Config registration, successful save/export.
    *   DEBUG: Memory-only config not persisted, auto-fix actions and decisions (e.g., value modified from X to Y by policy Z for field F), expression evaluation results, accessor proxy path resolutions.
    *   WARNING: Failure to load config from disk (falling back to defaults), failure to save/export config, bad data format encountered, auto-fix policy resulted in using original value due to pre-processing failure or rejection, missing optional I/O dependency for a requested format.
    *   ERROR: Critical internal errors (should be rare), failure during runtime model update if it cannot be safely rolled back.

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
from typing import Optional, Tuple, List, Any
from pathlib import Path
import datetime # For Appendix B examples if they were here
from pydantic import Field as PydanticField, PydanticUndefined, BaseModel as PydanticBaseModel # For ConfigField default and runtime update example

from dynamic_config_manager import (
    DynamicBaseSettings, ConfigField, ConfigManager, attach_auto_fix,
    NumericPolicy # Example policy enum
)

# 1. Define your configuration model
@attach_auto_fix(numeric_policy=NumericPolicy.CLAMP, eval_expressions=True)
class AppSettings(DynamicBaseSettings):
    server_port: int = ConfigField(default=8080, ge=1024, le=65535, ui_hint="SpinBox")
    log_level: str = ConfigField(default="INFO", options=["DEBUG", "INFO"], ui_hint="ComboBox")
    feature_flags: Optional[List[str]] = ConfigField(default=None, format_spec={"type": "multiple_choice"}, options=["A", "B", "C"])

    class NestedConfig(DynamicBaseSettings): # Pydantic models used for nesting
        nested_value: float = ConfigField(default=0.5, ge=0, le=1)
        deeply_nested: Optional[str] = ConfigField(default="deep")
    
    nested: NestedConfig = ConfigField(default_factory=NestedConfig)


# 2. Set default config directory
ConfigManager.default_dir = "~/.my_app_v2.2/config"

# 3. Register
app_settings = ConfigManager.register("app", AppSettings, auto_save=True)

# 4. Access and Modify using attribute style via .active
print(f"Initial Port: {app_settings.active.server_port}") 
app_settings.active.server_port = "9000 - 100" 
print(f"New Port: {app_settings.active.server_port}") # -> 8900

app_settings.active.nested.nested_value = 0.75
print(f"Nested Val: {app_settings.active.nested.nested_value}") # -> 0.75

# Using path-based set_value
app_settings.set_value("nested.deeply_nested", "new_deep_value")
print(f"Deeply nested: {app_settings.active.nested.deeply_nested}") # -> "new_deep_value"

# 5. Get metadata using .meta or get_metadata
port_meta_attr = app_settings.meta.server_port
port_meta_path = app_settings.get_metadata("server_port")
assert port_meta_attr == port_meta_path
print(f"Port Active: {port_meta_attr['active_value']}, Default: {port_meta_attr['default_value']}")
print(f"Port UI Hint: {port_meta_attr['json_schema_extra']['ui_hint']}") 
print(f"Port Max (le): {port_meta_attr['le']}") # Constraint from FieldInfo

nested_val_meta = app_settings.meta.nested.nested_value # or app_settings.get_metadata("nested.nested_value")
print(f"Nested Default: {nested_val_meta['default_value']}")


# 6. Runtime field update (Advanced - conceptual)
try:
    from pydantic.fields import FieldInfo
    # Create a new FieldInfo for server_port with an updated 'le'
    # This is a simplified way to get a FieldInfo. In practice, you might use ConfigField then extract, or build manually.
    new_field_info = FieldInfo.from_field(PydanticField(default=8000, ge=1000, le=30000, description="Updated port range"))
    
    # ConfigManager.update_model_field("app", "server_port", new_field_info) 
    
    # app_settings.active.server_port = 25000 # This would now be valid if update was successful
    # print(f"Port after model update, new value: {app_settings.active.server_port}")
    # current_le_after_update = app_settings.get_metadata("server_port")['le']
    # print(f"New Port Max from meta: {current_le_after_update}") # -> 30000
    print("Runtime model update example is conceptual and not fully run here.")
except Exception as e:
    print(f"Runtime model update example failed: {e}")
```

## Appendix A: Helper function details (`manager.py`)

*   **`_deep_get(data: Any, keys: List[str]) -> Any`**:
    Traverses nested Pydantic models, dictionaries, and lists using a list of string keys (segments of a dot-separated path). Handles attribute access for models and item access for dicts/lists (converting numeric string keys to `int` for lists). Raises `KeyError`, `AttributeError`, or `IndexError` on failure if a key is not found or an object is not subscriptable/does not have the attribute.
*   **`_deep_set(data: Any, keys: List[str], value: Any) -> BaseModel | Any`**:
    Recursively creates a *copy* of the nested structure `data` with the `value` set at the path specified by `keys` (segments of a dot-separated path).
    If `data` is a Pydantic `BaseModel`, it performs `model_dump(mode="python")` to get a dictionary representation, sets the nested value within this dictionary, and then returns a *new instance* of the model class initialized with the modified dictionary: `data.__class__(**copied_dict)`.
    If `data` is a `dict`, it returns a shallow copy with the nested value set: `{**data, keys[0]: _deep_set(data[keys[0]], keys[1:], value)}` (conceptual, actual implementation handles list indices and new key creation).
    If `data` is a `list`, it returns a shallow copy with the nested value set at the specified index: `list_copy = list(data); list_copy[int(keys[0])] = _deep_set(data[int(keys[0])], keys[1:], value); return list_copy`.
    This ensures that modifications trigger Pydantic's re-validation when the `ConfigInstance` uses the result to update its `_active` model. Handles creation of intermediate dictionaries/lists if path segments do not exist.

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
    1.  If `eval_expressions` is `True` and input is a string, attempt safe evaluation. If `_safe_eval` returns a number, use it; otherwise, use the original string for coercion.
    2.  Attempt coercion to the field's numeric type (e.g., `int(value)`, `float(value)`).
    3.  Apply `NumericPolicy` based on `ge`/`le`/`multiple_of` constraints. For `CLAMP` with `multiple_of`, clamping to `ge/le` happens first, then rounding to `multiple_of` (ensuring result is still within clamped `ge/le`).
    4.  If field is `Optional` and input is `None`, `None` is preserved and processing stops here. The fixer returns `(FixStatusEnum.PROCESSED_UNMODIFIED, None)`.

---

### B.2. Options (Single Choice String - Implicit)

*   **Purpose:** Handling fields where the value must be one of a predefined set of string options.
*   **Field Annotation:** `str`, `Optional[str]`, `Literal["opt1", "opt2"]`.
*   **`format_spec.type`:** Not explicitly set. Inferred if `json_schema_extra.options: List[str]` is present and the field is typically `str`, and not handled by `multiple_choice` format.
*   **`format_spec.options`:** N/A (options come from `json_schema_extra.options`).
*   **`autofix_settings`:**
    *   `options_policy: OptionsPolicy` (Default: `NEAREST`)
        *   `NEAREST`: If input string is not in `options`, attempts `difflib.get_close_matches`. If a good match (e.g., cutoff > 0.6) is found, it's used. Otherwise, original value.
        *   `REJECT`: If input string is not in `options`, original value is passed.
        *   `BYPASS`: Skips options auto-fixing.
*   **Behavior:**
    1.  If input is already in `options`, it's considered valid by this fixer, status `PROCESSED_UNMODIFIED`.
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
    *   `allow_single_value_as_range: bool` (Default: `False`): If `True`, an input like `5` becomes `(5,5)` (or `[5,5]`). If `False`, single value input is rejected by structure check unless parsed via separator.
    *   `enforce_min_le_max: bool` (Default: `True`): If `True`, ensures `range[0] <= range[1]` after individual item processing.
    *   `input_separator: Optional[str]` (Default: `None`): If provided (e.g. `"-"`, `","`), allows string input like "0-100" to be parsed into `(0, 100)`.
*   **`autofix_settings`:**
    *   `range_policy: RangePolicy` (Enum, e.g., `CLAMP_ITEMS`, `REJECT_IF_INVALID_STRUCTURE`, `REJECT_IF_ITEMS_INVALID`, `SWAP_IF_REVERSED_AND_VALID`, `BYPASS`)
*   **Behavior:**
    1.  **Input Parsing:**
        *   If `input_separator` is defined and input is a string, attempt to split and parse into two potential numeric values.
        *   If input is a single number and `allow_single_value_as_range` is `True`, convert to `(num, num)`.
    2.  **Structure Validation:** Check if input is a 2-element list/tuple (or became one). If not, and policy is `REJECT_IF_INVALID_STRUCTURE`, mark for rejection.
    3.  **Item Coercion & Validation:** For each item in the pair:
        *   Coerce to `item_type`. If coercion fails, handle based on `range_policy`.
        *   Apply `min_item_value`, `max_item_value`, `item_multiple_of` based on `range_policy` (e.g., clamp or reject individual items if `CLAMP_ITEMS` or `REJECT_IF_ITEMS_INVALID`). Clamping respects `item_multiple_of`.
    4.  **Order Enforcement:** If `enforce_min_le_max` is `True` and after item validation `range[0] > range[1]`:
        *   If `range_policy` allows swapping (e.g., `SWAP_IF_REVERSED_AND_VALID`), swap them.
        *   Otherwise, mark for rejection or pass original (depending on policy).
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
    *   `input_separator: Optional[str]` (Default: `None`): If input is a string (e.g., "apple,banana"), use this to split it into a list of strings before matching against options. Item types in `options` must be string if this is used. Items are typically stripped of whitespace.
*   **`autofix_settings`:**
    *   `multiple_choice_policy: MultipleChoicePolicy` (Enum, e.g., `REMOVE_INVALID_CHOICES`, `REJECT_IF_ANY_INVALID`, `REJECT_IF_COUNT_INVALID`, `BYPASS`)
*   **Behavior:**
    1.  **Input Normalization:**
        *   If `input_separator` is defined and input is a string, split it into a list of strings.
        *   Ensure input is a list. If it's a single item not in a list, it should be treated as `[item]`.
    2.  **Item Validation & Filtering:**
        *   If not `allow_duplicates`, make items unique while preserving order.
        *   Create a new list for valid items. Iterate through input items. Check if each item exists in `json_schema_extra.options`.
        *   Apply `multiple_choice_policy`:
            *   `REMOVE_INVALID_CHOICES`: Add valid items to the new list.
            *   `REJECT_IF_ANY_INVALID`: If any item is not in `options`, the entire input is marked for rejection.
    3.  **Count Validation:** Check `min_selections` and `max_selections` against the count of (now valid) selected items. If violated and policy is `REJECT_IF_COUNT_INVALID`, mark for rejection.
    4.  Return the processed list or original value.
    5.  Handles `Optional[List[T]]` if input is `None`.

---

### B.5. List Conversion (Generic String/List to Typed List)

*   **Purpose:** Converting a string (e.g., CSV) or a list of raw values into a list of a specific, validated type.
*   **Field Annotation:** `List[T]` (e.g., `List[int]`, `List[float]`, `List[str]`, `List[bool]`).
*   **`format_spec.type`:** E.g., `"string_to_list"`, `"list_to_typed_list"`. A single versatile type like `"list_conversion"` is preferred.
*   **`format_spec.options`:**
    *   `input_is_string: bool` (Default: `False`): If `True`, expects string input that needs splitting.
    *   `input_separator: str` (Default: `","`): Used if `input_is_string` is `True`. Defines how to split the string.
    *   `item_type: Literal["int", "float", "str", "bool"]` (Required): Target type for list items.
    *   `strip_items: bool` (Default: `True`): Strip whitespace from split string items before coercion (if `input_is_string`).
    *   **Item-level constraints (applied after coercion to `item_type`):**
        *   If `item_type` is numeric: `item_ge`, `item_le`, `item_multiple_of`.
        *   If `item_type` is string: `item_min_length`, `item_max_length`, `item_pattern`.
        *   `item_options: Optional[List[Any]]` (For items that must be one of specified options, matching `item_type`).
    *   `min_items: Optional[int]`: Minimum length of the resulting list.
    *   `max_items: Optional[int]`: Maximum length of the resulting list.
    *   `allow_duplicates: bool` (Default: `True`): If `False`, resulting list will have unique items (order of first occurrences preserved).
*   **`autofix_settings`:**
    *   `list_conversion_policy: ListConversionPolicy` (Enum, e.g., `CONVERT_OR_REJECT`, `CONVERT_BEST_EFFORT`, `BYPASS`)
    *   `item_numeric_policy: NumericPolicy` (If `item_type` is numeric, for applying `item_ge/le/multiple_of`).
    *   `item_options_policy: OptionsPolicy` (If `item_options` are provided, for matching items).
*   **Behavior:**
    1.  **Input Preparation:**
        *   If `input_is_string` is `True` and input is a string: Split string by `input_separator`. If `strip_items`, strip each part.
        *   Else, ensure input is a list. If not, it's a structural mismatch (handle per policy).
    2.  **Item Processing Loop:** For each item in the (potentially split) input list:
        *   Attempt to coerce to `item_type`. If coercion fails (e.g., `ValueError` for `int("text")`), this item is considered invalid.
        *   If coercion succeeds, apply item-level constraints (`item_ge/le`, `item_min_length`, `item_options`) using associated item-level policies (`item_numeric_policy`, `item_options_policy`). If an item fails its constraints, it's considered invalid.
        *   Collect valid processed items. How invalid items affect the outcome depends on `list_conversion_policy`:
            *   `CONVERT_OR_REJECT`: If any item is invalid, the entire original list is marked for rejection.
            *   `CONVERT_BEST_EFFORT`: Only valid, processed items are kept.
    3.  **List-level Adjustments:**
        *   If not `allow_duplicates`, make the list of successfully processed items unique.
    4.  **List Length Validation:** Check `min_items`/`max_items` against the final processed list. If violated, mark for rejection (if policy implies rejection).
    5.  Return the fully processed list or original value.
    6.  Handles `Optional[List[T]]` if input is `None`.

---

### B.6. Datetime String

*   **Purpose:** Parsing string inputs into `datetime.datetime`, `datetime.date`, or `datetime.time` objects, with format validation.
*   **Field Annotation:** `datetime.datetime`, `datetime.date`, `datetime.time`, or `Optional` versions.
*   **`format_spec.type`:** `"datetime_string"`
*   **`format_spec.options`:**
    *   `target_type: Literal["datetime", "date", "time"]` (Inferred from field annotation if possible, otherwise required).
    *   `formats: List[str]` (Optional, e.g., `["%Y-%m-%d %H:%M:%S", "%Y/%m/%d"]`): List of `strptime` format codes to try *in order*. If not provided, Pydantic's default parsing (which includes ISO 8601) is relied upon after this fixer (if it bypasses).
    *   `default_timezone: Optional[str]` (e.g., "UTC", "America/New_York"): If input string is naive and `target_type` is "datetime", localize to this timezone. Requires `pytz` or `zoneinfo` (Python 3.9+).
    *   `output_timezone: Optional[str]`: If `target_type` is "datetime", convert parsed datetime to this timezone.
    *   Constraints (applied after successful parsing):
        *   `min_datetime: Optional[Union[str, datetime.datetime, datetime.date]]` (Parsable datetime/date string or object).
        *   `max_datetime: Optional[Union[str, datetime.datetime, datetime.date]]`.
*   **`autofix_settings`:**
    *   `datetime_policy: DatetimePolicy` (Enum, e.g., `PARSE_FIRST_SUCCESSFUL_FORMAT`, `REJECT_IF_NO_FORMAT_MATCHES`, `REJECT_IF_CONSTRAINTS_VIOLATED`, `CLAMP_TO_CONSTRAINTS` (if sensible, e.g. for dates, not typically datetimes), `BYPASS`)
*   **Behavior:**
    1.  If input is already a Python `datetime.datetime`, `datetime.date`, or `datetime.time` object matching `target_type`, it may proceed to constraint checks or be bypassed.
    2.  If input is a string:
        *   If `formats` list is provided, try parsing with each format string in `formats` using `datetime.strptime`. The first successful parse is used.
        *   If `formats` is not provided or all fail, this fixer might pass the original string to Pydantic (if policy is `BYPASS` or implies fallback).
        *   If parsing succeeds:
            *   Apply `default_timezone` if `target_type` is "datetime" and parsed datetime is naive.
            *   Apply `min_datetime`/`max_datetime` constraints. If violated, handle based on `datetime_policy` (e.g., `REJECT_IF_CONSTRAINTS_VIOLATED`). Clamping might be complex and usually not done for datetimes by default.
            *   Apply `output_timezone` conversion if `target_type` is "datetime".
            *   Return the processed `datetime/date/time` object.
    3.  If parsing fails for all specified formats, or constraints are violated and policy dictates rejection, mark for rejection.
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
    *   `sort_ranges: bool` (Default: `False`): If `True`, sorts the list of ranges by their start points after all items are processed.
    *   `input_separator_list: Optional[str]` (Default: `None`): If input is a string, this separator is used to split it into multiple range strings (e.g., "0-10;20-30" with separator ";").
    *   `input_separator_range: str` (Required if `input_separator_list` is used, passed to individual range parser, e.g., "-").
*   **`autofix_settings`:**
    *   `multiple_ranges_policy: MultipleRangesPolicy` (Enum, e.g., `PROCESS_ITEMS_BEST_EFFORT`, `REJECT_IF_ANY_ITEM_INVALID`, `REJECT_IF_LIST_CONSTRAINTS_VIOLATED`, `BYPASS`)
    *   `item_range_policy: RangePolicy` (Policy to apply to each individual range tuple, see B.3).
*   **Behavior:**
    1.  **Input Parsing:** If input is a string and `input_separator_list` is provided, split by it. Each part is then treated as a string input for an individual range. If input is already a list, use it directly.
    2.  **Individual Range Processing:** For each potential range in the list (either from split string or original list):
        *   Apply the logic from **B.3. Range** using `item_range_*` options (including its `input_separator_range` if the item is a string) and `item_range_policy`.
        *   Collect successfully processed ranges. How failures of individual ranges are handled depends on `multiple_ranges_policy` (e.g., `PROCESS_ITEMS_BEST_EFFORT` discards failed ranges, `REJECT_IF_ANY_ITEM_INVALID` marks the whole list for rejection).
    3.  **List-level Validation:**
        *   Apply `min_ranges`/`max_ranges` to the count of successfully processed ranges.
        *   If `sort_ranges`, sort the list of valid ranges.
        *   If not `allow_overlapping_ranges`, check for overlaps among valid ranges. If overlap detected, mark for rejection.
    4.  Return the processed list of range tuples or original value.
    5.  Handles `Optional[List[Tuple[N,N]]]` if input is `None`.

---

### B.8. Boolean String/Numeric

*   **Purpose:** Flexible parsing of boolean values from strings (e.g., "yes", "True", "1") or numbers (0, 1).
*   **Field Annotation:** `bool`, `Optional[bool]`.
*   **`format_spec.type`:** `"boolean_flexible"`
*   **`format_spec.options`:**
    *   `true_values: List[Union[str, int, float]]` (Default: `["true", "t", "yes", "y", "on", "1", 1, 1.0]`). Comparison is case-insensitive for strings.
    *   `false_values: List[Union[str, int, float]]` (Default: `["false", "f", "no", "n", "off", "0", 0, 0.0]`). Comparison is case-insensitive for strings.
*   **`autofix_settings`:**
    *   `boolean_policy: BooleanPolicy` (Enum, e.g., `STRICT_MATCH` (must be in lists), `REJECT_IF_UNRECOGNIZED`, `BYPASS`)
*   **Behavior:**
    1.  If input is already a Python `bool`, it's used directly (status `PROCESSED_UNMODIFIED`).
    2.  If input is string, convert to lowercase for matching against `true_values`/`false_values`.
    3.  Check if (potentially normalized) input is in `true_values`. If yes, result is `True`.
    4.  Check if (potentially normalized) input is in `false_values`. If yes, result is `False`.
    5.  If not found in either:
        *   If policy is `REJECT_IF_UNRECOGNIZED`, mark for rejection.
        *   If policy is `STRICT_MATCH` (or similar), it implies rejection.
    6.  Handles `Optional[bool]` if input is `None`.

---

### B.9. File/Directory Path

*   **Purpose:** Validating strings as file or directory paths with existence/type checks and normalization.
*   **Field Annotation:** `pathlib.Path`, `str` (if output as string is desired), `Optional[...]`.
*   **`format_spec.type`:** `"path_string"`
*   **`format_spec.options`:**
    *   `path_type: Literal["file", "dir", "any"]` (Default: `"any"`): Expected type of path.
    *   `must_exist: bool` (Default: `False`): If `True`, path must exist.
    *   `resolve_path: bool` (Default: `True`): If `True`, converts to an absolute, symlink-resolved path (`Path.resolve()`).
    *   `expand_user: bool` (Default: `True`): If `True`, expands `~` (`Path.expanduser()`).
    *   `allowed_extensions: Optional[List[str]]` (e.g., `[".txt", ".csv"]`). Case-insensitive. Only checked if `path_type` is `"file"`. Input extensions should include the dot.
    *   `base_path: Optional[Union[str, Path]]` (Default: `None`): If provided, relative input paths are resolved against this base before other checks.
*   **`autofix_settings`:**
    *   `path_policy: PathPolicy` (Enum, e.g., `VALIDATE_AND_NORMALIZE`, `REJECT_IF_INVALID`, `BYPASS`)
*   **Behavior:**
    1.  If input is already a `pathlib.Path` object, use it. If string, convert to `Path`.
    2.  If `expand_user`, call `Path.expanduser()`.
    3.  If `base_path` is given and current path is relative, join with `Path(base_path)`.
    4.  If `resolve_path`, call `Path.resolve(strict=False)`. `strict=True` could be an option if path *must* exist for resolving.
    5.  If `must_exist`:
        *   Check `current_path.exists()`. If not, mark for rejection.
        *   If exists:
            *   If `path_type == "file"`, check `current_path.is_file()`. If not, mark for rejection.
            *   If `path_type == "dir"`, check `current_path.is_dir()`. If not, mark for rejection.
    6.  If `path_type == "file"` (or `"any"` and it is a file) and `allowed_extensions` are provided:
        *   Check `current_path.suffix.lower()` against lowercased `allowed_extensions`. If no match, mark for rejection.
    7.  If all checks pass, return the processed `Path` object. (If original annotation was `str`, `str(processed_path)` can be returned).
    8.  If any check fails and policy dictates rejection, mark original input for rejection.
    9.  Handles `Optional` field if input is `None`.

---
**(General Note on all format fixers):** Each fixer should be designed to gracefully handle `None` input if the field's Pydantic annotation is `Optional`. Typically, if `None` is received for an optional field, the fixer should return `(FixStatusEnum.PROCESSED_UNMODIFIED, None)` or `(FixStatusEnum.BYPASSED, None)` without further processing, unless the format specifically targets `None` values. The `PydanticUndefined` value from `raw_data_dict.get()` should also be handled to ensure defaults are respected (i.e., if a field is not in input, auto-fix usually doesn't act on it, Pydantic applies the default).