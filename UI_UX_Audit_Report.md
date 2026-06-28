# NOVA UI/UX Audit Report

**Date:** 2026-04-27
**Scope:** All windows, panels, styling, coloring, and control schemas
**Reference panels:** `ShipPanel` (top-center) and `BodiesPanel` ("Scanned Bodies", left column)

---

## 1. Executive Summary

NOVA’s visual identity is **strong and cohesive** at first glance. The amber/cyan-on-black palette directly echoes the Elite Dangerous cockpit HUD, giving it an authentic sci-fi feel. The two reference panels — `ShipPanel` and `BodiesPanel` — are the most polished parts of the UI and should serve as the baseline for standardization.

However, the codebase has **accumulated inconsistencies** over time:

- **Color leakage:** A "header gold" (`rgb(195,160,55)`) is hardcoded in ~23 locations but absent from the official palette.
- **Mixed styling mechanisms:** Some panels use Textual CSS, some use Rich inline styles, some use Rich markup strings, and some use Rich `Table`/`Panel` wrappers — often within the same file.
- **Control schema fragmentation:** Four different input-handling patterns coexist (`on_key()`, `BINDINGS`+`action_*`, panel methods called by the app, and focus-based dispatch).
- **Documentation drift:** The help screen and `Usage.md` contain inaccuracies about `Tab`, `w`/`s`, and `r` behavior.

**Verdict:** The UI looks good and functions well, but it lacks a single enforced design system. A consolidation pass would make future changes faster and prevent further drift.

---

## 2. Styling Consistency Analysis

### 2.1 Panel Inventory & Styling Approach

| Panel | Border Color | Styling Engine | Layout | Polish Rating |
|-------|-------------|----------------|--------|---------------|
| `SystemPanel` | `HUD_CYAN` | Rich `Table` + `Text` | Two-column table + header | ⭐⭐⭐ |
| `ShipPanel` | `AMBER` | Rich `Panel` + `Columns` + custom gauges | Gauge grids + button row | ⭐⭐⭐⭐⭐ |
| `RoutePanel` | `AMBER` | Rich `Text` (inline) | Label/value rows | ⭐⭐⭐ |
| `BodiesPanel` | `HUD_CYAN` | Rich `Table` | 8-column data table | ⭐⭐⭐⭐⭐ |
| `SituationalPanel` | Neutral grey (`rgb(90,90,90)`) | Mixed: `Table`, `Text`, Braille canvas, ASCII art | Mode-dependent | ⭐⭐⭐⭐ |
| `EventLogPanel` | Dark grey (`rgb(70,70,70)`) | Rich `Text` | Timestamp + prefix + message | ⭐⭐⭐ |
| `ChatLogPanel` | Chat blue (`rgb(0,120,160)`) | Rich `Text` | Same as EventLog | ⭐⭐⭐ |
| `FooterBar` | None | Rich `Table.grid` | 3-column status bar | ⭐⭐⭐⭐ |
| `SettingsScreen` | Gold (`rgb(195,160,55)`) | Textual CSS + `Static` rows | Vertical list | ⭐⭐⭐⭐ |
| `HelpScreen` | None (centered modal) | Rich `Table` + `Panel` | Two tables in a `Panel` | ⭐⭐⭐ |

### 2.2 Reference Panel Deep-Dive

#### `ShipPanel` — The Most Interactive Panel
- **Strengths:**
  - Uses `rich.panel.Panel` wrappers for each gauge, giving a tactile "card" feel.
  - Custom `_gauge_bar()` (█/░) and `_pip_bar()` (●/◑/○) provide immediate visual feedback.
  - Button row uses `reverse` style for active states — a clear, accessible toggle pattern.
  - Dynamic color shifts: shields turn `HUD_CRIT` when low, fuel turns `HUD_WARN` when low.
- **Weaknesses:**
  - On-Foot and SRV render paths duplicate most of the layout logic instead of sharing a generic gauge renderer.
  - Pip colors (`SYS`/`ENG`/`WEP`) are hardcoded; they are gameplay-accurate but not in the palette.

