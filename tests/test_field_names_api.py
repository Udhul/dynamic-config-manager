# =============================================================
#  tests/test_field_names_api.py
# =============================================================
import pytest
from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField


class SimpleConfig(DynamicBaseSettings):
    port: int = ConfigField(8080)
    name: str = ConfigField("app")


class NestedConfig(DynamicBaseSettings):
    class Database(DynamicBaseSettings):
        host: str = ConfigField("localhost")
        port: int = ConfigField(5432)
        
    class Cache(DynamicBaseSettings):
        ttl: int = ConfigField(300)
        
    db: Database = ConfigField(default_factory=Database)
    cache: Cache = ConfigField(default_factory=Cache)
    debug: bool = ConfigField(False)


class DeepNestedConfig(DynamicBaseSettings):
    class Level1(DynamicBaseSettings):
        class Level2(DynamicBaseSettings):
            class Level3(DynamicBaseSettings):
                value: str = ConfigField("deep")
            nested: Level3 = ConfigField(default_factory=Level3)
        level2: Level2 = ConfigField(default_factory=Level2)
    level1: Level1 = ConfigField(default_factory=Level1)
    simple: str = ConfigField("top")


class TestFieldNamesAPI:
    
    def test_simple_config_field_names(self):
        """Test basic functionality with simple flat config."""
        cfg = ConfigManager.register("test_simple", SimpleConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # Should return all top-level fields
        assert set(field_names) == {"port", "name"}
    
    def test_nested_config_all_fields(self):
        """Test getting all field names from nested config."""
        cfg = ConfigManager.register("test_nested", NestedConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # Should return all fields with dot-separated paths for nested ones
        expected = {"db.host", "db.port", "cache.ttl", "debug"}
        assert set(field_names) == expected
    
    def test_scoped_field_names_database(self):
        """Test scoped field retrieval for database section."""
        cfg = ConfigManager.register("test_scoped_db", NestedConfig, persistent=False)
        field_names = cfg.get_field_names("db")
        
        # Should return only database fields, relative to the scoped path
        assert set(field_names) == {"host", "port"}
    
    def test_scoped_field_names_cache(self):
        """Test scoped field retrieval for cache section."""
        cfg = ConfigManager.register("test_scoped_cache", NestedConfig, persistent=False)
        field_names = cfg.get_field_names("cache")
        
        # Should return only cache fields
        assert set(field_names) == {"ttl"}
    
    def test_deep_nested_config(self):
        """Test with deeply nested configuration."""
        cfg = ConfigManager.register("test_deep", DeepNestedConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # Should return all fields with proper dot notation
        expected = {"level1.level2.nested.value", "simple"}
        assert set(field_names) == expected
    
    def test_deep_nested_scoped(self):
        """Test scoped access on deeply nested config."""
        cfg = ConfigManager.register("test_deep_scoped", DeepNestedConfig, persistent=False)
        
        # Test scoping to level1
        level1_fields = cfg.get_field_names("level1")
        assert set(level1_fields) == {"level2.nested.value"}
        
        # Test scoping to level1.level2
        level2_fields = cfg.get_field_names("level1.level2")
        assert set(level2_fields) == {"nested.value"}
        
        # Test scoping to level1.level2.nested
        level3_fields = cfg.get_field_names("level1.level2.nested")
        assert set(level3_fields) == {"value"}
    
    def test_error_invalid_path(self):
        """Test error handling for invalid paths."""
        cfg = ConfigManager.register("test_error_path", NestedConfig, persistent=False)
        
        # Test non-existent field
        with pytest.raises(KeyError, match="Field 'nonexistent' not found"):
            cfg.get_field_names("nonexistent")
    
    def test_error_path_to_non_model_field(self):
        """Test error when path points to a non-model field."""
        cfg = ConfigManager.register("test_error_non_model", NestedConfig, persistent=False)
        
        # debug is a bool, not a model
        with pytest.raises(ValueError, match="does not point to a nested model"):
            cfg.get_field_names("debug")
    
    def test_error_path_through_non_model(self):
        """Test error when trying to traverse through a non-model field."""
        cfg = ConfigManager.register("test_error_traverse", NestedConfig, persistent=False)
        
        # Can't traverse through debug.something since debug is a bool
        with pytest.raises(ValueError, match="does not point to a nested model"):
            cfg.get_field_names("debug.something")
    
    def test_empty_path_same_as_no_path(self):
        """Test that empty string path behaves same as no path argument."""
        cfg = ConfigManager.register("test_empty_path", NestedConfig, persistent=False)
        
        all_fields_no_arg = cfg.get_field_names()
        all_fields_empty_str = cfg.get_field_names("")
        
        assert all_fields_no_arg == all_fields_empty_str
    
    def test_field_names_compatible_with_get_value(self):
        """Test that returned field names work with get_value method."""
        cfg = ConfigManager.register("test_compatibility", NestedConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # All returned field names should be accessible via get_value
        for field_name in field_names:
            value = cfg.get_value(field_name)
            assert value is not None  # All fields have defaults
    
    def test_field_names_compatible_with_set_value(self):
        """Test that returned field names work with set_value method."""
        cfg = ConfigManager.register("test_set_compatibility", NestedConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # Test setting a string field
        if "db.host" in field_names:
            cfg.set_value("db.host", "new-host")
            assert cfg.get_value("db.host") == "new-host"
        
        # Test setting an int field
        if "db.port" in field_names:
            cfg.set_value("db.port", 3306)
            assert cfg.get_value("db.port") == 3306
    
    def test_field_names_compatible_with_get_metadata(self):
        """Test that returned field names work with get_metadata method."""
        cfg = ConfigManager.register("test_meta_compatibility", NestedConfig, persistent=False)
        field_names = cfg.get_field_names()
        
        # All returned field names should have accessible metadata
        for field_name in field_names:
            metadata = cfg.get_metadata(field_name)
            assert metadata is not None
            assert "type" in metadata
            assert "default" in metadata
