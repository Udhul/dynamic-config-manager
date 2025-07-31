#!/usr/bin/env python3
# =============================================================
#  examples/field_names_example.py
# =============================================================
"""
Example demonstrating the get_field_names() API for field introspection.

This example shows how to use the new get_field_names() method to:
1. Get all field names from a configuration
2. Scope field retrieval to nested sections
3. Use returned field names with other config methods
"""

from dynamic_config_manager import ConfigManager, DynamicBaseSettings, ConfigField


class DatabaseConfig(DynamicBaseSettings):
    """Database connection settings."""
    host: str = ConfigField("localhost", description="Database host")
    port: int = ConfigField(5432, description="Database port")
    username: str = ConfigField("admin", description="Database username") 
    password: str = ConfigField("secret", description="Database password")


class CacheConfig(DynamicBaseSettings):
    """Caching settings."""
    ttl: int = ConfigField(300, description="Time to live in seconds")
    max_size: int = ConfigField(1000, description="Maximum cache size")


class APIConfig(DynamicBaseSettings):
    """API server settings."""
    timeout: float = ConfigField(30.0, description="Request timeout")
    rate_limit: int = ConfigField(100, description="Requests per minute")


class AppConfig(DynamicBaseSettings):
    """Complete application configuration."""
    
    # Top-level settings
    app_name: str = ConfigField("MyApp", description="Application name")
    debug: bool = ConfigField(False, description="Enable debug mode")
    
    # Nested configurations
    database: DatabaseConfig = ConfigField(default_factory=DatabaseConfig)
    cache: CacheConfig = ConfigField(default_factory=CacheConfig)
    api: APIConfig = ConfigField(default_factory=APIConfig)


def main():
    # Register the configuration
    config = ConfigManager.register("app", AppConfig, persistent=False)
    
    print("=== Field Names API Example ===\n")
    
    # 1. Get all field names from the root
    print("1. All field names in the configuration:")
    all_fields = config.get_field_names()
    for field in sorted(all_fields):
        print(f"   - {field}")
    
    print(f"\nTotal fields: {len(all_fields)}\n")
    
    # 2. Get field names scoped to specific sections
    print("2. Field names scoped to 'database' section:")
    db_fields = config.get_field_names("database")
    for field in sorted(db_fields):
        print(f"   - {field}")
    
    print("\n3. Field names scoped to 'cache' section:")
    cache_fields = config.get_field_names("cache")
    for field in sorted(cache_fields):
        print(f"   - {field}")
    
    print("\n4. Field names scoped to 'api' section:")
    api_fields = config.get_field_names("api")
    for field in sorted(api_fields):
        print(f"   - {field}")
    
    # 3. Use field names with other config methods
    print("\n=== Using field names with other methods ===\n")
    
    print("5. Reading values using field names:")
    for field in sorted(all_fields):
        value = config.get_value(field)
        print(f"   {field} = {value}")
    
    print("\n6. Getting metadata for database fields:")
    for field in sorted(db_fields):
        full_path = f"database.{field}"
        metadata = config.get_metadata(full_path)
        print(f"   {full_path}:")
        print(f"     Type: {metadata['type'].__name__}")
        print(f"     Default: {metadata['default']}")
        print(f"     Description: {metadata.get('description', 'N/A')}")
    
    # 4. Dynamic field discovery for UI generation
    print("\n=== Dynamic UI generation example ===\n")
    
    print("7. Generating configuration sections for UI:")
    sections = ["database", "cache", "api"]
    
    for section in sections:
        print(f"\n[{section.upper()} SECTION]")
        try:
            section_fields = config.get_field_names(section)
            for field in sorted(section_fields):
                full_path = f"{section}.{field}"
                meta = config.get_metadata(full_path)
                value = config.get_value(full_path)
                
                print(f"  {field}:")
                print(f"    Current: {value}")
                print(f"    Type: {meta['type'].__name__}")
                print(f"    Help: {meta.get('description', 'No description')}")
        except ValueError as e:
            print(f"  Error: {e}")
    
    # 5. Validation that all field names work with get/set
    print("\n=== Field name validation ===\n")
    
    print("8. Testing all field names work with get_value():")
    valid_fields = []
    for field in all_fields:
        try:
            value = config.get_value(field)
            valid_fields.append(field)
        except Exception as e:
            print(f"   ERROR with {field}: {e}")
    
    print(f"   All {len(valid_fields)}/{len(all_fields)} field names are valid!")
    
    # 6. Error handling examples
    print("\n=== Error handling examples ===\n")
    
    print("9. Attempting to get field names for invalid paths:")
    
    # Invalid field name
    try:
        config.get_field_names("nonexistent")
    except KeyError as e:
        print(f"   KeyError for 'nonexistent': {e}")
    
    # Path to non-model field
    try:
        config.get_field_names("debug")
    except ValueError as e:
        print(f"   ValueError for 'debug': {e}")
    
    # Path through non-model field  
    try:
        config.get_field_names("debug.something")
    except ValueError as e:
        print(f"   ValueError for 'debug.something': {e}")
    
    print("\n=== Example complete ===")


if __name__ == "__main__":
    main()
