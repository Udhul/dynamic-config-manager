# Dynamic Config Manager - Progress Tracker

This document tracks development toward a stable v1 release by mapping developer_spec.md to implementation work.

## Overview

| Increment | Focus | Status |
|-----------|-------|--------|
| **PI-1** | Foundation & API stabilization | Done |
| **PI-2** | Validation & Auto-fix subsystem | To Do |
| **PI-3** | Metadata & persistence features | To Do |
| **PI-4** | Extended formats & CLI / extras | To Do |
| **PI-5** | Quality-of-life, docs & packaging | To Do |

Each increment builds on the previous one so that later updates avoid breaking existing behaviour.

## PI-1 – Foundation & API Stabilization
Focus on implementing the core API as described in the spec.

- Use `.` as the path separator for `get_value`, `set_value`, `restore_value`, and metadata retrieval as noted in the spec lines around 22–24【F:developer_spec.md†L22-L24】.
- Implement `_ActiveAccessorProxy` and `_MetaAccessorProxy` so that attribute style access `config.active.section.option` proxies to the path based API【F:developer_spec.md†L219-L224】.
- Provide `DynamicBaseSettings` and `ConfigField` helpers to simplify model definitions (spec section 3.1)【F:developer_spec.md†L83-L113】.
- Re-export public API elements in `__init__.py` (ConfigManager, BaseSettings, DynamicBaseSettings, ConfigField, attach_auto_fix, policy enums, etc.) as outlined in section 6【F:developer_spec.md†L412-L418】.
- Make file I/O helpers gracefully handle missing optional dependencies and expose extras (`yaml`, `toml`).
- Add logging setup with `NullHandler` and ensure informative logging across operations (section 8).
- Provide a minimal test suite verifying registration, saving/loading default JSON configs, and the attribute-based access path.

## PI-2 – Validation & Auto‑Fix Subsystem
Extend `validation.py` to match section 3.4 and Appendix B.

- Introduce the policy enums (`NumericPolicy`, `OptionsPolicy`, `RangePolicy`, `MultipleChoicePolicy`, `ListConversionPolicy`, `FixStatusEnum`, `BooleanPolicy`, `DatetimePolicy`, `PathPolicy`, `MultipleRangesPolicy`) as per spec lines 302 and 419.
- Implement `_safe_eval` and helper fixers for numeric, options, range, multiple choice, list conversion, datetime strings, path strings and other formats described in Appendix B【F:developer_spec.md†L288-L668】.
- Update `attach_auto_fix` to dispatch to these helpers, honour per‑field overrides via `json_schema_extra["autofix"]`, and handle optional fields gracefully (section 3.4).
- Provide tests demonstrating numeric expression evaluation, options nearest match, range coercion, and list conversion behaviour.

## PI-3 – Metadata & Persistence Features
Complete the manager and instance functionality.

- Expand `get_metadata` to return the structure described in Appendix A, including `active_value`, `default_value` and, when persisted, `saved_value`.
- Implement `update_model_field` for runtime modification of registered models as detailed in section 3.2【F:developer_spec.md†L175-L214】.
- Add automatic save/restore helpers and ensure `_deep_get`/`_deep_set` support lists and nested models robustly (Appendix A).
- Implement restore methods and ensure they call `persist` when `auto_save` is enabled.
- Add tests covering metadata queries, restore operations and runtime model updates.

## PI-4 – Extended Formats & CLI / Extras
Enhance usability and optional features.

- Implement remaining field format fixers from Appendix B (boolean strings, path handling, multiple ranges etc.).
- Introduce a small CLI for inspecting and editing configuration files (optional, may be packaged as `dcm-cli`).
- Provide extras in `pyproject.toml` so that `pip install dynamic-config-manager[yaml,toml]` installs format dependencies.
- Improve packaging metadata and README usage examples.

## PI-5 – Quality of Life, Docs & Packaging
Prepare for a stable release.

- Finalise documentation: update README with installation instructions, quick start guide and API links.
- Provide comprehensive unit tests and type‑hints; integrate CI for tests and linting.
- Add convenience utilities (e.g., watchers/hot‑reload hooks) if time permits.
- Tag first stable version.

Progress entries will be updated as each PI completes.
