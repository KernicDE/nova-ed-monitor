# NOVA colour palette — dynamically themable
# ──────────────────────────────────────────────────────────────────────────────
# All UI colours must be defined here. No hardcoded rgb() values in panel/app
# code except for gameplay-specific mappings (star classes, pip colours, etc.).
#
# Themes live in config/themes/<name>.toml (TOML format).  The active theme is
# read from config.toml (key: theme) and applied by calling apply_theme()
# BEFORE any UI modules are imported.

from __future__ import annotations

import logging
import re
from pathlib import Path

_log = logging.getLogger("nova.palette")

# ── CSS helper ────────────────────────────────────────────────────────────────
_CSS_RE = re.compile(r"\[\[(\w+(?:\.\w+)*)\]\]")


def css(template: str) -> str:
    """Replace [[CONSTANT]] or [[DICT.key]] placeholders with current palette values."""
    def _repl(m: re.Match) -> str:
        parts = m.group(1).split(".")
        obj = globals().get(parts[0], None)
        for part in parts[1:]:
            if isinstance(obj, dict):
                obj = obj.get(part, None)
            else:
                return m.group(0)
        return obj if obj is not None else m.group(0)
    return _CSS_RE.sub(_repl, template)


# ── Default palette values ────────────────────────────────────────────────────
# These are overwritten by apply_theme() when a theme file is present.

# Core accent colours
AMBER     = "rgb(210,115,0)"
AMBER_DIM = "rgb(120,68,0)"

# HUD functional colours
HUD_GREEN = "rgb(0,170,60)"
HUD_WARN  = "rgb(195,150,0)"
HUD_CRIT  = "rgb(185,40,40)"
HUD_CYAN  = "rgb(0,175,185)"

# Data highlight colours
GOLD      = "rgb(230,185,0)"
BLUE_SH   = "rgb(50,130,210)"
PURPLE    = "rgb(140,100,165)"
ANALYSIS  = "rgb(90,160,230)"

# Neutral greys
WHITE        = "white"
LABEL        = "rgb(145,145,145)"
LABEL_LIGHT  = "rgb(160,160,160)"
LABEL_DIM    = "rgb(100,100,100)"
DIM          = "rgb(60,60,60)"
BG_DARK      = "rgb(18,18,18)"
PANEL_BORDER = "rgb(90,90,90)"

# Semantic constants
ROW_ALT      = "rgb(38,38,38)"
HIGH_G_CRIT  = "rgb(220,60,0)"
HIGH_G_WARN  = "rgb(220,140,0)"
BIO_DSS      = "rgb(0,220,80)"
HIGH_G_FLASH = "rgb(220,100,0)"

# Overlay / settings chrome
OVERLAY_BG         = "rgba(10,10,10,0.93)"
OVERLAY_BOX_BG     = "rgb(28,28,28)"
OVERLAY_BOX_BORDER = "rgb(195,160,55)"
SETTINGS_ROW_FOCUS_BG = "rgb(45,45,45)"
ALERT_FLASH_BG     = "rgb(80,0,0)"
HIGH_G_FLASH_BG    = "rgb(50,20,0)"

# Pip colours (gameplay, but exposed for theming)
PIP_SYS = "rgb(60,100,200)"
PIP_ENG = "rgb(160,200,60)"
PIP_WEP = "rgb(200,60,60)"

# Misc UI colours
COLD_WARN          = "rgb(120,180,255)"
CHAT_TWITCH        = "rgb(145,70,255)"
CHAT_YOUTUBE       = "rgb(255,70,70)"
CHAT_SQUAD         = "rgb(0,200,100)"
FLAGS_GOOD         = "rgb(130,200,130)"
POPULATED_NAME     = "rgb(255,235,180)"
BIO_SAMPLE_1       = "rgb(210,210,0)"
FIRST_FOOTFALL     = "rgb(80,240,160)"
FIRST_FOOTFALL_VALUE = "rgb(0,255,180)"
OVERVIEW_BIO       = "rgb(140,130,60)"
PP_MERITS          = "rgb(180,130,255)"
GALAXY_MARKER      = "rgb(0,200,80)"
NAV_LIGHT_PORT     = "rgb(255,60,60)"
NAV_LIGHT_STARBOARD = "rgb(0,255,100)"

# ── Mode palette system ───────────────────────────────────────────────────────

