"""Screenshot processing thread.

Monitors the ED screenshot folder, converts BMP → PNG (or renames existing
PNGs), and moves files to the configured destination directory.

Naming scheme: YYYY-MM-DD-HH-MM_CMDR_SYSTEM_BODY.png
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import AppState

_log = logging.getLogger("nova.screenshots")

# Supported source extensions (ED saves BMP on older builds, PNG on newer)
_SRC_EXTS = {".bmp", ".png"}


def _default_screenshot_dirs() -> list[Path]:
    """Return candidate ED screenshot directories in priority order."""
    home = Path.home()
    proton_base = home / ".local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Pictures/Frontier Developments/Elite Dangerous"
    return [
        # Proton default
        proton_base,
        home / ".steam/steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Pictures/Frontier Developments/Elite Dangerous",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Pictures/Frontier Developments/Elite Dangerous",
        # Windows native / WSL
        home / "Pictures/Frontier Developments/Elite Dangerous",
        # macOS
        home / "Pictures/Frontier Developments/Elite Dangerous",
    ]


def _find_screenshot_dir() -> Optional[Path]:
    for p in _default_screenshot_dirs():
        if p.is_dir():
            return p
    return None


def _sanitize(s: str) -> str:
    """Replace spaces with hyphens and strip chars invalid in filenames."""
    s = s.replace(" ", "-")
    s = re.sub(r"[^\w\-]", "", s)
    return s[:40]  # cap length


def _build_dest_name(state: AppState) -> str:
    ts   = datetime.now().strftime("%Y-%m-%d-%H-%M")
    cmdr = _sanitize(state.commander or "CMDR")
    sys  = _sanitize(state.system or "Unknown")
    body = _sanitize(state.approach_body or state.nearest_body or "")
    parts = [ts, cmdr, sys]
    if body:
        parts.append(body)
    return "_".join(parts) + ".png"


def _process_file(src: Path, dest_dir: Path, state: AppState) -> bool:
    """Convert/rename *src* to dest_dir with the current state-derived name.
    Returns True on success."""
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_name = _build_dest_name(state)
        dest_path = dest_dir / dest_name

        # Avoid overwriting if name collides (add counter suffix)
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / (dest_path.stem + f"_{counter}" + ".png")
            counter += 1

        if src.suffix.lower() == ".bmp":
            try:
                from PIL import Image
                with Image.open(src) as img:
                    img.save(dest_path, "PNG")
                src.unlink()
                _log.info(f"Converted BMP → PNG: {dest_path.name}")
                return True
            except ImportError:
                _log.warning("Pillow not installed; copying BMP without conversion.")
                dest_path = dest_path.with_suffix(".bmp")
        # PNG or fallback
        src.rename(dest_path)
        _log.info(f"Moved screenshot: {dest_path.name}")
        return True
    except Exception as exc:
        _log.warning(f"Screenshot processing failed for {src}: {exc}")
        return False


def monitor(state: AppState, lock: threading.RLock, cfg) -> None:
    """Main loop. Runs in the nova-screenshots daemon thread."""
    # Resolve source dir
    if cfg.screenshot_dir:
        src_dir = Path(cfg.screenshot_dir).expanduser()
    else:
        src_dir = _find_screenshot_dir()

    if src_dir is None or not src_dir.is_dir():
        _log.debug("No ED screenshot directory found; screenshot monitor idle.")
        # Recheck every 30 s in case the game is launched later
        while True:
            time.sleep(30)
            if cfg.screenshot_dir:
                src_dir = Path(cfg.screenshot_dir).expanduser()
            else:
                src_dir = _find_screenshot_dir()
            if src_dir and src_dir.is_dir():
                break

    # Resolve destination dir
    if cfg.screenshot_dest:
        dest_dir = Path(cfg.screenshot_dest).expanduser()
    else:
        dest_dir = Path.home() / "Pictures" / "Elite Dangerous"

    _log.info(f"Screenshot monitor: watching {src_dir} → {dest_dir}")

    # Track already-seen files by (path, mtime) to avoid double-processing
    seen: set[tuple[str, float]] = set()

    while True:
        try:
            if src_dir.is_dir():
                for entry in src_dir.iterdir():
                    if entry.suffix.lower() not in _SRC_EXTS:
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                    except OSError:
                        continue
                    key = (str(entry), mtime)
                    if key in seen:
                        continue
                    seen.add(key)

                    # Wait briefly so ED finishes writing the file
                    time.sleep(0.5)

                    with lock:
                        snap_cmdr    = state.commander or ""
                        snap_system  = state.system or ""
                        snap_approach = state.approach_body or state.nearest_body or ""

                    # Create a minimal state-like object for naming
                    class _Snap:
                        commander   = snap_cmdr
                        system      = snap_system
                        approach_body = snap_approach
                        nearest_body  = snap_approach

                    _process_file(entry, dest_dir, _Snap())
        except Exception as exc:
            _log.debug(f"Screenshot scan error: {exc}")

        time.sleep(2)
