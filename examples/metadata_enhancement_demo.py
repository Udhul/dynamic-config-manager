#!/usr/bin/env python3
"""
Demonstration of Enhanced Metadata Functionality
================================================

This script demonstrates the new comprehensive metadata access capabilities
that were added to dynamic-config-manager v1.3+.

The ConfigInstance.get_metadata() method now returns complete field metadata
including:
- description field from ConfigField
- Full json_schema_extra content  
- Flattened common ConfigField attributes (ui_hint, ui_extra, options, etc.)
- All existing metadata (type, constraints, active/default/saved values)
"""

from typing import List, Optional, Tuple
from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField


class DemoConfig(DynamicBaseSettings):
    """Demo configuration showcasing enhanced metadata features."""
    
    # Basic field with description
    server_port: int = ConfigField(
        default=8080,
        description="Port number for the web server",
        ge=1024,
        le=65535,
        ui_hint="SpinBox",
        ui_extra={"step": 1, "suffix": " (port)"}
    )
    
    # Field with options and UI hints
    log_level: str = ConfigField(
        default="INFO", 
        description="Application logging level",
        options=["DEBUG", "INFO", "WARNING", "ERROR"],
        ui_hint="ComboBox",
        autofix_settings={"options_policy": "nearest"}
    )
    
    # Advanced field with format specification
    feature_flags: Optional[List[str]] = ConfigField(
        default=None,
        description="List of enabled feature flags",
        ui_hint="MultiSelect",
        options=["feature_a", "feature_b", "feature_c", "experimental"],
        format_spec={
            "type": "multiple_choice",
            "min_selections": 0,
            "max_selections": 3
        },
        autofix_settings={"multiple_choice_policy": "remove_invalid"}
    )
    
    # Range field demonstrating complex format
    cpu_range: Tuple[int, int] = ConfigField(
        default=(2, 8),
        description="CPU core range (min, max)",
        ui_hint="RangeSlider",
        ui_extra={"min_val": 1, "max_val": 16, "step": 1},
        format_spec={
            "type": "range", 
            "item_type": "int",
            "min_item_value": 1,
            "max_item_value": 16
        }
    )
    
    # Simple field without extra metadata
    simple_value: float = 42.0


def main():
    print("=" * 60)
    print("Enhanced Metadata Functionality Demo")
    print("=" * 60)
    
    # Register the config
    cfg = ConfigManager.register("demo", DemoConfig, persistent=False)
    
    # Demonstrate enhanced metadata for server_port
    print("\n1. Server Port Field Metadata:")
    print("-" * 40)
    port_meta = cfg.get_metadata("server_port")
    
    print(f"Description: {port_meta['description']}")
    print(f"Type: {port_meta['type'].__name__}")
    print(f"Default: {port_meta['default']}")
    print(f"Required: {port_meta['required']}")
    print(f"Constraints: ge={port_meta.get('ge')}, le={port_meta.get('le')}")
    print(f"UI Hint: {port_meta.get('ui_hint')}")
    print(f"UI Extra: {port_meta.get('ui_extra')}")
    print(f"Active Value: {port_meta['active_value']}")
    
    # Demonstrate options and autofix settings
    print("\n2. Log Level Field Metadata:")
    print("-" * 40)
    log_meta = cfg.get_metadata("log_level")
    
    print(f"Description: {log_meta['description']}")
    print(f"Options: {log_meta.get('options')}")
    print(f"UI Hint: {log_meta.get('ui_hint')}")
    print(f"Autofix Settings: {log_meta.get('autofix_settings')}")
    
    # Demonstrate format specification
    print("\n3. Feature Flags Field Metadata:")
    print("-" * 40)
    flags_meta = cfg.get_metadata("feature_flags")
    
    print(f"Description: {flags_meta['description']}")
    print(f"Options: {flags_meta.get('options')}")
    print(f"Format Spec: {flags_meta.get('format_spec')}")
    print(f"UI Hint: {flags_meta.get('ui_hint')}")
    
    # Demonstrate full json_schema_extra access
    print("\n4. Full JSON Schema Extra:")
    print("-" * 40)
    json_extra = flags_meta.get('json_schema_extra', {})
    print(f"Complete json_schema_extra: {json_extra}")
    
    # Demonstrate range field
    print("\n5. CPU Range Field Metadata:")
    print("-" * 40)
    range_meta = cfg.get_metadata("cpu_range")
    
    print(f"Description: {range_meta['description']}")
    print(f"UI Hint: {range_meta.get('ui_hint')}")
    print(f"UI Extra: {range_meta.get('ui_extra')}")
    print(f"Format Spec: {range_meta.get('format_spec')}")
    
    # Demonstrate simple field (minimal metadata)
    print("\n6. Simple Field Metadata:")
    print("-" * 40)
    simple_meta = cfg.get_metadata("simple_value")
    
    print(f"Description: {simple_meta['description']}")
    print(f"Type: {simple_meta['type'].__name__}")
    print(f"Has json_schema_extra: {'json_schema_extra' in simple_meta}")
    print(f"Has UI hint: {'ui_hint' in simple_meta}")
    
    # Demonstrate .meta accessor
    print("\n7. Using .meta Accessor:")
    print("-" * 40)
    accessor_meta = cfg.meta.server_port
    direct_meta = cfg.get_metadata("server_port")
    
    print(f"Accessor and direct access are identical: {accessor_meta == direct_meta}")
    print(f"Via accessor - UI Hint: {accessor_meta.get('ui_hint')}")
    
    # Demonstrate backward compatibility
    print("\n8. Backward Compatibility:")
    print("-" * 40)
    print("All original metadata keys are preserved:")
    required_keys = ["type", "required", "default", "editable", "active_value", "default_value", "saved_value"]
    
    for key in required_keys:
        has_key = key in port_meta
        print(f"  {key}: {'YES' if has_key else 'NO'}")
    
    print(f"\nMetadata enhancement is fully backward compatible!")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
