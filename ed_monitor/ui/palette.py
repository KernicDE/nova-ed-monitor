# Elite Dangerous HUD colour palette
# ──────────────────────────────────────────────────────────────────────────────
# All UI colours must be defined here. No hardcoded rgb() values in panel/app
# code except for gameplay-specific mappings (star classes, pip colours, etc.).

# ── Core accent colours ───────────────────────────────────────────────────────
AMBER     = "rgb(210,115,0)"   # Data highlight — fuel state, cargo icons, non-mode UI
AMBER_DIM = "rgb(120,68,0)"    # Muted amber — footer labels, inactive accents

# ── HUD functional colours ────────────────────────────────────────────────────
HUD_GREEN = "rgb(0,170,60)"    # Positive / success / scoopable / bio present
HUD_WARN  = "rgb(195,150,0)"   # Warning / caution states
HUD_CRIT  = "rgb(185,40,40)"   # Critical / error / overheating (not combat mode)
HUD_CYAN  = "rgb(0,175,185)"   # Info / analysis data / on-foot gravity / position

# ── Data highlight colours ────────────────────────────────────────────────────
GOLD      = "rgb(230,185,0)"   # First discovery / mapping / notable value
BLUE_SH   = "rgb(50,130,210)"  # Shield / friend / clean legal
PURPLE    = "rgb(140,100,165)" # Geo signals / galaxy POIs
ANALYSIS  = "rgb(90,160,230)"  # Analysis mode data highlights

# ── Neutral greys ─────────────────────────────────────────────────────────────
WHITE        = "white"            # Primary text
LABEL        = "rgb(145,145,145)" # Secondary text / labels
LABEL_LIGHT  = "rgb(160,160,160)" # Muted primary text / inactive buttons
LABEL_DIM    = "rgb(100,100,100)" # Timestamps / footer hints / tertiary text
DIM          = "rgb(60,60,60)"    # Disabled / faint / no-data
BG_DARK      = "rgb(18,18,18)"    # App background
PANEL_BORDER = "rgb(90,90,90)"    # Default border for logs / secondary panels

# ── Semantic constants ────────────────────────────────────────────────────────
ROW_ALT     = "rgb(38,38,38)"    # Alternating table row background
HIGH_G_CRIT = "rgb(220,60,0)"    # ≥3.0 G gravity warnings
HIGH_G_WARN = "rgb(220,140,0)"   # ≥1.5 G gravity warnings
BIO_DSS     = "rgb(0,220,80)"    # Bio "needs DSS" highlight
HIGH_G_FLASH = "rgb(220,100,0)"  # High-G warning flash border

# ── Mode palette system ───────────────────────────────────────────────────────
# Each mode has: border (panels), h1 (section headers), h2 (table column headers),
# h3 (kv labels / inline dividers), bg (section header background tint).
#
# Usage: _mp = P.mp(snap.ui_mode)
#        _section_header("TITLE", _mp["h1"], _mp["bg"])
#        _data_table(_mp["h2"])
#        _kv_row("label", value, h3=_mp["h3"])
#
# ui_mode values: "ship" | "combat" | "on_foot" | "srv" | "offline"
# "analysis" maps to "ship" (same orange — analysis is still in ship).

_MODES: dict[str, dict[str, str]] = {
    "ship": dict(
        border = "rgb(255,128,0)",
        h1     = "rgb(255,128,0)",
        h2     = "rgb(200,95,0)",
        h3     = "rgb(140,65,0)",
        bg     = "rgb(50,22,0)",
    ),
    "combat": dict(
        border = "rgb(200,55,35)",
        h1     = "rgb(200,55,35)",
        h2     = "rgb(155,40,25)",
        h3     = "rgb(105,28,18)",
        bg     = "rgb(45,12,8)",
    ),
    "on_foot": dict(
        border = "rgb(80,160,235)",
        h1     = "rgb(80,160,235)",
        h2     = "rgb(55,120,195)",
        h3     = "rgb(38,85,145)",
        bg     = "rgb(10,28,58)",
    ),
    "srv": dict(
        border = "rgb(45,115,185)",
        h1     = "rgb(45,115,185)",
        h2     = "rgb(34,88,148)",
        h3     = "rgb(24,62,108)",
        bg     = "rgb(8,20,46)",
    ),
    "offline": dict(
        border = "rgb(70,70,70)",
        h1     = "rgb(90,90,90)",
        h2     = "rgb(70,70,70)",
        h3     = "rgb(55,55,55)",
        bg     = "rgb(22,22,22)",
    ),
}

# "analysis" is identical to "ship" — same orange, just scanner out
_MODES["analysis"] = _MODES["ship"]


def mp(mode: str) -> dict[str, str]:
    """Return the mode palette dict for the given ui_mode string."""
    return _MODES.get(mode, _MODES["ship"])


# ── Legacy aliases (kept for any remaining direct references) ─────────────────
HEADER      = _MODES["ship"]["h1"]   # section titles — use mp()["h1"] in new code
HEADER_BG   = _MODES["ship"]["bg"]   # section title bg — use mp()["bg"] in new code
