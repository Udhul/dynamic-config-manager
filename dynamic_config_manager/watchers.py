from __future__ import annotations

import threading
from pathlib import Path
from typing import Iterable, Tuple

from watchfiles import watch, Change

from .manager import ConfigManager

__all__ = ["watch_and_reload"]


def watch_and_reload(
    names: Iterable[str] | None = None,
    *,
    debounce: int = 500,
) -> Tuple[threading.Thread, threading.Event]:
    """Watch config files and reload them on modification.

    Parameters
    ----------
    names : Iterable[str] | None
        Specific config names to watch. If None, watch all registered configs.
    debounce : int
        Debounce interval passed to ``watchfiles.watch`` in milliseconds.

    Returns
    -------
    (thread, stop_event)
        The background watcher thread and an event which can be set to stop it.
    """

    stop_event = threading.Event()

    def _loop() -> None:
        file_map: dict[Path, object] = {}
        watch_paths = set()
        for name, inst in ConfigManager._instances.items():
            if names and name not in names:
                continue
            if inst._save_path:
                fpath = inst._save_path.resolve()
                file_map[fpath] = inst
                watch_paths.add(fpath if fpath.exists() else fpath.parent)

        if not watch_paths:
            return

        for changes in watch(*watch_paths, debounce=debounce, stop_event=stop_event):
            for change, p in changes:
                if change not in (Change.modified, Change.added):
                    continue
                path = Path(p).resolve()
                inst = file_map.get(path) or file_map.get(path.parent)
                if inst:
                    loaded = inst._load_from_disk()
                    inst._active = loaded or inst._defaults.model_copy(deep=True)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread, stop_event
