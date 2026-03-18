"""Elite Dangerous key bindings reader.

Discovers the bindings directory relative to the journal directory and parses
the PrimaryFire binding from the active custom bindings file.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def discover_bindings_dir(journal_dir: Path) -> Path | None:
    """Return the ED Options/Bindings directory, or None if not found.

    The journal directory is:
      .../steamuser/Saved Games/Frontier Developments/Elite Dangerous
    Walking up 3 levels yields:
      .../steamuser/
    The bindings dir is then:
      .../steamuser/AppData/Local/Frontier Developments/Elite Dangerous/Options/Bindings/
    """
    try:
        # Walk up: Elite Dangerous → Frontier Developments → Saved Games → steamuser
        steam_user = journal_dir.parent.parent.parent
        bindings = steam_user / "AppData" / "Local" / "Frontier Developments" / "Elite Dangerous" / "Options" / "Bindings"
        if bindings.is_dir():
            return bindings
    except Exception:
        pass
    return None


def read_primary_fire(journal_dir: Path) -> tuple[str, str] | None:
    """Parse the PrimaryFire binding from the active .binds file.

    Returns (device_guid, key_name) or None if not found/parseable.
    On Windows, joystick bindings are skipped — only Keyboard/Mouse are used.
    """
    bindings_dir = discover_bindings_dir(journal_dir)
    if bindings_dir is None:
        return None

    # Read the active preset name from StartPreset.4.start
    preset_name = "Custom"
    start_file = bindings_dir / "StartPreset.4.start"
    if start_file.exists():
        try:
            preset_name = start_file.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
        except OSError:
            pass

    # Try versioned binds files (.4.2.binds, .4.0.binds, plain .binds)
    candidates = [
        bindings_dir / f"{preset_name}.4.2.binds",
        bindings_dir / f"{preset_name}.4.0.binds",
        bindings_dir / f"{preset_name}.binds",
    ]
    binds_path = None
    for c in candidates:
        if c.exists():
            binds_path = c
            break

    if binds_path is None:
        return None

    try:
        tree = ET.parse(str(binds_path))
    except ET.ParseError:
        return None

    root = tree.getroot()
    pf = root.find(".//PrimaryFire")
    if pf is None:
        return None

    is_windows = sys.platform == "win32"

    # Try Primary first, then Secondary
    for tag in ("Primary", "Secondary"):
        el = pf.find(tag)
        if el is None:
            continue
        device = el.get("Device", "")
        key    = el.get("Key", "")
        if not device or not key or device == "{NoDevice}":
            continue
        # On Windows skip joystick devices — only Keyboard/Mouse work without vJoy
        if is_windows and device not in ("Keyboard", "Mouse"):
            continue
        return (device, key)

    return None
