from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, Tuple, Dict, Set, Any

from watchfiles import watch, Change

from .manager import ConfigManager

# Set up logging
log = logging.getLogger(__name__)


def _normalize_path(path: Path) -> str:
    """Return a normalized path for cross-platform compatibility.

    This handles:
    - Case sensitivity differences between Windows and Unix
    - Path resolution and canonicalization
    - Windows-specific path prefixes like \\?\\
    """
    try:
        # First resolve the path to handle symlinks and relative components
        resolved_path = path.resolve()
        # Then normalize case for Windows compatibility
        return os.path.normcase(str(resolved_path))
    except (OSError, ValueError) as e:
        log.warning(f"Failed to normalize path {path}: {e}")
        # Fallback to basic normalization
        return os.path.normcase(str(path))


def watch_and_reload(
    names: Iterable[str] | None = None,
    *,
    debounce: int = 500,
) -> Tuple[threading.Thread, threading.Event]:
    """Watch config files and reload them on modification.

    This helper starts a **daemon** thread that monitors the on‑disk files
    backing the given configuration instances. When one of those files is
    written (including the common *atomic‑rename* pattern used by many text
    editors and cross‑platform `Path.write_text()`), the instance is re‑loaded
    in memory so that the application immediately sees the updated values.

    Parameters
    ----------
    names : Iterable[str] | None
        If supplied, watch only the named configs; otherwise watch every
        registered `ConfigInstance` that has a ``_save_path``.
    debounce : int, default ``500``
        Milliseconds to wait after the *first* event in a burst before the
        event set is yielded (passed straight to :pyfunc:`watchfiles.watch`).

    Returns
    -------
    (thread, stop_event)
        The background watcher thread *and* an :class:`threading.Event` that
        can be set to stop it.
    """
    stop_event = threading.Event()

    # Convert names to set for faster lookup if provided
    watch_names = set(names) if names is not None else None

    def _watcher_loop() -> None:
        """Main watcher loop that runs in a background thread."""
        try:
            log.debug("Starting file watcher loop")

            # Build mapping from normalized file paths to config instances
            file_map: Dict[str, Any] = {}
            watch_directories: Set[Path] = set()

            # Collect all config instances that should be watched
            for config_name, config_instance in ConfigManager._instances.items():
                # Skip if we're only watching specific configs and this isn't one of them
                if watch_names is not None and config_name not in watch_names:
                    continue

                # Skip configs without file paths (memory-only configs)
                if config_instance._save_path is None:
                    continue

                try:
                    # Get the resolved file path
                    file_path = config_instance._save_path.resolve()
                    normalized_path = _normalize_path(file_path)

                    # Map normalized path to config instance
                    file_map[normalized_path] = config_instance

                    # Add the parent directory to our watch list
                    watch_directories.add(file_path.parent)

                    log.debug(f"Watching config '{config_name}' at {file_path}")

                except (OSError, ValueError) as e:
                    log.warning(f"Could not resolve path for config '{config_name}': {e}")
                    continue

            if not watch_directories:
                log.debug("No directories to watch, exiting watcher loop")
                return

            log.debug(f"Watching {len(watch_directories)} directories for {len(file_map)} config files")

            # Determine which file change events should trigger reloads
            reload_events = {Change.modified, Change.added}

            # Handle newer watchfiles versions that have 'moved' events for atomic saves
            # This is particularly important on Windows where editors often use atomic saves
            moved_event = getattr(Change, "moved", None)
            if moved_event is None:
                # Try alternative naming in older versions
                moved_event = getattr(Change, "move", None)
            if moved_event is not None:
                reload_events.add(moved_event)
                log.debug(f"Including moved/atomic save events: {moved_event}")

            log.debug(f"Watching for events: {reload_events}")

            # Main file watching loop
            for change_batch in watch(*watch_directories, debounce=debounce, stop_event=stop_event):
                if stop_event.is_set():
                    break

                log.debug(f"File changes detected: {change_batch}")

                # Collect affected config instances (avoid duplicates)
                affected_configs: Set[Any] = set()

                for change_type, changed_path_str in change_batch:
                    # Skip change types we don't care about
                    if change_type not in reload_events:
                        log.debug(f"Ignoring change type {change_type} for {changed_path_str}")
                        continue

                    try:
                        changed_path = Path(changed_path_str)
                        normalized_changed_path = _normalize_path(changed_path)

                        # Look for exact file match
                        config_instance = file_map.get(normalized_changed_path)
                        if config_instance is not None:
                            log.debug(f"Found exact match for {changed_path_str}")
                            affected_configs.add(config_instance)
                            continue

                        # For atomic saves, editors might create a temp file and rename it
                        # Check if this is a rename into a directory we're watching
                        parent_dir = changed_path.parent
                        normalized_parent = _normalize_path(parent_dir)

                        # Look for any config files in this directory
                        for file_path, instance in file_map.items():
                            file_path_obj = Path(file_path)
                            if _normalize_path(file_path_obj.parent) == normalized_parent:
                                if file_path_obj.name == changed_path.name:
                                    log.debug(f"Found parent directory match for {changed_path_str}")
                                    affected_configs.add(instance)
                                    break

                    except (OSError, ValueError) as e:
                        log.warning(f"Error processing changed path {changed_path_str}: {e}")
                        continue

                # Reload each affected config instance
                for config_instance in affected_configs:
                    _reload_config_instance(config_instance)

        except Exception as e:
            log.error(f"File watcher loop failed: {e}", exc_info=True)
        finally:
            log.debug("File watcher loop exiting")

    def _reload_config_instance(config_instance: Any) -> None:
        """Reload a single config instance from disk with retry logic."""
        config_name = getattr(config_instance, 'name', '<unknown>')
        log.debug(f"Reloading config '{config_name}'")

        # Retry loading with exponential backoff to handle cases where
        # the file is temporarily locked by the writing process
        max_attempts = 5
        base_delay = 0.01  # Start with 10ms delay

        for attempt in range(max_attempts):
            try:
                loaded_instance = config_instance._load_from_disk()

                if loaded_instance is not None:
                    # Successfully loaded new configuration
                    config_instance._active = loaded_instance
                    log.debug(f"Successfully reloaded config '{config_name}' on attempt {attempt + 1}")
                    return
                else:
                    # _load_from_disk returned None, which means parsing failed
                    log.debug(f"Failed to parse config '{config_name}' on attempt {attempt + 1}")

            except Exception as e:
                log.warning(f"Error loading config '{config_name}' on attempt {attempt + 1}: {e}")

            # Wait before retrying, with exponential backoff
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)

        # All attempts failed, check if file still exists
        try:
            if config_instance._save_path and not config_instance._save_path.exists():
                log.info(f"Config file for '{config_name}' no longer exists, resetting to defaults")
                config_instance._active = config_instance._defaults.model_copy(deep=True)
            else:
                log.warning(f"Failed to reload config '{config_name}' after {max_attempts} attempts, keeping current state")
        except Exception as e:
            log.error(f"Error checking if config file exists for '{config_name}': {e}")

    # Create and start the watcher thread
    thread = threading.Thread(target=_watcher_loop, daemon=True, name="ConfigWatcher")
    thread.start()

    log.debug(f"Started file watcher thread: {thread.name}")
    return thread, stop_event


__all__ = ["watch_and_reload"]