#### `BodiesPanel` — The Most Data-Dense Panel
- **Strengths:**
  - Clean 8-column table with alternating row backgrounds (`on rgb(38,38,38)`).
  - Hierarchical moon indentation (`↳`) makes relationships obvious.
  - Color-coded value states: `GOLD` (first disc + mapped), `AMBER` (first mapped), `white` (basic), `DIM` (none).
  - High-G warnings use distinct red/orange tiers (`≥3.0G` vs `≥1.5G`).
  - Dynamic border subtitle shows scroll position (`▲N ▼M`).
- **Weaknesses:**
  - Table header color `bold rgb(195,160,55)` is hardcoded and not in the palette.
  - Bio "needs DSS" color `rgb(0,220,80)` is a brighter green than `HUD_GREEN` — visually inconsistent.

### 2.3 Inconsistencies Found

#### A. Border Color Philosophy (No Guideline)
There is **no documented rule** for why a panel gets a specific border color:
- `SystemPanel` + `BodiesPanel` = Cyan (`HUD_CYAN`)
- `ShipPanel` + `RoutePanel` = Amber (`AMBER`)
- `SituationalPanel` = Neutral grey
- `EventLogPanel` = Dark grey
- `ChatLogPanel` = Chat-specific blue

**Recommendation:** Define a semantic border system. For example:
- **Cyan** = Information / position / exploration
- **Amber** = Ship status / target / actionable
- **Grey** = Logs / secondary readouts
- **Green/Purple/Red** = Mode overlays (already implemented at the `Screen` level for combat/analysis/on-foot/offline)

#### B. Mixed Styling Mechanisms
Every panel uses a different combination of technologies:

| Mechanism | Used By | Pros | Cons |
|-----------|---------|------|------|
| Textual `DEFAULT_CSS` | All panels | Declarative, hot-reloadable | Only handles widget-level borders/sizing |
| Rich inline `Text.append(style=...)` | Most panels | Fine-grained, fast | Verbose, easy to drift from palette |
| Rich markup strings (`[bold]...[/]`) | `SituationalPanel._make_title()` | Compact | Easy to typo, harder to lint |
| Rich `Table` | `BodiesPanel`, many situational sub-modes | Structured data | Header/row style definitions are scattered |
| Rich `Panel` | `ShipPanel` gauges, `Engineers` detail | Visual depth | Adds render overhead |

**Recommendation:** Pick a primary mechanism for each layer:
- **Widget chrome** (borders, height, width) → Textual CSS
- **Data tables** → Rich `Table` with centralized helper functions
- **Inline highlights** → Rich `Text` with palette constants only
- **Avoid** Rich markup strings except for truly dynamic content

#### C. Header / Section Label Color Drift
A "header gold" color family is used across ~23 locations but is **not in `palette.py`**:

| Hardcoded Color | Used In | Count |
|-----------------|---------|-------|
| `rgb(195,160,55)` | `BodiesPanel` header, `_section_header()`, Overview, Bio, Missions, Engineers, Wealth, Neutron, Stats | ~15 |
| `rgb(180,140,50)` | `_section_header()` background variant | ~5 |
| `rgb(255,220,80)` | `SituationalPanel` title highlight | ~2 |
| `rgb(255,200,0)` | `Colonisation` header | ~1 |

These are all variations of the same amber/gold family. `P.GOLD` (`rgb(230,185,0)`) exists but is brighter and used for "first discovery" data highlights, not headers.

**Recommendation:** Add a `HEADER` or `HDR_GOLD` constant to the palette and consolidate all header usages.

---

## 3. Color Palette Analysis

### 3.1 Current Palette (`ed_monitor/ui/palette.py`)

| Constant | Value | Role | Usage Count (panels.py) |
|----------|-------|------|------------------------|
| `AMBER` | `rgb(210,115,0)` | Primary accent | 48 |
| `AMBER_DIM` | `rgb(120,68,0)` | Muted amber | 8 |
| `LABEL` | `rgb(145,145,145)` | Secondary text | 116 |
| `HUD_GREEN` | `rgb(0,170,60)` | Positive / scoopable | 55 |
| `HUD_WARN` | `rgb(195,150,0)` | Warning | 14 |
| `HUD_CRIT` | `rgb(185,40,40)` | Critical / combat | 41 |
| `BG_DARK` | `rgb(18,18,18)` | Deep background | 4 |
| `HUD_CYAN` | `rgb(0,175,185)` | Info / analysis | 22 |
| `DIM` | `rgb(60,60,60)` | Disabled / faint | 23 |
| `WHITE` | `white` | Primary text | 6 |
| `GOLD` | `rgb(230,185,0)` | First discovery | 19 |
| `BLUE_SH` | `rgb(50,130,210)` | Shield / friend | 3 |
| `PURPLE` | `rgb(175,85,220)` | On-foot mode | 5 |
| `ANALYSIS` | `rgb(90,160,230)` | Analysis mode | 1 |

