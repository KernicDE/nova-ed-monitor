"""Elite Dangerous keybindings file monitor.

Watches the active .binds file (and preset selection) for changes.
On every detected change a timestamped backup is created in
~/.config/nova/bindings_backup/ and an info event is pushed to the UI log.

Only the 5 most recent backups are kept; older ones are pruned automatically.
No TTS is triggered and no config option gates this behaviour — it always runs
when the bindings directory can be found.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import AppState, EventCategory, LogEvent

_log = logging.getLogger("nova.bindings")


# ── Discovery ──────────────────────────────────────────────────────────────────

def discover_bindings_dir(journal_dir: Path) -> Optional[Path]:
    """Return the ED Options/Bindings directory, or None if not found.

    The journal directory is:
      .../steamuser/Saved Games/Frontier Developments/Elite Dangerous
    Walking up 3 levels yields:
      .../steamuser/
    The bindings dir is then:
      .../steamuser/AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings/
    This path works for both Windows-native installs and Linux/Proton.
    """
    try:
        steam_user = journal_dir.parent.parent.parent
        bindings = (
            steam_user
            / "AppData" / "Local"
            / "Frontier Developments" / "Elite Dangerous"
            / "Options" / "Bindings"
        )
        if bindings.is_dir():
            return bindings
    except Exception:
        pass
    return None


def _read_preset(bindings_dir: Path) -> str:
    """Return the active preset name from StartPreset.4.start."""
    start_file = bindings_dir / "StartPreset.4.start"
    try:
        return start_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _active_binds_file(bindings_dir: Path, preset: str) -> Optional[Path]:
    """Return the active .binds path for the given preset name, or None."""
    for suffix in (f"{preset}.4.2.binds", f"{preset}.4.0.binds", f"{preset}.binds"):
        p = bindings_dir / suffix
        if p.exists():
            return p
    return None


# ── Backup helpers ─────────────────────────────────────────────────────────────

def _backup(src: Path, backup_dir: Path) -> Path:
    """Copy *src* to a timestamped file inside *backup_dir*. Returns new path."""
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest = backup_dir / f"{src.stem}_{ts}.binds"
    shutil.copy2(str(src), str(dest))
    return dest


def _prune(backup_dir: Path, keep: int = 5) -> None:
    """Delete the oldest .binds backups, keeping at most *keep* files."""
    try:
        files = sorted(
            backup_dir.glob("*.binds"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


# ── Monitor thread ─────────────────────────────────────────────────────────────

def monitor(
    state:       AppState,
    lock:        threading.RLock,
    journal_dir: Path,
    cfg_dir:     Path,
) -> None:
    """Daemon thread: watch .binds files and back them up on change.

    Exits immediately (silently) if the bindings directory cannot be found —
    this is expected when journal_dir is the fallback '.' path or on a platform
    where the bindings dir layout differs.
    """
    bindings_dir = discover_bindings_dir(journal_dir)
    if bindings_dir is None:
        _log.debug("Bindings directory not found — monitor inactive")
        return

    backup_dir = cfg_dir / "bindings_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    _log.info(f"Watching bindings: {bindings_dir}")

    # last known mtime for each .binds path
    last_mtimes: dict[Path, float] = {}
    # last known preset name (list so inner functions can mutate it)
    last_preset: list[str] = [""]

    while True:
        try:
            _poll(state, lock, bindings_dir, backup_dir, last_mtimes, last_preset)
        except Exception as exc:
            _log.warning(f"Bindings poll error: {exc}")
        time.sleep(2.0)


def _poll(
    state:        AppState,
    lock:         threading.RLock,
    bindings_dir: Path,
    backup_dir:   Path,
    last_mtimes:  dict,
    last_preset:  list,
) -> None:
    """Single poll cycle: check preset file and all .binds files."""

    # ── Preset switch detection ────────────────────────────────────────────────
    preset = _read_preset(bindings_dir)
    if preset and preset != last_preset[0] and last_preset[0] != "":
        _log.info(f"Binding preset changed: '{last_preset[0]}' → '{preset}'")
        # Back up the newly-active file so we have a snapshot at time of switch
        binds = _active_binds_file(bindings_dir, preset)
        if binds:
            try:
                dest = _backup(binds, backup_dir)
                _prune(backup_dir)
                _log.info(f"Preset switch backup: {dest.name}")
                with lock:
                    state.push_event(LogEvent.new(
                        EventCategory.System,
                        f"Binding preset changed to '{preset}' — backup saved",
                    ))
            except OSError as exc:
                _log.warning(f"Backup failed on preset switch: {exc}")
    if preset:
        last_preset[0] = preset

    # ── .binds file change detection ──────────────────────────────────────────
    try:
        binds_files = list(bindings_dir.glob("*.binds"))
    except OSError:
        return

    for binds_file in binds_files:
        try:
            mtime = binds_file.stat().st_mtime
        except OSError:
            continue

        prev = last_mtimes.get(binds_file)
        last_mtimes[binds_file] = mtime

        if prev is None:
            # First time we see this file — record mtime but don't back up yet
            continue

        if mtime == prev:
            continue

        # File changed since last check → back it up
        try:
            dest = _backup(binds_file, backup_dir)
            _prune(backup_dir)
            _log.info(f"Bindings changed: {binds_file.name} → {dest.name}")
            with lock:
                state.push_event(LogEvent.new(
                    EventCategory.System,
                    f"Keybindings backed up: {binds_file.stem}",
                ))
        except OSError as exc:
            _log.warning(f"Backup failed for {binds_file.name}: {exc}")
