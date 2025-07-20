# Dynamic Config Manager - Agent Guide

## Build/Test Commands
- **Test all**: `python -m pytest` or `pytest`
- **Test single file**: `pytest tests/test_basic.py`
- **Test specific test**: `pytest tests/test_basic.py::test_function_name`
- **Install**: `pip install -e .` (editable install)
- **Install with all deps**: `pip install -e .[all]` (includes YAML, TOML, watchfiles)
- **Install for CI**: `pip install -e .[ci]` (includes all deps + pytest, flake8)
- **Lint**: `flake8` (see setup.cfg for config: max-line-length=120)
- **CLI tool**: `dcm-cli` (after install)

## Project Structure
- **Core library**: `dynamic_config_manager/` - Pydantic-based config management with singleton pattern
- **Manager**: `manager.py` - ConfigManager singleton, ConfigInstance wrapper, file I/O
- **Models**: `models.py` - DynamicBaseSettings, ConfigField helper for Pydantic
- **Validation**: `validation.py` - attach_auto_fix decorator for input preprocessing  
- **Watchers**: `watchers.py` - File watching capabilities with watchfiles
- **CLI**: `cli.py` - Command-line interface
- **Tests**: `tests/` - pytest-based test suite
- **Documentation**: `docs/` - Markdown format specs, progress, user and API docs (to be referenced in README.md)

## Core Architecture
- **ConfigManager**: Singleton for managing multiple typed configurations
- **ConfigInstance**: Wrapper for individual configs with .active and .meta accessors
- **Path-based access**: Use dots for deep access (e.g., "nested.field.value") 
- **File formats**: JSON (default), YAML, TOML with auto-detection by extension
- **Auto-fix system**: attach_auto_fix decorator for input preprocessing with policies
- **Optional dependencies**: PyYAML (yaml), tomli/tomli-w (toml), watchfiles (watch)

## Code Style  
- **Line length**: 120 chars (flake8 configured)
- **Types**: Full type hints required, uses typing-extensions
- **Imports**: Standard library, third-party, local modules (separated by blank lines)
- **Base classes**: DynamicBaseSettings extends BaseSettings, use ConfigField helper
- **Patterns**: Singleton pattern, deep path traversal, attribute-style access via proxies
- **Error handling**: ValidationError for validation, custom exceptions for config ops
- **Policies**: Enums for auto-fix behavior (CLAMP, REJECT, BYPASS, etc.)
