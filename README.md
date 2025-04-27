# Dynamic Config Manager

A singleton manager for handling multiple, strongly-typed configuration sets within your Python application using [Pydantic](https://docs.pydantic.dev/) and [Pydantic-Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Features

*   **Singleton Access:** Centralized management (`ConfigManager`) for all application configurations.
*   **Type Safety & Validation:** Define configuration structure, types, defaults, and validation rules using Pydantic models (`BaseSettings`). Catches configuration errors early.
*   **Multiple Config Sets:** Manage distinct configuration groups (e.g., UI, API, Database) independently via named `ConfigInstance` objects.
*   **Persistence:** Load from and save to JSON files automatically (on change) or manually. Handles missing files and directories gracefully.
*   **Defaults Handling:** Automatically uses defaults defined in the Pydantic model for missing values during load. Easily restore active values to defaults.
*   **Metadata Driven:** Extract field metadata (description, constraints, custom `json_schema_extra` hints like `ui_editable`, `ui_hint`, `min`, `max`) directly from Pydantic models to drive UIs or documentation.
*   **State Management:** Clear separation between default settings and active settings. Restore individual keys or entire configurations to their default values.
*   **Flexibility:** Configure auto-save behavior per configuration set; supports configurations without file persistence (in-memory only).
*   **Logging:** Uses standard Python logging for feedback (configure handlers in your application).

## Installation

```bash
pip install dynamic-config-manager