import json
import os
import tempfile
import logging
import copy
from typing import Dict, Type, Optional, Any, List, TypeVar, Union
from pydantic import BaseModel, Field, ValidationError, SecretStr
from pydantic_settings import BaseSettings
# Import PydanticUndefined helper
try:
    from pydantic_core import PydanticUndefined
except ImportError:
    PydanticUndefined = object() # Fallback

logger = logging.getLogger(__name__)

SettingsModelType = TypeVar('SettingsModelType', bound=BaseSettings)

class ConfigInstance:
    """
    Manages a single configuration set (default, active, saved state)
    backed by a Pydantic BaseSettings model.
    """
    def __init__(self,
                 name: str,
                 settings_model: Type[SettingsModelType],
                 save_path: Optional[str] = None,
                 auto_save: bool = False):
        self.name = name
        if not issubclass(settings_model, BaseSettings):
            raise TypeError("settings_model must be a subclass of pydantic_settings.BaseSettings")
        self._settings_model: Type[SettingsModelType] = settings_model
        self._save_path = os.path.abspath(save_path) if save_path else None
        self._auto_save = auto_save
        # Reference to the singleton config manager instance
        self._manager = _manager_instance

        # --- State Management ---
        # 1. Original Defaults: Captured once from the model definition
        try:
            self._default_settings: SettingsModelType = self._settings_model()
            logger.debug(f"Captured initial defaults for '{self.name}'.")
        except ValidationError as e:
            logger.error(f"CRITICAL: Error creating default settings for '{self.name}' using model "
                         f"{self._settings_model.__name__}. Check model defaults & validators: {e}")
            raise ValueError(f"Could not initialize default settings for '{self.name}'.") from e

        # 2. Active Settings: Loaded from file or initialized from defaults
        self._active_settings: SettingsModelType = self._load_or_get_defaults()
        # --- End State Management ---

        self._ensure_save_dir_exists()

        logger.info(f"Initialized ConfigInstance '{self.name}' (Model: {self._settings_model.__name__}, "
                    f"Save path: {self._save_path or 'None'}, AutoSave: {self._auto_save})")

    def save(self, settings_object: Optional[SettingsModelType] = None):
        """Saves the current active settings (or provided object) to the JSON file."""
        save_path = self._resolve_save_path()
        
        if not save_path:
            logger.warning(f"No save path specified for config '{self.name}' and no default directory configured. Cannot save.")
            return False
            
        target_settings = settings_object if settings_object is not None else self._active_settings
        
        # Basic type check
        if not isinstance(target_settings, self._settings_model):
            logger.error(f"Attempted to save an object of incorrect type for config '{self.name}'.")
            return False  # <-- Added return False here
        
        # Ensure the directory exists
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            try:
                os.makedirs(save_dir, exist_ok=True)
                logger.info(f"Created configuration directory: {save_dir}")
            except OSError as e:
                logger.error(f"Error creating directory {save_dir} for config '{self.name}': {e}", exc_info=True)
                return False
                
        try:
            config_data = target_settings.model_dump(mode='json', exclude_defaults=False)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Config '{self.name}' saved successfully to {save_path}")
            return True
        except TypeError as e:
            logger.error(f"Serialization Error saving config '{self.name}'. Check data types. Error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error writing config '{self.name}' to {save_path}: {e}", exc_info=True)
            return False

    def _resolve_save_path(self) -> Optional[str]:
        """
        Helper method to resolve the correct save path, using default if needed.
        Returns None if no valid save path could be determined.
        """
        if self._save_path:
            return self._save_path
            
        # No specific save path, try using default directory
        default_dir = self._manager.default_save_dir
        if default_dir:
            return os.path.join(default_dir, f"{self.name}.json")
            
        # No default directory configured
        return None
    
    def _ensure_save_dir_exists(self):
        """Creates the directory for the save file if it doesn't exist."""
        save_path = self._resolve_save_path()
        if save_path:
            dir_name = os.path.dirname(save_path)
            if dir_name and not os.path.exists(dir_name):
                try:
                    os.makedirs(dir_name, exist_ok=True)
                    logger.info(f"Created configuration directory: {dir_name}")
                except OSError as e:
                    logger.warning(f"Could not create directory {dir_name} for config '{self.name}'. Saving might fail. Error: {e}")

    def _load_or_get_defaults(self) -> SettingsModelType:
        """Loads settings from save_path using Pydantic, falling back to code defaults."""
        save_path = self._resolve_save_path()
        
        if save_path and os.path.exists(save_path):
            try:
                logger.debug(f"Attempting to load config '{self.name}' from {save_path}")
                # Load and validate from the resolved path
                with open(save_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                loaded_settings = self._settings_model(**data)
                logger.info(f"Successfully loaded and validated config '{self.name}' from {save_path}")
                return loaded_settings
                
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in config file '{save_path}' for '{self.name}'. Using defaults. Error: {e}")
            except ValidationError as e:
                logger.warning(f"Data validation errors loading config '{self.name}' from '{save_path}'. "
                            f"Using defaults. Please check/fix the file. Errors:\n{e}")
            except FileNotFoundError:
                logger.warning(f"Config file '{save_path}' not found for '{self.name}' during load attempt. Using defaults.")
            except Exception as e:
                logger.error(f"Unexpected error loading config '{self.name}' from {save_path}. Using defaults. Error: {e}", exc_info=True)
        else:
            if save_path:
                logger.info(f"Config file '{save_path}' not found for '{self.name}'. Initializing with defaults.")
                # Create the file from default immediately if missing
                self.save(self._default_settings)
            else:
                logger.info(f"No save path for '{self.name}'. Initializing with defaults.")
                
        # Fallback: Return a pristine copy of the original defaults
        logger.debug(f"Using code-defined defaults for '{self.name}'.")
        return self._default_settings.model_copy(deep=True)

    @property
    def active(self) -> SettingsModelType:
        """Returns the currently active settings object (read-only recommended)."""
        return self._active_settings

    def get_value(self, key_path: str) -> Any:
        """
        Gets a value from the active configuration using a '/' delimited path for nesting.
        """
        keys = key_path.split('/')
        current_obj = self._active_settings
        try:
            for i, key in enumerate(keys):
                if isinstance(current_obj, BaseModel):
                    if key not in current_obj.model_fields:
                        raise KeyError(f"Key '{key}' not found in model.")
                    current_obj = getattr(current_obj, key)
                elif isinstance(current_obj, dict):
                     if key not in current_obj:
                        raise KeyError(f"Key '{key}' not found in dict.")
                     current_obj = current_obj[key]
                elif isinstance(current_obj, list):
                    try:
                        idx = int(key)
                        if idx >= len(current_obj):
                            raise IndexError("Index out of bounds")
                        current_obj = current_obj[idx]
                    except (ValueError, IndexError):
                        raise KeyError(f"Invalid list index '{key}' in path '{key_path}'.")
                else:
                    # Trying to traverse into a non-container type
                    remaining_path = "/".join(keys[i:])
                    raise TypeError(f"Cannot traverse path further at '{remaining_path}'. Object is not a Model or dict.")

            # Handle SecretStr automatically for safety if needed, but often better left to caller
            # if isinstance(current_obj, SecretStr):
            #     return current_obj.get_secret_value()
            return current_obj
        except (KeyError, AttributeError, TypeError, IndexError) as e:
            logger.error(f"Error getting value for path '{key_path}' in config '{self.name}': {e}")
            raise ValueError(f"Invalid key path '{key_path}' for config '{self.name}'.") from e

    def set_value(self, key_path: str, value: Any):
        """
        Sets a value in the active configuration using a '/' delimited path,
        re-validates the entire model, and auto-saves if enabled.
        """
        keys = key_path.split('/')
        target_key = keys[-1]
        parent_keys = keys[:-1]

        # Check editability/locked status *before* attempting modification
        try:
            metadata = self.get_field_metadata(key_path)
            if metadata.get('editable') is False: # Check for explicit False
                logger.warning(f"Attempt blocked: Setting field '{key_path}' in config '{self.name}' is not allowed (editable=False).")
                raise PermissionError(f"Field '{key_path}' is not editable.")
        except ValueError:
            # If path doesn't resolve to a field (e.g., setting dict key), metadata check might fail - proceed carefully
            logger.debug(f"Could not get specific field metadata for path '{key_path}'. Proceeding without editability check.")
        except PermissionError:
            raise # Re-raise the permission error cleanly

        try:
            # Use model_copy and update for immutability benefits and easier validation
            # Create a deep copy of the current active data
            current_data = self._active_settings.model_dump(mode='python') # Use python mode for complex objects

            # Navigate to the parent dictionary/object
            parent_obj_data = current_data
            for key in parent_keys:
                if key not in parent_obj_data or not isinstance(parent_obj_data[key], (dict)):
                    # This case should ideally not happen if structure matches model, but handle defensively
                    logger.error(f"Invalid structure for path '{key_path}' when trying to set value.")
                    raise ValueError(f"Cannot find or access parent element for path '{key_path}' in config '{self.name}'.")
                parent_obj_data = parent_obj_data[key]

            # Set the value in the copied data structure
            parent_obj_data[target_key] = value

            # Re-validate the entire structure by creating a new model instance
            new_settings = self._settings_model(**current_data)

            # If validation passes, update the active settings
            self._active_settings = new_settings

            # Log safely
            log_value = value
            if isinstance(value, SecretStr): log_value = "***"
            elif isinstance(getattr(self._active_settings, target_key, None) if not parent_keys else None, SecretStr): log_value = "***" # Crude check
            logger.debug(f"Set '{self.name}.{key_path}' = {log_value}")

            if self._auto_save:
                self.save()

        except ValidationError as e:
            logger.error(f"Validation Error setting '{self.name}.{key_path}':\n{e}")
            raise # Re-raise for the caller
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.error(f"Error setting value for path '{key_path}' in config '{self.name}': {e}")
            raise ValueError(f"Could not set value for path '{key_path}': {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error setting '{self.name}.{key_path}': {e}", exc_info=True)
            raise

    def get_field_metadata(self, key_path: str) -> Dict[str, Any]:
        """
        Retrieves consolidated metadata for a specific field using a '/' delimited path.
        """
        keys = key_path.split('/')
        current_model_or_field = self._settings_model
        current_instance_for_default = self._default_settings # Use default instance to get actual default value

        field_info = None
        field_key = None

        try:
            for i, key in enumerate(keys):
                field_key = key
                if hasattr(current_model_or_field, 'model_fields') and key in current_model_or_field.model_fields:
                    field_info = current_model_or_field.model_fields[key]
                    # Move to the nested model type for the next iteration, if applicable
                    current_model_or_field = field_info.annotation
                    # Get nested default value
                    if hasattr(current_instance_for_default, key):
                        current_instance_for_default = getattr(current_instance_for_default, key)
                    else:
                        current_instance_for_default = None # Cannot traverse further
                # Handling traversal into Dict fields (metadata applies to values or the dict itself)
                elif isinstance(getattr(current_model_or_field, '__origin__', None), type) and issubclass(current_model_or_field.__origin__, Dict):
                    # We've hit a Dict. Metadata usually defined on the Dict field itself.
                    # The path now refers to a *key* within the dict, not a model field.
                    # Return the metadata of the Dict field itself.
                    # Further path elements (dict keys) don't have separate Pydantic metadata.
                    if field_info: # Use metadata from the Dict Field
                        break
                    else: raise KeyError(f"Path traverses into a Dict, but no field info found before it.")
                # Handling traversal into List fields
                elif isinstance(getattr(current_model_or_field, '__origin__', None), type) and issubclass(current_model_or_field.__origin__, List):
                    # Similar to Dict, metadata applies to the List field.
                    if field_info: # Use metadata from the List Field
                        break
                    else: raise KeyError(f"Path traverses into a List, but no field info found before it.")
                else:
                    # Path doesn't correspond to a model field at this level
                    raise KeyError(f"Key '{key}' not found as a model field in the current structure.")

            if not field_info:
                raise ValueError(f"Path '{key_path}' did not resolve to a specific model field.")

            # --- Consolidate Metadata ---
            metadata = copy.deepcopy(field_info.json_schema_extra or {})

            metadata['name'] = field_key # The specific field name
            metadata['path'] = key_path # The full path provided
            metadata['description'] = field_info.description or ""
            metadata['type'] = field_info.annotation # Python type hint
            metadata['required'] = field_info.is_required()

            # Get default value correctly, handling factories
            default_val = PydanticUndefined
            # Check for default value using hasattr instead of method call
            if hasattr(field_info, 'default') and field_info.default is not PydanticUndefined:
                default_val = field_info.default
            elif hasattr(field_info, 'default_factory') and field_info.default_factory is not None:
                # Call the factory to get the default value
                default_val = field_info.default_factory()
        
            # Use value from _default_settings instance if available (covers nested defaults)
            if current_instance_for_default is not None and hasattr(current_instance_for_default, '__class__') and field_key in getattr(current_instance_for_default.__class__, 'model_fields', {}):
                # This might be more reliable than using default_val from field_info
                pass

            metadata['default'] = default_val

            # Extract Pydantic constraints
            constraints = {}
            if hasattr(field_info, 'metadata'):
                for item in field_info.metadata:
                    if hasattr(item, 'gt'): constraints['gt'] = item.gt
                    if hasattr(item, 'ge'): constraints['ge'] = item.ge
                    if hasattr(item, 'lt'): constraints['lt'] = item.lt
                    if hasattr(item, 'le'): constraints['le'] = item.le
                    if hasattr(item, 'multiple_of'): constraints['multiple_of'] = item.multiple_of
                    if hasattr(item, 'min_length'): constraints['min_length'] = item.min_length
                    if hasattr(item, 'max_length'): constraints['max_length'] = item.max_length
                    if hasattr(item, 'pattern'): constraints['pattern'] = item.pattern
            metadata['constraints'] = constraints

            # Convenience min/max (prefer json_schema_extra if defined)
            metadata['min'] = metadata.get('min', constraints.get('ge', constraints.get('gt')))
            metadata['max'] = metadata.get('max', constraints.get('le', constraints.get('lt')))

            # Editable/Locked status (default to True if not specified)
            metadata['editable'] = metadata.get('editable', True)

            # Add actual current value
            try:
                metadata['value'] = self.get_value(key_path)
            except ValueError:
                metadata['value'] = PydanticUndefined # Or None, indicate value couldn't be retrieved

            return metadata

        except (KeyError, AttributeError, ValueError, IndexError) as e:
            logger.warning(f"Could not retrieve metadata for path '{key_path}' in config '{self.name}': {e}")
            raise ValueError(f"Invalid path or structure for retrieving metadata: '{key_path}'.") from e


    def get_all_field_paths(self, current_model=None, current_path="", separator="/") -> List[str]:
        """Recursively finds all possible key paths for the settings model."""
        if current_model is None:
            current_model = self._settings_model

        paths = []
        if not hasattr(current_model, 'model_fields'):
            return paths # Not a Pydantic model/BaseSettings

        for name, field_info in current_model.model_fields.items():
            new_path = f"{current_path}{separator}{name}" if current_path else name
            paths.append(new_path)

            # Recurse if the annotation is a Pydantic model itself
            field_type = field_info.annotation
            origin = getattr(field_type, '__origin__', None)
            args = getattr(field_type, '__args__', ())

            nested_model_type = None
            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                nested_model_type = field_type
            elif origin and args:
                 # Check for Optional[Model], Union[Model, ...], List[Model], Dict[Any, Model]
                 if origin is Union or origin is Optional:
                    model_args = [arg for arg in args if isinstance(arg, type) and issubclass(arg, BaseModel)]
                    if model_args: nested_model_type = model_args[0] # Take first model type
                 elif origin is List and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    # Cannot recurse into list items this way, path ends here
                    # paths.extend(self.get_all_field_paths(args[0], new_path + separator + "0")) # Example index
                     pass
                 elif origin is Dict and args and len(args) > 1 and isinstance(args[1], type) and issubclass(args[1], BaseModel):
                    # Cannot recurse into dict values this way, path ends here
                    # paths.extend(self.get_all_field_paths(args[1], new_path + separator + "key")) # Example key
                    pass

            if nested_model_type:
                paths.extend(self.get_all_field_paths(nested_model_type, new_path, separator))

        return paths

    def restore_key_to_default(self, key_path: str):
        """Restores a single key (using path) in the active config to its original code-defined default value."""
        try:
            # Navigate the default settings object to get the default value
            keys = key_path.split('/')
            default_value_obj = self._default_settings
            for key in keys:
                if isinstance(default_value_obj, BaseModel):
                    default_value_obj = getattr(default_value_obj, key)
                elif isinstance(default_value_obj, dict):
                    default_value_obj = default_value_obj[key]
                # Cannot reliably get default for list/dict elements this way
                else: raise ValueError("Cannot traverse default structure further.")

            # Need to handle potential deep copies if default is mutable
            default_value = copy.deepcopy(default_value_obj)

            # Log safely
            current_value_for_log = self.get_value(key_path)
            log_default = default_value
            if isinstance(current_value_for_log, SecretStr): current_value_for_log = "***"
            if isinstance(default_value, SecretStr): log_default = "***"

            logger.info(f"Restoring '{self.name}.{key_path}' from '{current_value_for_log}' to default '{log_default}'.")
            # Use set_value to ensure validation and auto-save logic applies
            self.set_value(key_path, default_value)

        except (KeyError, AttributeError, ValueError, IndexError) as e:
            logger.error(f"Failed to get default value for path '{key_path}' in config '{self.name}': {e}")
            raise ValueError(f"Could not restore default for path '{key_path}'.") from e
        except PermissionError as e:
            logger.error(f"Cannot restore default for '{key_path}': {e}") # Permission denied by set_value
            raise


    def restore_all_to_default(self):
        """Restores the entire active configuration to its original code-defined default state."""
        logger.info(f"Restoring all settings for config '{self.name}' to original defaults.")
        # Create a fresh copy from the stored defaults
        self._active_settings = self._default_settings.model_copy(deep=True)
        if self._auto_save:
            self.save()
        logger.info(f"Config '{self.name}' restored to defaults.")


# --- Singleton ConfigManager --- (Class _ConfigManagerInternal and instance creation remain the same)
class _ConfigManagerInternal:
    """Internal implementation of the ConfigManager."""
    def __init__(self):
        self._configs: Dict[str, ConfigInstance] = {}
        # Set the default save directory to temp folder
        self._default_save_dir = os.path.join(tempfile.gettempdir(), "Dynamic-Config-Manager")
        logger.info("Dynamic Config Manager initialized.")

    @property
    def default_save_dir(self) -> Optional[str]:
        """Returns the default directory where configs are saved if no specific path is provided."""
        return self._default_save_dir
        
    @default_save_dir.setter
    def default_save_dir(self, path: Optional[str]):
        """Sets the default save directory."""
        self.set_default_save_dir(path)
    
    def set_default_save_dir(self, path: Optional[str]) -> str:
        """
        Sets the default directory where configs will be saved when no specific path is provided.
        If path is None, reverts to using the temp directory.
        Ensures the directory exists.
        """
        if path is None:
            # Use temp directory if None is provided
            self._default_save_dir = os.path.join(tempfile.gettempdir(), "Dynamic-Config-Manager")
        else:
            # Use provided path
            self._default_save_dir = os.path.abspath(path)
        
        # Ensure the directory exists
        if self._default_save_dir and not os.path.exists(self._default_save_dir):
            try:
                os.makedirs(self._default_save_dir, exist_ok=True)
                logger.info(f"Created default configuration directory: {self._default_save_dir}")
            except OSError as e:
                logger.warning(f"Could not create default save directory {self._default_save_dir}. Error: {e}")
                
        logger.info(f"Default save directory set to: {self._default_save_dir}")
        return self._default_save_dir
    
    def register_config(self,
                        name: str,
                        settings_model: Type[SettingsModelType],
                        save_path: Optional[str] = None,
                        auto_save: bool = False) -> ConfigInstance:
        """Registers and initializes a new configuration instance."""
        if name in self._configs:
            logger.error(f"Configuration name '{name}' conflict. Already registered.")
            raise ValueError(f"Configuration with name '{name}' is already registered.")

        try:
            # Determine save path more intelligently (e.g., user config dir)
            if save_path and not os.path.isabs(save_path):
                # Example: Place in a standard user config location if relative
                APP_NAME = "YourAppName" # Define this globally or pass it in
                if os.name == 'nt':
                    base_dir = os.path.join(os.getenv('LOCALAPPDATA', os.getenv('APPDATA', '')), APP_NAME, 'Config')
                else:
                    base_dir = os.path.join(os.path.expanduser("~"), '.config', APP_NAME)
                if not base_dir: # Fallback if standard dirs fail
                    base_dir = os.path.join(os.path.expanduser("~"), f'.{APP_NAME.lower()}_config')

                final_save_path = os.path.join(base_dir, save_path)
                logger.debug(f"Resolved relative save path '{save_path}' to '{final_save_path}'")
            else:
                final_save_path = save_path # Use as is if absolute or None

            instance = ConfigInstance(
                name=name,
                settings_model=settings_model,
                save_path=final_save_path,
                auto_save=auto_save
            )
            self._configs[name] = instance
            logger.info(f"Successfully registered config instance: '{name}'")
            return instance
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to register config '{name}': {e}", exc_info=True)
            raise

    def get_config(self, name: str) -> ConfigInstance:
        """Retrieves a registered configuration instance by name."""
        try:
            return self._configs[name]
        except KeyError:
            logger.error(f"Attempted to access unregistered config: '{name}'")
            raise KeyError(f"Configuration '{name}' not found. Registered configs: {list(self._configs.keys())}")

    def get(self, name: str, default: Optional[Any] = None) -> Optional[ConfigInstance]:
        """Retrieves a config instance, returning None or a default if not found."""
        return self._configs.get(name, default)

    def save_all(self):
        """Saves all registered configurations."""
        logger.info("Attempting to save all configurations...")
        saved_count = 0
        failed_count = 0
        for name, config in self._configs.items():
            # Try to save each config (uses default save path if needed)
            if config.save():
                saved_count += 1
            else:
                failed_count += 1
                logger.warning(f"Failed to save config '{name}'.")
        
        logger.info(f"Save all complete. Saved: {saved_count}, Failed: {failed_count}")

    def restore_all_defaults(self):
        """Restores all registered configurations to their original code-defined default values."""
        logger.info("Restoring all configurations to defaults...")
        for config in self._configs.values():
            config.restore_all_to_default() # Delegates to ConfigInstance method
        logger.info("Restore all defaults complete.")

    def get_all_config_names(self) -> List[str]:
        """Returns a list of names of all registered configurations."""
        return list(self._configs.keys())

    def is_registered(self, name: str) -> bool:
        """Checks if a configuration name is already registered."""
        return name in self._configs

# --- Singleton Instance ---
_manager_instance = _ConfigManagerInternal()

# --- Public Access ---
ConfigManager = _manager_instance