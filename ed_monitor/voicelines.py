"""
NOVA Voicelines — random variant picker with per-language TOML support.

Voiceline files are copied to ~/.config/nova/voicelines/ on first launch so
users can find and edit them directly. Files are only copied if they don't
already exist, so user edits are never overwritten on update.

Load order:
  1. ~/.config/nova/voicelines/{lang}.toml  (user copy — takes priority)
  2. <package>/voicelines/{lang}.toml       (built-in fallback for missing keys)

TOML format:
  [EventKey]
  lines = [
      "Variant one with {variable}.",
      "Variant two.",
  ]

Call pick(key, lang="en", **kwargs) to get a formatted random line.
Returns None if the key is not found so callers can fall back gracefully.
"""
from __future__ import annotations

import random
import tomllib
from pathlib import Path
from typing import Optional

# Cache: lang → {event_key → [line, ...]}
_CACHE: dict[str, dict[str, list[str]]] = {}

# Default user config dir  (overridable for tests)
_CONFIG_DIR: Optional[Path] = None


def _config_dir() -> Path:
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    import os
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"


def _builtin_dir() -> Path:
    return Path(__file__).parent / "voicelines"


def _load(lang: str) -> dict[str, list[str]]:
    """Load and cache voicelines for a language. Returns mapping key→[lines]."""
    if lang in _CACHE:
        return _CACHE[lang]

    lines: dict[str, list[str]] = {}

    # Try user file first (overrides built-in)
    user_path    = _config_dir() / "voicelines" / f"{lang}.toml"
    builtin_path = _builtin_dir() / f"{lang}.toml"

    for path in (user_path, builtin_path):
        if path.exists():
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                for key, val in data.items():
                    if isinstance(val, dict):
                        raw = val.get("lines", [])
                        if isinstance(raw, list):
                            lines[key] = [str(s) for s in raw if s]
            except Exception:
                pass
            break  # stop at first found file

    # If built-in exists but user file was found (and possibly broken), also load built-in
    # as a fallback for keys the user hasn't overridden
    if user_path.exists() and builtin_path.exists():
        try:
            with open(builtin_path, "rb") as f:
                data = tomllib.load(f)
            for key, val in data.items():
                if key not in lines and isinstance(val, dict):
                    raw = val.get("lines", [])
                    if isinstance(raw, list):
                        lines[key] = [str(s) for s in raw if s]
        except Exception:
            pass

    _CACHE[lang] = lines
    return lines


def pick(key: str, lang: str = "en", **kwargs) -> Optional[str]:
    """Return a random formatted voiceline for *key* in *lang*, or None."""
    lines_map = _load(lang)
    variants  = lines_map.get(key)

    # Fall back to English if key missing in target language
    if not variants and lang != "en":
        lines_map = _load("en")
        variants  = lines_map.get(key)

    if not variants:
        return None

    template = random.choice(variants)
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        # Return unformatted template rather than crashing
        return template


def reload(lang: str) -> None:
    """Invalidate cache for *lang* so files are re-read on next pick()."""
    _CACHE.pop(lang, None)


def reload_all() -> None:
    """Invalidate entire cache."""
    _CACHE.clear()


_SUPPORTED_LANGS = ("en", "de", "fr", "it", "es", "pt", "ru")


def ensure_user_files() -> None:
    """Copy built-in voiceline files to the user config dir if not already present.

    Called once at startup so users can find and edit the files at
    ~/.config/nova/voicelines/ without digging into the installed package.
    Existing files are never overwritten.
    """
    dest_dir = _config_dir() / "voicelines"
    dest_dir.mkdir(parents=True, exist_ok=True)
    builtin = _builtin_dir()
    for lang in _SUPPORTED_LANGS:
        dest = dest_dir / f"{lang}.toml"
        if not dest.exists():
            src = builtin / f"{lang}.toml"
            if src.exists():
                try:
                    dest.write_bytes(src.read_bytes())
                except OSError:
                    pass
