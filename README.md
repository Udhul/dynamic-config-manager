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

