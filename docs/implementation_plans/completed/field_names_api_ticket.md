# Implementation Ticket: Field Names API

## Summary

Add a supported API method to retrieve all registered field names from a config model, including nested ones, with proper path formatting for use with existing `get_*` methods.

## Current State

Users currently access field names using an unsupported hack:

```python
# Current unsupported approach
self.config_fields = [
    field_name
    for field_name in self.config._model_cls.model_fields.keys()
]
```

This approach has several limitations:
- Only returns top-level field names
- No support for nested field paths
- Direct access to internal `_model_cls` attribute
- No way to scope field retrieval to a specific nested level

## Requirements

### Primary API Method

Add a new method `get_field_names()` to `ConfigInstance` with the following signature:

```python
def get_field_names(self, path: str = "") -> List[str]:
    """
    Get all registered field names, optionally scoped to a nested path.
    
    Args:
        path: Optional dot-separated path to scope field retrieval.
              If empty, returns all field names from the root.
              
    Returns:
        List of field names/paths that can be used with get_* methods.
        For nested fields, returns dot-separated paths (e.g., "nested.field").
    """
```

### Behavior Specifications

1. **Root Level Call** (`get_field_names()` or `get_field_names("")`):
   - Returns all field names including nested ones
   - Nested fields returned as dot-separated paths (e.g., `["port", "nested.value", "nested.deep.field"]`)
   - Paths are compatible with existing `get_value()`, `set_value()`, `get_metadata()` methods

2. **Scoped Call** (`get_field_names("nested.path")`):
   - Returns only field names at the specified nested level and below
   - Field names are relative to the scoped path
   - For example, `get_field_names("nested")` returns `["value", "deep.field"]` not `["nested.value", "nested.deep.field"]`

3. **Error Handling**:
   - Invalid paths should raise `KeyError` with descriptive message
   - Paths pointing to non-model fields should raise `ValueError`

## Technical Design

### Implementation Location

Add the method to `ConfigInstance` class in `dynamic_config_manager/manager.py`.

### Core Algorithm

The implementation should:

1. **Path Validation**: Use existing path traversal logic similar to `get_metadata()`
2. **Model Traversal**: Recursively traverse `model_fields` of Pydantic models
3. **Path Construction**: Build dot-separated paths for nested fields
4. **Scoping Logic**: When a path is provided, traverse to that model and collect fields relative to it

### Helper Function

Create a recursive helper function `_collect_field_names()`:

```python
def _collect_field_names(model_cls: Type[BaseModel], prefix: str = "") -> List[str]:
    """
    Recursively collect all field names from a Pydantic model.
    
    Args:
        model_cls: The Pydantic model class to traverse
        prefix: Current path prefix for nested fields
        
    Returns:
        List of field names/paths
    """
```

### Integration Considerations

1. **Consistency**: Follow existing patterns from `get_metadata()` for path handling
2. **Performance**: Consider caching for frequently accessed models
3. **Type Safety**: Ensure proper type annotations and error handling
4. **Documentation**: Include comprehensive docstrings and examples

## Implementation Steps

1. **Add Helper Function**: Implement `_collect_field_names()` recursive traversal
2. **Add Main Method**: Implement `get_field_names()` in `ConfigInstance`
3. **Path Validation**: Reuse existing path traversal logic from `get_metadata()`
4. **Error Handling**: Add appropriate exception handling with clear messages
5. **Testing**: Create comprehensive test suite covering all scenarios
6. **Documentation**: Update API reference and user guide and full_specification

## Test Cases

### Basic Functionality
```python
class SimpleConfig(DynamicBaseSettings):
    port: int = ConfigField(8080)
    name: str = ConfigField("app")

cfg = ConfigManager.register("test", SimpleConfig)
assert cfg.get_field_names() == ["port", "name"]
```

### Nested Models
```python
class NestedConfig(DynamicBaseSettings):
    class Database(DynamicBaseSettings):
        host: str = ConfigField("localhost")
        port: int = ConfigField(5432)
        
    class Cache(DynamicBaseSettings):
        ttl: int = ConfigField(300)
        
    db: Database = ConfigField(default_factory=Database)
    cache: Cache = ConfigField(default_factory=Cache)
    debug: bool = ConfigField(False)

cfg = ConfigManager.register("nested", NestedConfig)

# Root level - all fields
assert cfg.get_field_names() == [
    "db.host", "db.port", "cache.ttl", "debug"
]

# Scoped to database
assert cfg.get_field_names("db") == ["host", "port"]

# Scoped to cache  
assert cfg.get_field_names("cache") == ["ttl"]
```

### Error Cases
```python
# Invalid path
with pytest.raises(KeyError):
    cfg.get_field_names("nonexistent")
    
# Path to non-model field
with pytest.raises(ValueError):
    cfg.get_field_names("debug")  # debug is bool, not a model
```

## Breaking Changes

None. This is a new API method that doesn't modify existing functionality.

## Version
Bump package _version after change

## Dependencies

- Leverages existing Pydantic model introspection
- Uses existing path traversal patterns from `get_metadata()`
- No new external dependencies required

## Documentation Updates

1. **API Reference**: Add method documentation with examples
2. **User Guide**: Add section on field introspection
3. **Full Specification**: Add `get_field_names()` method description
4. **Examples**: Create example script demonstrating usage patterns

## Success Criteria

1. ✅ Method returns correct field names for simple models
2. ✅ Method returns correct dot-separated paths for nested models  
3. ✅ Scoped calls return relative field names correctly
4. ✅ Error handling works for invalid paths
5. ✅ Performance is acceptable for complex nested models
6. ✅ API is consistent with existing `get_*` method patterns
7. ✅ Comprehensive test coverage (>95%)
8. ✅ Documentation is complete and includes examples

## Future Enhancements

- Optional filtering by field type or metadata attributes
- Support for array/list field indexing in paths
- Integration with IDE auto-completion for field paths
