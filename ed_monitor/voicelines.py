"""
NOVA Voicelines — random variant picker with per-language TOML support.

Load order:
  1. <package>/voicelines/{lang}.default.toml  — built-in default (replaced on each update)
  2. config/voicelines/{lang}.toml              — user customisation (optional)

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

import logging
import re
import random
import tomllib
from pathlib import Path
from typing import Optional

_log = logging.getLogger("nova.voicelines")

# Cache: lang → {event_key → [line, ...]}
_CACHE: dict[str, dict[str, list[str]]] = {}

# Cache: lang → {unit_key → localized_string}
_UNITS_CACHE: dict[str, dict[str, str]] = {}

# Default user config dir  (overridable for tests)
_CONFIG_DIR: Optional[Path] = None


def _config_dir() -> Path:
    if _CONFIG_DIR is not None:
        return _CONFIG_DIR
    from .config import config_dir
    return config_dir()


def _builtin_dir() -> Path:
    return Path(__file__).parent / "voicelines"


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


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

    _CACHE[lang] = lines
    return lines


def pick(key: str, lang: str = "en", **kwargs) -> Optional[str]:
    """Return a random formatted voiceline for *key* in *lang*, or None.

    Render pipeline (in order):
      1. _expand_includes — expands {include:_KeyName} / {_KeyName} fragments
      2. _evaluate_conditionals — replaces WHEN...THEN blocks
      3. format_map(_SafeDict) — fills {variable} references (missing keys → "")

    Fallback logic:
      - Key in lang map → use it; empty list → None.
      - Key absent from lang map and lang != "en" → try English built-in.
      - Key absent entirely → None.
    Fragment keys (starting with '_') are not directly speakable.
    """
    if key.startswith("_"):
        return None   # fragment keys are for includes only

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
        template = _expand_includes(template, lines_map, kwargs)
        template = _evaluate_conditionals(template, kwargs)
        return template.format_map(_SafeDict(kwargs))
    except Exception:
        return template


def is_muted(key: str, lang: str = "en") -> bool:
    """Return True if *key* has been explicitly silenced with ``replace = []``."""
    lines_map = _load(lang)
    return key in lines_map and lines_map[key] == []


def validate_user_file(lang: str) -> Optional[str]:
    """Validate the user voiceline file for *lang*.

    Returns None if the file doesn't exist or parses successfully.
    Returns a short user-friendly error message if the file has a syntax error.
    The message deliberately does not include TOML parser internals.
    """
    user_path = _config_dir() / "voicelines" / f"{lang}.toml"
    if not user_path.exists():
        return None
    try:
        with open(user_path, "rb") as f:
            tomllib.load(f)
        return None
    except Exception:
        return (
            f"User voiceline file '{lang}.toml' has a syntax error and will not be used. "
            "Please check and fix the file."
        )


def reload(lang: str) -> None:
    """Invalidate cache for *lang* so files are re-read on next pick()."""
    _CACHE.pop(lang, None)
    _UNITS_CACHE.pop(lang, None)


def reload_all() -> None:
    """Invalidate entire cache."""
    _CACHE.clear()
    _UNITS_CACHE.clear()


def _load_units(lang: str) -> dict[str, str]:
    """Load and cache unit strings for *lang* from built-in and user TOML.

    User [units] table overrides built-in defaults.
    """
    if lang in _UNITS_CACHE:
        return _UNITS_CACHE[lang]

    units: dict[str, str] = {}

    # 1. Built-in default
    builtin_path = _builtin_dir() / f"{lang}.default.toml"
    if builtin_path.exists():
        data = _read_toml(builtin_path)
        if isinstance(data.get("units"), dict):
            units.update(data["units"])

    # 2. User override
    user_path = _config_dir() / "voicelines" / f"{lang}.toml"
    if user_path.exists():
        data = _read_toml(user_path)
        if isinstance(data.get("units"), dict):
            units.update(data["units"])

    _UNITS_CACHE[lang] = units
    return units


def _slavic_plural(n: int) -> str:
    """Return plural form key for Slavic languages (Russian).

    one  → 1, 21, 31... (but not 11-14)
    few  → 2-4, 22-24, 32-34... (but not 11-14)
    many → 0, 5-20, 25-30, 100, etc.
    """
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "many"
    n %= 10
    if n == 1:
        return "one"
    if 2 <= n <= 4:
        return "few"
    return "many"


def unit_for(lang: str, key: str, count: int | None = None) -> str:
    """Return localized unit string for *key* in *lang*.

    For Slavic languages (ru) and count-sensitive keys, pass *count*
    to get the correct plural form (one/few/many).
    Falls back to English, then to the key itself.
    """
    units = _load_units(lang)

    # Slavic plural dispatch
    if count is not None and lang == "ru":
        plural_key = f"{key}_{_slavic_plural(count)}"
        if plural_key in units:
            return units[plural_key]

    if key in units:
        return units[key]

    # Fallback to English
    en_units = _load_units("en")
    if count is not None and lang == "ru":
        plural_key = f"{key}_{_slavic_plural(count)}"
        if plural_key in en_units:
            return en_units[plural_key]

    return en_units.get(key, key)


_SUPPORTED_LANGS = ("en", "de", "fr", "it", "es", "pt", "ru")


class _SafeDict(dict):
    """dict subclass that returns '' for missing keys instead of raising KeyError.
    Used in format_map() so unknown {variables} in user templates don't crash."""
    def __missing__(self, key: str) -> str:
        return ""


