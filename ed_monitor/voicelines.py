"""
NOVA Voicelines — random variant picker with per-language TOML support.

Load order:
  1. <package>/voicelines/{lang}.default.toml  — built-in default (replaced on each update)
  2. ~/.config/nova/voicelines/{lang}.toml      — user customisation (optional)

User file format (different from the default file):
  [EventKey]
  add     = ["Extra variant 1.", "Extra variant 2."]
  # OR
  replace = ["Only this.", "Or this."]

  add     — appends lines to the built-in pool (more random variety)
  replace — uses only user lines for this event (overrides the default)
  replace = []  — silences the event entirely

Rules:
  - If a key is absent from both, English is tried as a last resort (non-EN only).

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

    Built-in default is loaded first; user file is applied on top using
    add/replace semantics.
    """
    if lang in _CACHE:
        return _CACHE[lang]

    lines: dict[str, list[str]] = {}

    # 1. Load built-in default ({lang}.default.toml)
    builtin_path = _builtin_dir() / f"{lang}.default.toml"
    if builtin_path.exists():
        for key, val in _read_toml(builtin_path).items():
            if isinstance(val, dict):
                raw = val.get("lines", [])
                if isinstance(raw, list):
                    lines[key] = [str(s) for s in raw if s]

    # 2. Apply user file ({lang}.toml) with add/replace semantics
    user_path = _config_dir() / "voicelines" / f"{lang}.toml"
    if user_path.exists():
        _migrate_user_voiceline_file(user_path)
        for key, val in _read_toml(user_path).items():
            if not isinstance(val, dict):
                continue
            if "replace" in val:
                # replace: use only user lines (empty list = silence)
                raw = val["replace"]
                if isinstance(raw, list):
                    lines[key] = [str(s) for s in raw if s]
            elif "add" in val:
                # add: append user lines to the default pool
                raw = val["add"]
                if isinstance(raw, list):
                    extra = [str(s) for s in raw if s]
                    lines[key] = lines.get(key, []) + extra
            elif "lines" in val:
                # Legacy format: treat as replace for backwards compat
                raw = val["lines"]
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


def _migrate_old_user_voicelines() -> None:
    """One-time migration: back up old-style user voiceline files.

    Before v1.22.4 the user override files used ``lines = [...]`` syntax and had
    the same name as the built-in files (e.g. ``en.toml``).  The built-in files
    are now named ``en.default.toml``; user files keep the ``en.toml`` name but
    use ``add``/``replace`` syntax.

    If old-format ``*.toml`` files are found and no migration sentinel exists,
    they are moved to a ``backup/`` subdirectory so the user doesn't lose them.
    A sentinel file ``.migrated_v2`` is written afterwards to prevent re-running.
    """
    dest_dir = _config_dir() / "voicelines"
    sentinel = dest_dir / ".migrated_v2"
    if sentinel.exists() or not dest_dir.is_dir():
        return

    old_files = [
        p for p in dest_dir.glob("*.toml")
        if not p.name.endswith(".default.toml")
    ]
    if old_files:
        backup_dir = dest_dir / "backup"
        try:
            backup_dir.mkdir(exist_ok=True)
            for f in old_files:
                f.rename(backup_dir / f.name)
        except OSError:
            pass

    try:
        sentinel.touch()
    except OSError:
        pass


def _copy_defaults_to_config() -> None:
    """Copy built-in default TOML files to ~/.config/nova/voicelines/default/.

    Always overwrites so users always have a current reference copy.
    """
    import shutil
    builtin = _builtin_dir()
    dest = _config_dir() / "voicelines" / "default"
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for src in builtin.glob("*.default.toml"):
        try:
            shutil.copy2(src, dest / src.name)
        except OSError:
            pass


def ensure_user_files() -> None:
    """Create the user voicelines directory and a README explaining the override system.

    Also performs a one-time migration of old-style user voiceline files and
    copies the built-in default files to a reference directory.
    """
    dest_dir = _config_dir() / "voicelines"
    dest_dir.mkdir(parents=True, exist_ok=True)

    _migrate_old_user_voicelines()
    _copy_defaults_to_config()

    readme = dest_dir / "README.md"
    readme_text = (
        "# NOVA Voicelines — User Customisation\n\n"
        "Place files named `en.toml`, `de.toml`, etc. here to customise\n"
        "built-in voicelines.  Only the events you define are affected;\n"
        "everything else uses the built-in defaults.\n\n"
        "## Format\n\n"
        "    [EventKey]\n"
        "    add = [\n"
        "        \"Extra variant one.\",\n"
        "        \"Extra variant two.\",\n"
        "    ]\n\n"
        "    [AnotherEvent]\n"
        "    replace = [\n"
        "        \"Only this line is used now.\",\n"
        "    ]\n\n"
        "## Rules\n\n"
        "- `add`     — appends your lines to the built-in pool (more random variety).\n"
        "- `replace` — replaces the built-in lines entirely for this event.\n"
        "- `replace = []` — silences the event completely.\n"
        "- Keys absent from your file use the built-in default.\n\n"
        "## Finding built-in defaults\n\n"
        "The current default files are copied to the `default/` subfolder here\n"
        "on every NOVA launch — use them as a reference for available keys and formats.\n"
        "Do **not** edit the files in `default/` directly; they are overwritten each launch.\n"
    )
    try:
        readme.write_text(readme_text, encoding="utf-8")
    except OSError:
        pass
