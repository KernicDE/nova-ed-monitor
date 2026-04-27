# Elite Dangerous HUD colour palette
# ──────────────────────────────────────────────────────────────────────────────
# All UI colours must be defined here. No hardcoded rgb() values in panel/app
# code except for gameplay-specific mappings (star classes, pip colours, etc.).

# ── Core accent colours ───────────────────────────────────────────────────────
AMBER     = "rgb(210,115,0)"   # Primary accent — ship status, target, actions
AMBER_DIM = "rgb(120,68,0)"    # Muted amber — footer labels, inactive accents

# ── HUD functional colours ────────────────────────────────────────────────────
HUD_GREEN = "rgb(0,170,60)"    # Positive / success / scoopable / bio present
HUD_WARN  = "rgb(195,150,0)"   # Warning / caution states
HUD_CRIT  = "rgb(185,40,40)"   # Critical / combat / error / overheating
HUD_CYAN  = "rgb(0,175,185)"   # Info / analysis / on-foot gravity / position

# ── Data highlight colours ────────────────────────────────────────────────────
GOLD      = "rgb(230,185,0)"   # First discovery / mapping / notable value
BLUE_SH   = "rgb(50,130,210)"  # Shield / friend / clean legal
PURPLE    = "rgb(140,100,165)" # On-foot mode borders / geo signals / galaxy POIs
ANALYSIS  = "rgb(90,160,230)"  # Analysis mode data highlights

# ── Neutral greys ─────────────────────────────────────────────────────────────
WHITE       = "white"            # Primary text
LABEL       = "rgb(145,145,145)" # Secondary text / labels
LABEL_LIGHT = "rgb(160,160,160)" # Muted primary text / inactive buttons
LABEL_DIM   = "rgb(100,100,100)" # Timestamps / footer hints / tertiary text
DIM         = "rgb(60,60,60)"    # Disabled / faint / no-data
BG_DARK     = "rgb(18,18,18)"    # App background

# ── Semantic constants (derived from core palette) ────────────────────────────
# Use these for specific UI elements to keep styling consistent across panels.
HEADER      = "rgb(195,160,55)"  # Table headers, section titles, modal borders
HEADER_BG   = "rgb(45,35,10)"    # Background behind section headers
ROW_ALT     = "rgb(38,38,38)"    # Alternating table row background
HIGH_G_CRIT = "rgb(220,60,0)"    # ≥3.0 G gravity warnings
HIGH_G_WARN = "rgb(220,140,0)"   # ≥1.5 G gravity warnings
BIO_DSS     = "rgb(0,220,80)"    # Bio "needs DSS" highlight

# ── Mode border colours ───────────────────────────────────────────────────────
# These are used in app.py for the global mode CSS overrides.
# They should remain visually distinct from each other and from panel borders.
COMBAT_BORDER  = HUD_CRIT         # Combat mode
ON_FOOT_BORDER = PURPLE           # On-foot / EVA mode
ANALYSIS_BORDER = "rgb(120,190,120)"  # Analysis mode (soft sage green)
OFFLINE_BORDER = "rgb(70,70,70)"  # Offline / game not running
OFFLINE_TITLE  = "rgb(90,90,90)"  # Offline border title
HIGH_G_FLASH   = "rgb(220,100,0)" # High-G warning flash border