### 3.2 Sci-Fi Aesthetic & Contrast Assessment

**Aesthetic: ✅ Strong**
The amber/cyan/dark triad is instantly recognizable as "cockpit HUD." The low saturation of most colors (except critical red) keeps it from looking like a generic IDE theme.

**Contrast: ✅ Good, with caveats**
- `WHITE` on `BG_DARK` = excellent contrast (ratio ~18:1).
- `AMBER` on `BG_DARK` = good contrast (ratio ~7:1).
- `LABEL` (`rgb(145,145,145)`) on `BG_DARK` = acceptable (ratio ~5:1), but may be hard to read on cheap/dim terminals.
- `DIM` (`rgb(60,60,60)`) on `BG_DARK` = poor (ratio ~2:1). This is intentional for "disabled" elements, but it borders on invisible in sunlight.
- `HUD_WARN` (`rgb(195,150,0)`) is close to `AMBER` but slightly more yellow — this is fine for semantic differentiation.

**Brightness: ✅ Appropriate**
No colors are eye-searingly bright. Even `GOLD` and `HUD_CYAN` are subdued compared to pure RGB values. The only aggressive color is `HUD_CRIT`, which is correct for emergency states.

### 3.3 Hardcoded Colors That Should Use the Palette

Exact duplicates found in code:
- `rgb(0,175,185)` → `HUD_CYAN` (5× in panels.py, 2× in app.py)
- `rgb(210,115,0)` → `AMBER` (4× in panels.py)
- `rgb(185,40,40)` → `HUD_CRIT` (2× in app.py)
- `rgb(175,85,220)` → `PURPLE` (2× in app.py)
- `rgb(18,18,18)` → `BG_DARK` (2× in app.py, 2× in settings_screen.py)
- `rgb(60,60,60)` → `DIM` (1× in panels.py)

**`app.py` and `settings_screen.py` do not import the palette at all.** They redefine their own inline colors (`GOLD = "bold rgb(195,160,55)"`, `DIM = "rgb(140,140,140)"`).

### 3.4 Missing Palette Constants (Recommended Additions)

| Proposed Name | Value | Usage |
|---------------|-------|-------|
| `HEADER` | `rgb(195,160,55)` | Table headers, section titles, settings border |
| `HEADER_BG` | `rgb(45,35,10)` | Background behind section titles |
| `ROW_ALT` | `rgb(38,38,38)` | Alternating table row background |
| `LABEL_DIM` | `rgb(100,100,100)` | Timestamps, footer hints |
| `LABEL_LIGHT` | `rgb(160,160,160)` | Muted primary text |
| `HIGH_G_CRIT` | `rgb(220,60,0)` | ≥3.0G gravity warnings |
| `HIGH_G_WARN` | `rgb(220,140,0)` | ≥1.5G gravity warnings |
| `BIO_DSS` | `rgb(0,220,80)` | Bio "needs DSS" highlight |

### 3.5 Contrast Issues to Address

1. **`rgb(120,120,80)` on `BG_DARK`** (Bio panel hints)
   - Very low contrast, muddy appearance. Suggest `LABEL` or `AMBER_DIM`.
2. **`rgb(140,130,60)` and `rgb(160,130,60)`** (Wealth panel hints)
   - Dark yellow-browns on near-black. Suggest `LABEL` or `HEADER`.
3. **`rgb(45,35,10)` behind `rgb(180,140,50)`** (`_section_header`)
   - The background is so dark it adds almost no visible depth. Consider removing the background or lightening it slightly.

---

## 4. Control Schema Analysis

### 4.1 Global Controls (`NOVAApp.on_key()`)

