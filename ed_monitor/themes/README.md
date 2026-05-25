# NOVA Themes

NOVA supports custom colour themes via TOML files placed in this folder.

## Quick Start

1. Duplicate `default.toml` and rename it (e.g. `my_theme.toml`).
2. Edit the colour values inside.
3. Set `theme = my_theme` in `config.toml` (or pick it in the in-app Settings overlay).
4. Restart NOVA — themes are applied at startup.

## Built-in Themes

| Theme | Description |
|-------|-------------|
| `default` | Classic Elite Dangerous orange-cyan HUD palette. |
| `sakura` | Soft pink and violet tones on a deep night background. |

## Theme File Format

Every theme is a TOML file with three sections:

```toml
# Optional metadata
description = "My custom dark theme"
author = "Your Name"

[colors]
# Define any colour constant here.  The key name becomes the UPPER_CASE constant
# used in NOVA's palette module (e.g. "amber" → P.AMBER).
amber     = "rgb(210,115,0)"
hud_green = "rgb(0,170,60)"
bg_dark   = "rgb(18,18,18)"
white     = "white"

[modes.ship]
border = "rgb(255,128,0)"
h1     = "rgb(255,128,0)"
h2     = "rgb(200,95,0)"
h3     = "rgb(140,65,0)"
bg     = "rgb(50,22,0)"

[modes.combat]
border = "rgb(200,55,35)"
h1     = "rgb(200,55,35)"
h2     = "rgb(155,40,25)"
h3     = "rgb(105,28,18)"
bg     = "rgb(45,12,8)"
```

### `[colors]` — Core Palette

These keys control every UI element that is not a mode border.  Keys you will want to change first:

| Key | Default | Used for |
|-----|---------|----------|
| `amber` | `rgb(210,115,0)` | Ship panel, route panel, fuel, cargo accents |
| `hud_cyan` | `rgb(0,175,185)` | System panel, bodies panel, info text |
| `hud_green` | `rgb(0,170,60)` | Positive states, scoopable stars, bio present |
| `hud_warn` | `rgb(195,150,0)` | Warning states |
| `hud_crit` | `rgb(185,40,40)` | Critical / error / overheating |
| `gold` | `rgb(230,185,0)` | First discovery, notable value |
| `bg_dark` | `rgb(18,18,18)` | App background |
| `white` | `white` | Primary text |
| `label` | `rgb(145,145,145)` | Secondary labels |
| `label_dim` | `rgb(100,100,100)` | Timestamps, hints |
| `dim` | `rgb(60,60,60)` | Disabled / faint |
| `panel_border` | `rgb(90,90,90)` | Event log, chat log, situational panel borders |

There are also constants for overlay chrome, pip colours, chat source colours, and more.  Open `default.toml` for the full list.

### `[modes.*]` — Mode Borders & Headers

NOVA has five UI modes that change panel border colours:

| Mode | Trigger |
|------|---------|
| `ship` | In main ship, docked, supercruise |
| `combat` | Hardpoints deployed, in main ship |
| `on_foot` | On-foot / EVA |
| `srv` | Driving SRV |
| `offline` | No journal connection |

Each mode defines five colours:

| Key | Purpose |
|-----|---------|
| `border` | Panel border colour |
| `h1` | Section headers, modal borders |
| `h2` | Table column headers |
| `h3` | Key-value labels, inline dividers |
| `bg` | Section header background tint |

`analysis` automatically mirrors `ship`.

## Tips

- **Use `rgba(r,g,b,a)`** for translucent overlays (the `overlay_bg` key).
- **Only changed keys are needed.**  If a key is missing from your theme, the built-in default is used.
- **Invalid TOML** will silently fall back to the default palette — check the file syntax if colours don't change.
- **Share your themes!**  A theme file is self-contained; just copy the `.toml` file.

## Restart Required

Because Textual evaluates CSS when classes are defined (at import time), changing the active theme **requires a NOVA restart**.  The Settings overlay will automatically restart NOVA when you select a different theme and press SAVE.