_MODES: dict[str, dict[str, str]] = {
    "ship": dict(
        border="rgb(255,128,0)",
        h1="rgb(255,128,0)",
        h2="rgb(200,95,0)",
        h3="rgb(140,65,0)",
        bg="rgb(50,22,0)",
    ),
    "combat": dict(
        border="rgb(200,55,35)",
        h1="rgb(200,55,35)",
        h2="rgb(155,40,25)",
        h3="rgb(105,28,18)",
        bg="rgb(45,12,8)",
    ),
    "on_foot": dict(
        border="rgb(80,160,235)",
        h1="rgb(80,160,235)",
        h2="rgb(55,120,195)",
        h3="rgb(38,85,145)",
        bg="rgb(10,28,58)",
    ),
    "srv": dict(
        border="rgb(45,115,185)",
        h1="rgb(45,115,185)",
        h2="rgb(34,88,148)",
        h3="rgb(24,62,108)",
        bg="rgb(8,20,46)",
    ),
    "offline": dict(
        border="rgb(70,70,70)",
        h1="rgb(90,90,90)",
        h2="rgb(70,70,70)",
        h3="rgb(55,55,55)",
        bg="rgb(22,22,22)",
    ),
}
_MODES["analysis"] = _MODES["ship"]


def mp(mode: str) -> dict[str, str]:
    """Return the mode palette dict for the given ui_mode string."""
    return _MODES.get(mode, _MODES["ship"])


# Legacy aliases (kept for any remaining direct references)
HEADER      = _MODES["ship"]["h1"]
HEADER_BG   = _MODES["ship"]["bg"]


# ── Theme loading ─────────────────────────────────────────────────────────────

def _theme_dir() -> Path:
    """Return the directory where user theme files live."""
    try:
        from ..config import config_dir
        return config_dir() / "themes"
    except Exception:
        return Path(".")


def _builtin_theme_dir() -> Path:
    """Return the directory containing built-in theme files."""
    try:
        return Path(__file__).parent.parent / "themes"
    except Exception:
        return Path(".")


def _load_toml(path: Path) -> dict:
    try:
        import tomllib as _tomllib
    except ImportError:  # pragma: no cover
        import tomli as _tomllib  # type: ignore[no-redef]
    try:
        with open(path, "rb") as f:
            return _tomllib.load(f)
    except Exception:
        return {}


def _color_key_to_constant(key: str) -> str:
    """Map a TOML colour key to the Python constant name."""
    return key.upper()


def apply_theme(theme_name: str = "default") -> None:
    """Read the named theme TOML and override module-level palette variables.

    Must be called **before** any UI module that imports ``palette as P`` is
    loaded, because Textual CSS strings are evaluated at class-definition time.
    """
    theme_path = _theme_dir() / f"{theme_name}.toml"
    if not theme_path.exists():
        theme_path = _builtin_theme_dir() / f"{theme_name}.toml"

    data = _load_toml(theme_path) if theme_path.exists() else {}
    colors = data.get("colors", {})
    modes = data.get("modes", {})

    g = globals()

    # Override simple colour constants
    for key, val in colors.items():
        const = _color_key_to_constant(key)
        if const in g:
            g[const] = val
        else:
            # Allow arbitrary new colour keys for advanced theming
            g[const] = val

    # Override mode palettes
    for mode_name, mode_vals in modes.items():
        if mode_name in _MODES:
            for k, v in mode_vals.items():
                _MODES[mode_name][k] = v

    # Analysis mirrors ship
    _MODES["analysis"] = _MODES["ship"]

    # Update legacy aliases
    g["HEADER"] = _MODES["ship"]["h1"]
    g["HEADER_BG"] = _MODES["ship"]["bg"]

    if data:
        _log.info("Applied theme: %s", theme_name)


def ensure_theme_files() -> None:
    """Copy built-in theme files to the user's config/themes/ directory.

    Called once at startup so users always have the built-in defaults as
    reference and can duplicate them to create custom themes.
    """
    import shutil
    builtin = _builtin_theme_dir()
    dest = _theme_dir()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for src in builtin.glob("*.toml"):
        try:
            shutil.copy2(src, dest / src.name)
        except OSError:
            pass
    readme_src = builtin / "README.md"
    if readme_src.exists():
        try:
            shutil.copy2(readme_src, dest / "README.md")
        except OSError:
            pass
