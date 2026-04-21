"""Config and voiceline file watcher for NOVA.

Watches ~/.config/nova/config.toml and ~/.config/nova/voicelines/ for changes.
When a change is detected, reloads configuration and voiceline caches.

Usage:
    spawn(cfg_dir, on_config_changed, on_voicelines_changed)

Both callbacks are called from the watcher thread (not the main thread).
Keep them short and non-blocking.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

_log = logging.getLogger("nova.config_watcher")

_POLL_INTERVAL = 2.0  # seconds (fallback when watchdog unavailable)


def spawn(
    cfg_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> threading.Thread:
    """Start the watcher daemon thread and return it."""
    t = threading.Thread(
        target=_monitor,
        args=(cfg_dir, on_config_changed, on_voicelines_changed),
        name="nova-config-watcher",
        daemon=True,
    )
    t.start()
    return t


def _monitor(
    cfg_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    config_path   = cfg_dir / "config.toml"
    voiceline_dir = cfg_dir / "voicelines"
    changed       = threading.Event()

    # Try watchdog first, fall back to polling
    try:
        from watchdog.observers import Observer          # type: ignore[import]
        from watchdog.events import FileSystemEventHandler  # type: ignore[import]

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:       # type: ignore[override]
                changed.set()
            def on_created(self, event) -> None:        # type: ignore[override]
                changed.set()

        obs = Observer()
        obs.schedule(_Handler(), str(cfg_dir), recursive=True)
        obs.daemon = True
        obs.start()
        _log.info("Config watcher: watchdog active")

        while True:
            changed.wait()
            changed.clear()
            time.sleep(0.3)  # debounce
            _dispatch(on_config_changed, on_voicelines_changed)

    except Exception as exc:
        _log.warning("Config watcher: watchdog failed (%s) — polling every %.0fs", exc, _POLL_INTERVAL)
        _poll(config_path, voiceline_dir, on_config_changed, on_voicelines_changed)


def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _max_voiceline_mtime(voiceline_dir: Path) -> float:
    try:
        return max(
            (_get_mtime(p) for p in voiceline_dir.glob("*.toml")),
            default=0.0,
        )
    except OSError:
        return 0.0


def _poll(
    config_path: Path,
    voiceline_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    last_config_mtime    = _get_mtime(config_path)
    last_voiceline_mtime = _max_voiceline_mtime(voiceline_dir)
    while True:
        time.sleep(_POLL_INTERVAL)
        cur_config    = _get_mtime(config_path)
        cur_voiceline = _max_voiceline_mtime(voiceline_dir)
        if cur_config != last_config_mtime:
            last_config_mtime = cur_config
            try:
                on_config_changed()
            except Exception:
                _log.exception("Config reload callback failed")
        if cur_voiceline != last_voiceline_mtime:
            last_voiceline_mtime = cur_voiceline
            try:
                on_voicelines_changed()
            except Exception:
                _log.exception("Voiceline reload callback failed")


def _dispatch(
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    """Called after a watchdog event — call both reload callbacks."""
    try:
        on_config_changed()
    except Exception:
        _log.exception("Config reload callback failed")
    try:
        on_voicelines_changed()
    except Exception:
        _log.exception("Voiceline reload callback failed")
