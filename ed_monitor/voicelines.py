"""
NOVA Voicelines — random variant picker with per-language TOML support.

Load order (built-in first, user overlays on top):
  1. <package>/voicelines/{lang}.toml  (built-in standard — single line per event)
  2. ~/.config/nova/voicelines/{lang}.toml  (user overrides — any number of lines)

Rules:
  - If a key is present in the user file, NOVA uses those lines (no fallback).
    Set lines = [] to silence an event entirely.
  - If a key is absent from the user file, the built-in default is used.
  - If a key is absent from both, English is tried as a last resort (non-EN only).

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

import re
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


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _migrate_user_voiceline_file(path: Path) -> None:
    """Patch out removed template variables from user override files in-place.

    Handles:
    - BioReady: removes the "{dist}" distance clause (removed in v1.15.5)
    - Touchdown: removes the entire [Touchdown] section if it still has {lat}/{lon}
      so the built-in default (no coordinates) takes over
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return

    if "{dist}" not in text and "{lat}" not in text and "{lon}" not in text:
        return

    new_text = text

    # BioReady: strip the sentence-fragment containing {dist}.
    # e.g. ". Distance {dist} metres." → "." in any language.
    # Pattern: non-period chars surrounding {dist} up to the next period.
    new_text = re.sub(r'[^.]*\{dist\}[^.]*\.', '.', new_text)
    # Clean up double-period artefacts like ".." → "."
    new_text = re.sub(r'\.(\s*)\.', r'.\1', new_text)

    # Touchdown: the coordinate portion is tightly coupled to the rest of the
    # sentence (prepositions vary per language), so we remove the whole section
    # and let the built-in default ("Touchdown." / "Gelandet." etc.) take over.
    # Use lookahead for next section header (line starting with [) or end of string.
    if re.search(r'\[Touchdown\].*?\{(?:lat|lon)\}', new_text, re.DOTALL):
        new_text = re.sub(
            r'\[Touchdown\].*?(?=\n\[|\Z)', '', new_text, flags=re.DOTALL,
        )

    if new_text != text:
        try:
            path.write_text(new_text, encoding="utf-8")
        except OSError:
            pass


def _load(lang: str) -> dict[str, list[str]]:
    """Load and cache voicelines for a language. Returns mapping key→[lines].

    Built-in is loaded first; user file overlays on top.  A key present in the
    user file (even with an empty list) is never overridden by the built-in.
    """
    if lang in _CACHE:
        return _CACHE[lang]

    lines: dict[str, list[str]] = {}

    # 1. Load built-in (standard, single line per event)
    builtin_path = _builtin_dir() / f"{lang}.toml"
    if builtin_path.exists():
        for key, val in _read_toml(builtin_path).items():
            if isinstance(val, dict):
                raw = val.get("lines", [])
                if isinstance(raw, list):
                    lines[key] = [str(s) for s in raw if s]

    # 2. Overlay user file — user keys win, including empty lists (= silence)
    user_path = _config_dir() / "voicelines" / f"{lang}.toml"
    if user_path.exists():
        _migrate_user_voiceline_file(user_path)
        for key, val in _read_toml(user_path).items():
            if isinstance(val, dict) and "lines" in val:
                raw = val.get("lines", [])
                if isinstance(raw, list):
                    lines[key] = [str(s) for s in raw if s]

    _CACHE[lang] = lines
    return lines


def pick(key: str, lang: str = "en", **kwargs) -> Optional[str]:
    """Return a random formatted voiceline for *key* in *lang*, or None.

    Fallback logic:
      - Key in lang map (built-in or user-overridden) → use it; empty list = None.
      - Key absent from lang map and lang != "en" → try English built-in.
      - Key absent entirely → None.
    """
    lines_map = _load(lang)

    if key in lines_map:
        variants = lines_map[key]
    elif lang != "en":
        variants = _load("en").get(key)
    else:
        variants = None

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
    """Create the user voicelines directory and a README explaining the override system.

    No built-in files are copied — the built-in TOML files are the standard
    defaults and are always loaded automatically.  Users only need to create
    their own {lang}.toml here for the events they want to customise.
    """
    dest_dir = _config_dir() / "voicelines"
    dest_dir.mkdir(parents=True, exist_ok=True)
    readme = dest_dir / "README.md"
    if not readme.exists():
        try:
            readme.write_text(
                "# NOVA Voicelines — User Overrides\n\n"
                "Place files named `en.toml`, `de.toml`, etc. in this directory\n"
                "to override any built-in voicelines.  Only the events you define\n"
                "here are affected; everything else uses the built-in defaults.\n\n"
                "## Format\n\n"
                "    [EventKey]\n"
                "    lines = [\n"
                "        \"Variant one.\",\n"
                "        \"Variant two.\",\n"
                "    ]\n\n"
                "## Rules\n\n"
                "- Key present in your file → NOVA uses your lines (any number of variants).\n"
                "- Key absent from your file → built-in default is used.\n"
                "- `lines = []` → event is silenced entirely (no fallback).\n\n"
                "## Finding the built-in files\n\n"
                "    python -c \"import ed_monitor.voicelines as v; print(v._builtin_dir())\"\n",
                encoding="utf-8",
            )
        except OSError:
            pass
