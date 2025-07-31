# =============================================================
#  tests/test_metadata.py - Test enhanced metadata functionality  
# =============================================================

from typing import List, Optional, Tuple
import pytest
from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField


class TestMetadata:
    """Test comprehensive field metadata access including ConfigField attributes."""

    def test_basic_metadata_with_description(self):
        """Test that description is included in metadata."""
        
        class SimpleConfig(DynamicBaseSettings):
            server_port: int = ConfigField(
                default=8080, 
                description="Server port number",
                ge=1024, 
                le=65535
            )
            
        cfg = ConfigManager.register("test_desc", SimpleConfig)
        meta = cfg.get_metadata("server_port")
        
        assert meta["description"] == "Server port number"
        assert meta["type"] == int
        assert meta["required"] is False
        assert meta["default"] == 8080
        assert meta["ge"] == 1024
        assert meta["le"] == 65535

    def test_configfield_attributes_flattened(self):
        """Test that ConfigField attributes are flattened to top level."""
        
        class UIConfig(DynamicBaseSettings):
            log_level: str = ConfigField(
                default="INFO",
                description="Logging level",
                ui_hint="ComboBox",
                ui_extra={"width": 200, "editable": True},
                options=["DEBUG", "INFO", "WARNING", "ERROR"],
                autofix_settings={"options_policy": "nearest"},
                format_spec={"type": "single_choice", "case_sensitive": False}
            )
            
        cfg = ConfigManager.register("test_ui", UIConfig)
        meta = cfg.get_metadata("log_level")
        
        # Check flattened attributes
        assert meta["ui_hint"] == "ComboBox"
        assert meta["ui_extra"] == {"width": 200, "editable": True}
        assert meta["options"] == ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert meta["autofix_settings"] == {"options_policy": "nearest"}
        assert meta["format_spec"] == {"type": "single_choice", "case_sensitive": False}
        
        # Check description is included
        assert meta["description"] == "Logging level"

    def test_json_schema_extra_included(self):
        """Test that full json_schema_extra is included in metadata."""
        
        class AdvancedConfig(DynamicBaseSettings):
            feature_flags: Optional[List[str]] = ConfigField(
                default=None,
                description="Feature toggles",
                ui_hint="MultiSelect",
                options=["feature_a", "feature_b", "feature_c"],
                format_spec={"type": "multiple_choice", "min_selections": 0, "max_selections": 2},
                json_schema_extra={"custom_data": {"group": "features", "beta": True}}
            )
            
        cfg = ConfigManager.register("test_advanced", AdvancedConfig)
        meta = cfg.get_metadata("feature_flags")
        
        # Check full json_schema_extra is present
        assert "json_schema_extra" in meta
        json_extra = meta["json_schema_extra"]
        
        assert json_extra["ui_hint"] == "MultiSelect"
        assert json_extra["options"] == ["feature_a", "feature_b", "feature_c"]
        assert json_extra["format_spec"]["type"] == "multiple_choice"
        assert json_extra["custom_data"] == {"group": "features", "beta": True}
        
        # Check flattened access still works
        assert meta["ui_hint"] == "MultiSelect"
        assert meta["options"] == ["feature_a", "feature_b", "feature_c"]

    def test_fields_without_json_schema_extra(self):
        """Test metadata for fields without json_schema_extra attributes."""
        
        class PlainConfig(DynamicBaseSettings):
            plain_field: int = 42
            described_field: str = ConfigField(default="test", description="A simple field")
            
        cfg = ConfigManager.register("test_plain", PlainConfig)
        
        # Test field without ConfigField
        meta_plain = cfg.get_metadata("plain_field")
        assert meta_plain["description"] is None
        assert "json_schema_extra" not in meta_plain
        assert "ui_hint" not in meta_plain
        assert "options" not in meta_plain
        
        # Test field with only description
        meta_desc = cfg.get_metadata("described_field")
        assert meta_desc["description"] == "A simple field"
        assert "json_schema_extra" not in meta_desc
        assert "ui_hint" not in meta_desc

    def test_nested_field_metadata(self):
        """Test metadata access for nested model fields."""
        
        class NestedConfig(DynamicBaseSettings):
            nested_value: float = ConfigField(
                default=0.5, 
                description="Nested float value",
                ge=0, 
                le=1,
                ui_hint="Slider",
                ui_extra={"step": 0.1}
            )
            
        class MainConfig(DynamicBaseSettings):
            nested: NestedConfig = ConfigField(
                default_factory=NestedConfig,
                description="Nested configuration"
            )
            
        cfg = ConfigManager.register("test_nested", MainConfig)
        
        # Test nested field access
        meta = cfg.get_metadata("nested.nested_value")
        assert meta["description"] == "Nested float value"
        assert meta["ui_hint"] == "Slider"
        assert meta["ui_extra"] == {"step": 0.1}
        assert meta["ge"] == 0
        assert meta["le"] == 1

    def test_meta_accessor_proxy_returns_enhanced_metadata(self):
        """Test that .meta accessor also returns enhanced metadata."""
        
        class ProxyTestConfig(DynamicBaseSettings):
            field_with_ui: str = ConfigField(
                default="test",
                description="UI field",
                ui_hint="TextBox",
                options=["test", "prod"]
            )
            
        cfg = ConfigManager.register("test_proxy", ProxyTestConfig)
        
        # Test direct get_metadata call
        direct_meta = cfg.get_metadata("field_with_ui")
        
        # Test .meta accessor
        proxy_meta = cfg.meta.field_with_ui
        
        # Should return the same enhanced metadata
        assert direct_meta == proxy_meta
        assert proxy_meta["description"] == "UI field"
        assert proxy_meta["ui_hint"] == "TextBox"
        assert proxy_meta["options"] == ["test", "prod"]

    def test_backward_compatibility(self):
        """Test that existing metadata keys are unchanged."""
        
        class CompatConfig(DynamicBaseSettings):
            port: int = ConfigField(default=8080, ge=1024, le=65535)
            
        cfg = ConfigManager.register("test_compat", CompatConfig)
        meta = cfg.get_metadata("port")
        
        # All existing keys should still be present
        required_keys = [
            "type", "required", "default", "editable", 
            "active_value", "default_value", "saved_value"
        ]
        for key in required_keys:
            assert key in meta
            
        # Constraint keys should be present
        assert "ge" in meta
        assert "le" in meta

    def test_all_common_configfield_attributes(self):
        """Test all common ConfigField attributes are properly flattened."""
        
        class FullFeaturedConfig(DynamicBaseSettings):
            range_field: Tuple[int, int] = ConfigField(
                default=(10, 20),
                description="A range field with all features",
                ui_hint="RangeSlider",
                ui_extra={"min_val": 0, "max_val": 100, "step": 5},
                autofix_settings={
                    "range_policy": "clamp_items",
                    "numeric_policy": "clamp"
                },
                format_spec={
                    "type": "range",
                    "item_type": "int",
                    "min_item_value": 0,
                    "max_item_value": 100
                }
            )
            
        cfg = ConfigManager.register("test_full", FullFeaturedConfig)
        meta = cfg.get_metadata("range_field")
        
        # Test all common attributes are flattened
        assert meta["ui_hint"] == "RangeSlider"
        assert meta["ui_extra"]["step"] == 5
        assert meta["autofix_settings"]["range_policy"] == "clamp_items"
        assert meta["format_spec"]["type"] == "range"
        
        # Test they're also in json_schema_extra
        json_extra = meta["json_schema_extra"]
        assert json_extra["ui_hint"] == "RangeSlider"
        assert json_extra["format_spec"]["item_type"] == "int"

    def test_partial_configfield_attributes(self):
        """Test that only present ConfigField attributes are included."""
        
        class PartialConfig(DynamicBaseSettings):
            simple_field: str = ConfigField(
                default="hello",
                description="Simple field",
                ui_hint="TextBox"
                # Missing: ui_extra, options, autofix_settings, format_spec
            )
            
        cfg = ConfigManager.register("test_partial", PartialConfig)
        meta = cfg.get_metadata("simple_field")
        
        # Present attributes should be flattened
        assert meta["ui_hint"] == "TextBox"
        
        # Missing attributes should not be present at top level
        assert "ui_extra" not in meta
        assert "options" not in meta  
        assert "autofix_settings" not in meta
        assert "format_spec" not in meta
        
        # But json_schema_extra should only contain what's actually there
        json_extra = meta["json_schema_extra"]
        assert "ui_hint" in json_extra
        assert "ui_extra" not in json_extra

    def test_active_default_saved_values_still_work(self):
        """Test that active_value, default_value, and saved_value still work correctly."""
        
        class ValueConfig(DynamicBaseSettings):
            test_field: int = ConfigField(
                default=100,
                description="Test field for values"
            )
            
        cfg = ConfigManager.register("test_values", ValueConfig, persistent=False)
        
        # Set a different active value
        cfg.set_value("test_field", 200)
        
        meta = cfg.get_metadata("test_field")
        
        assert meta["active_value"] == 200
        assert meta["default_value"] == 100
        # saved_value should be PydanticUndefined for non-persistent config
        from pydantic.fields import PydanticUndefined
        assert meta["saved_value"] is PydanticUndefined

    def teardown_method(self):
        """Clean up registered configs after each test."""
        # Clear all registered instances to avoid conflicts
        ConfigManager._instances.clear()