| Key | Action | Notes |
|-----|--------|-------|
| `q` | Quit | Immediate |
| `Esc` | Clear focus → Quit | Two-stage, intuitive |
| `?` | Help screen | Correct |
| `1`–`6` | Focus panel N | Good for mouseless navigation |
| `0` | Clear focus | Correct |
| `Tab` | Cycle **focused panels** 1→6 | ⚠️ Help text says "Cycle situational panel forward" |
| `Shift+Tab` | Cycle focused panels 6→1 | ⚠️ Same help text error |
| `←` / `→` | Cycle **situational modes** | Correct, but undiscovered for new users |
| `↑` / `k` | Scroll situational up | Also `galaxy` back, `engineers` up, etc. |
| `↓` / `j` | Scroll situational down | Also `galaxy` forward, `engineers` down, etc. |
| `PgUp` / `PgDn` | Scroll focused panel by 5 (or situational) | Correct |
| `Home` | Jump to latest events (if log focused) | ⚠️ Docs say `Home / g` but `g` is chat mute |
| `w` | Scroll Bodies panel **up** by 1 | ⚠️ Docs say `w / s` for up/down, but `s` opens Settings |
| `s` | Open **Settings** overlay | ⚠️ Conflicts with doc claim that `s` scrolls bodies down |
| `r` | Cycle Maps sub-screen **forward** | ⚠️ Docs imply bidirectional; code is forward-only |
| `n` | Neutron route input | Mode-gated correctly |
| `m` | Mute/unmute all TTS | Correct |
| `g` | Toggle in-game chat TTS | Correct |
| `t` | Toggle Twitch chat TTS | Correct |
| `y` | Toggle YouTube chat TTS | Correct |
| `p` | Toggle all chat TTS at once | Correct |
| `+` / `=` | Volume up (+5) | Correct |
| `−` / `-` | Volume down (-5) | Correct |
| `Enter` | Engineers select/back | ⚠️ Not documented in HelpScreen |

### 4.2 Per-Panel / Contextual Controls

#### Settings Overlay (`SettingsScreen`)
Uses Textual's **declarative `BINDINGS`** — the only screen that does.

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate rows |
| `←` / `→` | Cycle toggle/select values |
| `Enter` | Activate Save / open text editor |
| `Esc` | Cancel editor / close screen |

**Inconsistency:** Settings uses `BINDINGS`+`action_*` while the rest of the app uses `on_key()`. This is functionally fine (SettingsScreen blocks app keys via `isinstance(self.screen, SettingsScreen)`), but it splits the mental model for developers.

#### Engineers Mode (`SituationalPanel` sub-mode)
| Key | Action |
|-----|--------|
| `↑` / `↓` or `k` / `j` | Move cursor |
| `Enter` | Open detail / return to list |

This is the only situational mode with an "Enter" action. It is documented in `Usage.md` but **not in the HelpScreen**.

#### Galaxy / Maps Mode (`SituationalPanel` sub-mode)
| Key | Action |
|-----|--------|
| `↑` / `↓` or `r` | Cycle scale forward (`system → regional → galaxy`) |
| `k` | Cycle scale **backward** |

**Inconsistency:** There is no `R` or `shift+r` for backward cycling. The only way to go back is `↑`/`k`, which is inconsistent with the `r` key's forward-only behavior.

#### Bodies Panel
| Key | Action |
|-----|--------|
| `w` | Scroll **up** by 1 |
| `s` | ❌ **No scroll-down key exists** |

`Usage.md` claims `w / s` scrolls the bodies panel up/down, but `s` globally opens Settings. There is no key bound to `scroll_bodies(+1)`. The user must focus the panel (`4`) and use `↓` or `PgDn`.

### 4.3 Control Schema Issues Summary

| # | Issue | Severity |
|---|-------|----------|
| 1 | **HelpScreen lies about `Tab`/`Shift+Tab`** — says situational cycle, actually focuses panels | 🔴 High |
| 2 | **`w` has no down counterpart** — `s` is Settings, not bodies scroll down | 🔴 High |
| 3 | **`Home / g` docs are wrong** — `g` toggles in-game chat TTS, not jump to events | 🟡 Medium |
| 4 | **`r` is forward-only** but docs imply cycling; no dedicated backward key | 🟡 Medium |
| 5 | **`Enter` for Engineers** is undocumented in HelpScreen | 🟡 Medium |
| 6 | **Settings uses `BINDINGS`, rest uses `on_key()`** — developer cognitive load | 🟢 Low |
| 7 | **No visual focus indicator documentation** in `Usage.md` | 🟢 Low |