def _eval_clause(clause: str) -> bool:
    """Evaluate a single condition clause.

    Supported forms:
      value IS TRUE / IS FALSE / IS NOT TRUE / IS NOT FALSE
      left == right  |  left != right  |  left < right  |  left > right
      left <= right  |  left >= right
    Values are compared numerically when both sides parse as float,
    otherwise as stripped strings. '' and '0' are falsy for IS TRUE checks.
    """
    clause = clause.strip()

    # IS NOT TRUE / IS NOT FALSE
    m = re.match(r'^(.*?)\s*IS\s+NOT\s+(TRUE|FALSE)\s*$', clause, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        right = m.group(2).upper()
        is_truthy = bool(val) and val.upper() not in ("FALSE", "0")
        return (not is_truthy) if right == "TRUE" else is_truthy

    # IS TRUE / IS FALSE
    m = re.match(r'^(.*?)\s*IS\s+(TRUE|FALSE)\s*$', clause, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        right = m.group(2).upper()
        is_truthy = bool(val) and val.upper() not in ("FALSE", "0")
        return is_truthy if right == "TRUE" else not is_truthy

    # Comparison operators (==, !=, <=, >=, <, >)
    m = re.match(r'^(.*?)\s*(==|!=|<=|>=|<|>)\s*(.*)\s*$', clause)
    if m:
        left  = m.group(1).strip().strip('"')
        op    = m.group(2)
        right = m.group(3).strip().strip('"')
        try:
            lf, rf = float(left), float(right)
            return {
                "==": lf == rf, "!=": lf != rf,
                "<":  lf <  rf, ">":  lf >  rf,
                "<=": lf <= rf, ">=": lf >= rf,
            }[op]
        except ValueError:
            return {
                "==": left == right, "!=": left != right,
                "<":  left <  right, ">":  left >  right,
                "<=": left <= right, ">=": left >= right,
            }[op]

    # Bare value — truthy check
    return bool(clause) and clause.upper() not in ("FALSE", "0")


# Regex to find {varname} references in a condition string (word chars only)
_COND_VAR_RE = re.compile(r'\{(\w+)\}')


def _eval_condition(condition: str, kwargs: dict) -> bool:
    """Evaluate a full WHEN condition (may contain AND/OR) against kwargs.

    Variable references {varname} are substituted from kwargs before evaluation.
    OR has lower precedence than AND: each OR-group is ANDed together.
    """
    def _sub(m: re.Match) -> str:
        v = kwargs.get(m.group(1), "")
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        return str(v)

    cond = _COND_VAR_RE.sub(_sub, condition)

    # Split by OR (lower precedence) — any OR-group being true makes the whole true
    for or_part in re.split(r'\bOR\b', cond, flags=re.IGNORECASE):
        # Split by AND — all AND-clauses must be true
        if all(_eval_clause(c.strip()) for c in re.split(r'\bAND\b', or_part, flags=re.IGNORECASE)):
            return True
    return False


# Regex to match WHEN ... THEN "..." ; blocks.
# Group 1: condition text; Group 2: THEN text (supports \" escapes inside)
_WHEN_RE = re.compile(
    r'WHEN\s+(.+?)\s+THEN\s+"((?:[^"\\]|\\.)*)"\s*;?',
    re.DOTALL,
)


def _evaluate_conditionals(template: str, kwargs: dict) -> str:
    """Replace all WHEN...THEN "text"; blocks with their resolved text or ''.

    The THEN text is returned as-is (with {variable} references intact)
    so the final format_map() pass can fill them in.
    """
    def _replace(m: re.Match) -> str:
        condition = m.group(1)
        then_text = m.group(2).replace('\\"', '"')
        return then_text if _eval_condition(condition, kwargs) else ""

    return _WHEN_RE.sub(_replace, template)


# Matches both include syntaxes:
#   {include:KeyName}  — explicit; matches any key ([\w-]+); non-_ keys are rejected in handler
#   {_KeyName}         — shorthand; word characters only, must start with _ (\w+)
# Group 1: explicit key, Group 2: shorthand key
_INCLUDE_RE = re.compile(r'\{include:([\w-]+)\}|\{(_\w+)\}')

_INCLUDE_MAX_DEPTH = 5


def _expand_includes(template: str, lines_map: dict, kwargs: dict, depth: int = 0) -> str:
    """Expand include fragments in *template*.

    Supports two syntaxes:
      {include:_KeyName}  — explicit; key may contain hyphens
      {_KeyName}          — shorthand; word characters only

    Looks up each fragment key in *lines_map*, picks a random line, and
    substitutes it inline. Recursively expands nested includes.

    Cycle detection: depth > _INCLUDE_MAX_DEPTH → warning + expand to ''.
    Missing or non-_ keys → warning + expand to ''.
    """
    if depth > _INCLUDE_MAX_DEPTH:
        _log.warning("voicelines: include depth exceeded (circular include?)")
        return _INCLUDE_RE.sub("", template)

    def _replace(m: re.Match) -> str:
        key = m.group(1) or m.group(2)   # explicit group 1, shorthand group 2
        if not key.startswith("_"):
            _log.warning("voicelines: include key %r has no _ prefix — ignored", key)
            return ""
        variants = lines_map.get(key)
        if not variants:
            _log.warning("voicelines: include key %r not found", key)
            return ""
        fragment = random.choice(variants)
        return _expand_includes(fragment, lines_map, kwargs, depth + 1)

    return _INCLUDE_RE.sub(_replace, template)


def _copy_defaults_to_config() -> None:
    """Copy built-in default TOML files to config/voicelines/default/.

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
    """Create the user voicelines directory, README, and reference copy of built-in files."""
    dest_dir = _config_dir() / "voicelines"
    dest_dir.mkdir(parents=True, exist_ok=True)

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
        "Do **not** edit the files in `default/` directly; they are overwritten each launch.\n\n"
        "## Template Engine\n\n"
        "### Includes\n\n"
        "Define a reusable fragment (key must start with `_`) in your user file:\n\n"
        "    [_ship_status]\n"
        "    add = [\"{ship_name} — hull {hull}, fuel {fuel}.\"]\n\n"
        "Use `{include:_ship_status}` or shorthand `{_ship_status}` in any line.\n"
        "Hyphens in key names require the explicit form: `{include:_my-key}`.\n\n"
        "### Conditionals\n\n"
        "Inline `WHEN condition THEN \"text\";` blocks in any line:\n\n"
        "    [Scan_Notable]\n"
        "    add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN \"Worth {value}.\";']\n\n"
        "Condition true → 'text' included. False → replaced with ''.\n\n"
        "Supported: `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`\n"
    )
    try:
        readme.write_text(readme_text, encoding="utf-8")
    except OSError:
        pass
