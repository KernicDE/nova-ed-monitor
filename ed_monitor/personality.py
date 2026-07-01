"""
NOVA Personality — user-editable persona shaping AI-generated voice lines.

Load order (mirrors voicelines.py):
  1. <package>/personality/{name}.default.toml — built-in default
  2. config/personality/{name}.toml             — user customisation (optional)

The user file simply overrides individual top-level keys (name, tone, traits,
speech_style, style_notes) — no add/replace list semantics like voicelines,
since this isn't a pool of random variants.

Call get_prompt_fragment(name) to get a compact natural-language persona
block for splicing into AI voice-generation prompts.
"""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Optional

_log = logging.getLogger("nova.personality")

# Cache: name → merged persona dict
_CACHE: dict[str, dict] = {}

# Default user config dir (overridable for tests)
_CONFIG_DIR: Optional[Path] = None


def _config_dir() -> Path:
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    from .config import config_dir
    return config_dir()


def _builtin_dir() -> Path:
    return Path(__file__).parent / "personality"


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _load(name: str) -> dict:
    """Load and cache the persona for *name*. Built-in first, user override on top."""
    if name in _CACHE:
        return _CACHE[name]

    persona: dict = {}

    builtin_path = _builtin_dir() / f"{name}.default.toml"
    if builtin_path.exists():
        persona.update(_read_toml(builtin_path))
    elif name != "default":
        # Unknown custom name with no built-in — fall back to the shipped default
        fallback_path = _builtin_dir() / "default.default.toml"
        persona.update(_read_toml(fallback_path))

    user_path = _config_dir() / "personality" / f"{name}.toml"
    if user_path.exists():
        persona.update(_read_toml(user_path))

    _CACHE[name] = persona
    return persona


def get_prompt_fragment(name: str = "default") -> str:
    """Render the persona into a short natural-language block for AI prompts."""
    persona = _load(name)
    if not persona:
        return ""

    lines = [f"You are {persona.get('name', 'NOVA')}, a starship AI assistant."]
    tone = persona.get("tone")
    if tone:
        lines.append(f"Tone: {str(tone).strip()}")
    traits = persona.get("traits")
    if isinstance(traits, list) and traits:
        lines.append("Traits: " + "; ".join(str(t).strip() for t in traits) + ".")
    speech_style = persona.get("speech_style")
    if speech_style:
        lines.append(f"Speech style: {str(speech_style).strip()}")
    style_notes = persona.get("style_notes")
    if style_notes:
        lines.append(f"Notes: {str(style_notes).strip()}")
    return "\n".join(lines)


def validate_user_file(name: str) -> Optional[str]:
    """Validate the user personality file for *name*.

    Returns None if the file doesn't exist or parses successfully, else a
    short user-friendly error message.
    """
    user_path = _config_dir() / "personality" / f"{name}.toml"
    if not user_path.exists():
        return None
    try:
        with open(user_path, "rb") as f:
            tomllib.load(f)
        return None
    except Exception:
        return (
            f"User personality file '{name}.toml' has a syntax error and will not be used. "
            "Please check and fix the file."
        )


def reload(name: str) -> None:
    """Invalidate cache for *name* so files are re-read on next get_prompt_fragment()."""
    _CACHE.pop(name, None)


def reload_all() -> None:
    """Invalidate entire cache."""
    _CACHE.clear()


def _copy_defaults_to_config() -> None:
    """Copy built-in default TOML files to config/personality/default/.

    Always overwrites so users always have a current reference copy.
    """
    import shutil
    builtin = _builtin_dir()
    dest = _config_dir() / "personality" / "default"
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
    """Create the user personality directory, README, and reference copy of built-ins."""
    dest_dir = _config_dir() / "personality"
    dest_dir.mkdir(parents=True, exist_ok=True)

    _copy_defaults_to_config()

    readme = dest_dir / "README.md"
    readme_text = (
        "# NOVA Personality — User Customisation\n\n"
        "Create a file named `default.toml` here (or `<name>.toml` and set\n"
        "`personality_name = <name>` in config.toml) to customise how NOVA's\n"
        "AI-generated voice lines sound. Only used when `voice_engine` is set\n"
        "to `kimi` or `claude` — the static voiceline system ignores this file.\n\n"
        "## Fields\n\n"
        "    name         = \"NOVA\"\n"
        "    tone         = \"Short free-text description of overall tone.\"\n"
        "    traits       = [\"trait one\", \"trait two\"]\n"
        "    speech_style = \"How lines should be phrased for TTS.\"\n"
        "    style_notes  = \"Any additional guidance for the AI generator.\"\n\n"
        "Fields absent from your file fall back to the built-in default.\n\n"
        "## Finding the built-in default\n\n"
        "The current default file is copied to the `default/` subfolder here\n"
        "on every NOVA launch — use it as a reference.\n"
        "Do **not** edit files in `default/` directly; they are overwritten each launch.\n"
    )
    try:
        readme.write_text(readme_text, encoding="utf-8")
    except OSError:
        pass