---

## 5. Recommendations

### 5.1 Immediate Actions (High Impact, Low Effort)

1. **Fix the HelpScreen text**
   - Change `Tab` description to "Cycle focused panel forward (1→6)"
   - Change `Shift+Tab` description to "Cycle focused panel backward (6→1)"
   - Remove `w / s` bodies scroll claim; change to `w` = "Scroll bodies panel up" and note that focused panel arrows also work
   - Fix `Home` description (remove `/ g`)
   - Add `Enter` = "Engineers: open detail view"

2. **Add a `scroll_bodies(+1)` key**
   - Bind `S` (capital S) or `x` to scroll down, or document that `↓`/`PgDn` work when the panel is focused.

3. **Import `palette` in `app.py` and `settings_screen.py`**
   - Replace exact-match hardcodes (`rgb(0,175,185)`, `rgb(210,115,0)`, etc.) with palette constants.

### 5.2 Short-Term Improvements (Medium Effort)

4. **Expand `palette.py` with missing constants**
   ```python
   HEADER      = "rgb(195,160,55)"
   HEADER_BG   = "rgb(45,35,10)"
   ROW_ALT     = "rgb(38,38,38)"
   LABEL_DIM   = "rgb(100,100,100)"
   LABEL_LIGHT = "rgb(160,160,160)"
   HIGH_G_CRIT = "rgb(220,60,0)"
   HIGH_G_WARN = "rgb(220,140,0)"
   BIO_DSS     = "rgb(0,220,80)"
   ```
   Then replace all hardcoded occurrences.

5. **Standardize the `_section_header()` helper**
   - Ensure all situational sub-modes use the same helper (some currently inline their own gold-on-brown header).
   - Move `_section_header` to the module level if it isn't already, and enforce its use.

6. **Document the border color philosophy**
   - Add a comment block to `palette.py` or `app.py` explaining the semantic meaning of each border color (Cyan = info, Amber = ship/status, etc.).

### 5.3 Structural Improvements (Higher Effort)

7. **Create a `_PanelBase` with common rendering utilities**
   - A shared base class or mixin that provides:
     - `_header(text)` — consistent gold header
     - `_table(columns)` — consistent table with alternating rows and gold header
     - `_label_value(label, value)` — consistent two-column row
   - This would reduce duplication and enforce consistency across `SystemPanel`, `RoutePanel`, and situational sub-modes.

8. **Unify input handling**
   - Consider migrating all screens to Textual's `BINDINGS` system, or explicitly document that `on_key()` is the app-wide pattern and `SettingsScreen` is the exception.
   - Alternatively, keep `on_key()` for the app but add a `_handle_key(key)` dispatch table instead of the long `if/elif` chain for readability.

9. **Add a UI Style Guide document**
   - A new file (e.g., `docs/UI_Style_Guide.md`) that covers:
     - Color semantics (what each palette constant means)
     - Border color rules
     - When to use `Table` vs `Text` vs `Panel`
     - Typography hierarchy (header > label > value > dim)
     - Control schema conventions (global vs focused vs modal)

### 5.4 Contrast & Accessibility Fixes

10. **Audit low-contrast combinations**
    - Replace `rgb(120,120,80)` bio hints with `LABEL` or `AMBER_DIM`.
    - Replace `rgb(140,130,60)` / `rgb(160,130,60)` wealth hints with `LABEL`.
    - Evaluate `_section_header()` background — either remove `on rgb(45,35,10)` or lighten it to `rgb(60,50,20)` for visible depth.

---

## 6. Conclusion

NOVA's UI is **functional, atmospheric, and mostly cohesive**. The `ShipPanel` and `BodiesPanel` are excellent templates that establish a strong sci-fi HUD identity. The color palette is well-chosen and appropriate for long gaming sessions.

The main problems are **accumulated drift** rather than fundamental flaws:
- Colors leak out of the palette file.
- Control documentation is slightly out of sync with code.
- Styling mechanisms vary from panel to panel without a documented reason.

A single consolidation pass — expanding the palette, centralizing header/table helpers, and correcting the help text — would bring the entire UI up to the standard set by the best panels.
