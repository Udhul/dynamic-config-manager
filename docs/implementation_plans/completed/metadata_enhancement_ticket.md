# Enhancement Ticket: Complete Field Metadata Access

## Problem Statement

The `ConfigInstance.get_metadata()` method currently returns incomplete field metadata, missing important `ConfigField` attributes that users expect to access programmatically. Specifically:

- `description` from the field definition
- `ui_hint`, `ui_extra`, `options` from `ConfigField` parameters
- `autofix_settings`, `format_spec` from validation configuration
- Full `json_schema_extra` content

This forces users to access the underlying Pydantic model directly, breaking the abstraction and making the API inconsistent.

## Current Behavior

```python
class MyConfig(DynamicBaseSettings):
    field: str = ConfigField("default", description="My field", ui_hint="TextBox", options=["a", "b"])

cfg = ConfigManager.register("test", MyConfig)
meta = cfg.get_metadata("field")
# meta only contains: type, required, default, editable, constraints, active_value, default_value
# Missing: description, ui_hint, options, full json_schema_extra
```

## Proposed Solution

### 1. Enhance `get_metadata()` Method

Modify `ConfigInstance.get_metadata()` in `dynamic_config_manager/manager.py`:

```python
def get_metadata(self, path: str, default: Any | None = None) -> Dict[str, Any] | Any:
    try:
        # ... existing field extraction logic ...
        
        meta = {
            "type": field.annotation,
            "required": field.is_required(),
            "default": field.default,
            "description": field.description,  # NEW: Include description
            "editable": (field.json_schema_extra or {}).get("editable", True),
            **_extract_constraints(field),
            "active_value": active_val,
            "default_value": default_val,
        }
        
        # NEW: Include full json_schema_extra content
        if field.json_schema_extra:
            meta["json_schema_extra"] = field.json_schema_extra.copy()
            
            # NEW: Flatten common ConfigField attributes for convenience
            common_attrs = ["ui_hint", "ui_extra", "options", "autofix_settings", "format_spec"]
            for attr in common_attrs:
                if attr in field.json_schema_extra:
                    meta[attr] = field.json_schema_extra[attr]
        
        # ... existing saved_value logic ...
        return meta
    except Exception:
        return default
```

### 2. Update `_MetaAccessorProxy`

Ensure the `.meta` accessor also returns the enhanced metadata:

```python
class _MetaAccessorProxy:
    def __getattr__(self, name: str) -> Any:
        return self._config_instance.get_metadata(name)
```

## Expected Behavior After Fix

```python
class MyConfig(DynamicBaseSettings):
    field: str = ConfigField("default", description="My field", ui_hint="TextBox", options=["a", "b"])

cfg = ConfigManager.register("test", MyConfig)
meta = cfg.get_metadata("field")

# All attributes now accessible:
print(meta["description"])      # "My field"
print(meta["ui_hint"])          # "TextBox"  
print(meta["options"])          # ["a", "b"]
print(meta["json_schema_extra"]) # Full dict with all ConfigField extras

# Also works with .meta accessor:
print(cfg.meta.field["ui_hint"]) # "TextBox"
```

## Implementation Checklist

- [ ] Modify `ConfigInstance.get_metadata()` method
- [ ] Should also work with `.meta` accessor
- [ ] Should robustly handle missing fields
- [ ] Should consistently return a `dict` with all attributes registered in `ConfigField`
- [ ] Add `description` field to metadata response
- [ ] Include full `json_schema_extra` in metadata response
- [ ] Flatten common ConfigField attributes to top level
- [ ] Ensure backward compatibility (existing keys unchanged)
- [ ] Add unit tests for new metadata fields
- [ ] Update relevant docs to reflect new metadata structure
- [ ] Test with nested field paths (`"parent.child.field"`)

## Testing Requirements

1. **Unit Tests**: Verify all ConfigField attributes appear in metadata
2. **Backward Compatibility**: Ensure existing metadata keys still work
3. **Nested Fields**: Test metadata access for nested model fields
4. **Edge Cases**: Handle fields without json_schema_extra gracefully

## Files to Modify

- `dynamic_config_manager/manager.py` - Main implementation
- `tests/test_metadata.py` - New test cases
- `docs/api_reference.md` - Update metadata documentation
- `docs/user_guide.md` - Mention how to access metadata fields
- `docs/full_specification.md` - Update the specification accordingly

## Backward Compatibility

This change is fully backward compatible:
- All existing metadata keys remain unchanged
- New keys are additive only
- No breaking changes to method signatures
- Existing code continues to work without modification

## Benefits

1. **Complete API**: Users can access all field metadata through the intended API
2. **Consistency**: No need to access underlying Pydantic models directly  
3. **UI Integration**: Full metadata enables rich UI generation
4. **Developer Experience**: Simpler, more intuitive metadata access