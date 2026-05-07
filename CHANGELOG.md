# Changelog

## v2.14.6 — 2026-05-07

### Bug Fixes

- **Volume control — +/- keys reset to config default**
  - `_update_example_file()` wrote `config.toml.example` on every `config.load()` call, including inside the hot-reload callback. The file-system watcher picked up that write and re-triggered the callback in a ~0.3 s loop, resetting `state.volume` to `default_volume` from config.toml after every keypress.
  - Fixed by calling `_notify_self_write()` after writing the example file so the watcher ignores self-generated events.
  - Also fixed `_on_config_changed` not updating `volume[0]` (the TTS worker list), keeping display and playback volume in sync on genuine config reloads.

---

## v2.14.5 — 2026-05-07

### Bug Fixes

- **#122 Material Tracker — category overflow & edge margins**
  - Category names (e.g. "Emission Data", "Data Archives") are now properly truncated with `…` when they exceed the allocated column width, preventing line breaks in narrow terminals
  - Added 1-space left and right margin to every material row so text no longer touches the panel walls

---

## v2.14.4 — 2026-05-07

### Enhancements

- **#126 Make missions better readable**
  - Empty line between each destination system block for clearer visual separation
  - Mission rows indented by 2 spaces relative to the column header
  - Blank line added between the massacre progress section and the first destination block

---

## v2.14.3 — 2026-05-07

### Enhancements

- **#122 Material Tracker — Compact Vertical List (Option A)**
  - Replaced horizontal grade-based tables with a compact vertical list: one row per material
  - Columns: Category | Grade | Name | Count/Cap | [Progress Bar] | Percentage
  - Global column alignment: widths computed once across all material types and applied uniformly
  - Space-filling progress bars: all remaining panel width goes to the bar after fixing other columns
  - Minimum 1-space gap between every column
  - Names truncate with … when tight; full names shown on wide terminals
  - Colour coding: dim grey (empty), white (partial), amber (near-cap), green (≥80%)
  - Scroll count fixed: counts individual material rows for smooth scrolling

---

## v2.14.2 — 2026-05-07

### Enhancements

- **#122 Material Tracker — Layout Overhaul**
  - Horizontal grade-based tables: G1–G5 as columns, categories as rows
  - Aligned columns within each material type (Raw / Manufactured / Encoded)
  - Two rows per category: name+count/cap, then progress bar+percentage
  - Responsive truncation for narrow terminals
  - Fixed scroll bug: scroll count now correctly includes category headers

---

## v2.14.1 — 2026-05-07

### Bug Fixes

- **#120 Fix wording in docking computer**
  - Coriolis, Orbis, and Ocellus station hints now use **Front / Back** terminology instead of inner / outer rings
  - All cylindrical station types are now consistent with the spatial layout relative to the mailslot

- **#121 Slow refresh rate of position in orbital cruise**
  - Status monitor now **slow-polls (5 s) in deep space** when no lat/lon/alt data is present
  - Fast-poll (0.2 s) preserved for: landed, SRV, on-foot, orbital cruise, and near-surface flight
  - Reduces unnecessary CPU load when exact positions aren't needed

---

## v2.14.0 — 2026-05-06

### Enhancements

- **#122 Material Tracker**
  - New Assets panel section showing full Raw (G1‑G4), Manufactured (G1‑G5), and Encoded (G1‑G5) material catalogues
  - Zero-count materials shown dimmed; owned materials highlighted with colour-coded stock levels
  - Progress bars and percentage indicators for every material
  - Uses the verified in-game material catalogue with correct caps per grade

- **#123 Fuel Warning**
  - Configurable fuel threshold (default 25%) in `config.toml`
  - Triggers `LowFuel` TTS voiceline and event log entry when fuel drops below threshold

- **#124 Home System**
  - New `home_system` config key — set your home system name
  - `FSDJump_Home` voiceline fires on arrival (falls back to `FSDJump` if undefined)

- **#125 Panel Toggles**
  - New `situational_panels` config key controls which situational panels are shown and in what order
  - Cycle left/right only visits visible panels

---

## v2.13.0 — 2026-05-05

### Enhancements

- **In-app Settings Overlay** (`S` key)
  - Live editable settings: TTS rate/volume, voice selection per language, panel toggles, fuel threshold, home system
  - Voice catalog fetched from `edge-tts` with language filtering
  - Settings saved back to `config.toml` on confirm (`Enter`)
  - Cancel (`Esc` / `Q`) discards changes

- **Bio Panel Improvements**
  - Distance and bearing calculations now use proper spherical geometry with body-radius scaling
  - Prescan and predicted body rows show genus list and estimated value range
  - First-footfall bonus tracking across sessions

- **Mission Panel Improvements**
  - Destination grouping: massacre missions to the same system are stacked with kill counts
  - Type badges (Massacre, Courier, etc.) and wing/influence indicators
  - Reward column with CR formatting and colour coding

---

## v2.12.0 — 2026-05-04

### Enhancements

- **Neutron Route Planner**
  - Integrated Spansh neutron router: request routes, monitor progress, display hop list with scoopable indicators
  - Scrollable route list with jump range and remaining distance

- **Colonisation Panel**
  - Track colonisation construction sites, required commodities, and completion progress
  - Commodity tables with delivered / required counts

- **Engineers Panel**
  - List view with rank pips, unlock status, and invite progress
  - Detail view with workshop location, modifications offered, and experimental effects

---

## v2.11.0 — 2026-05-03

### Enhancements

- **BGS Panel**
  - System-level faction influence tracking with colour-coded bars
  - State badges (Boom, War, Election, etc.) and pending/recovery indicators
  - Activity log grouped by system with timestamps

- **Route Panel**
  - In-system route display with next waypoint, distance, and scoopable star indicator
  - Station list for next system with services and landing pad sizes

- **Stats Panel**
  - Session and lifetime statistics: jumps, scans, mapped bodies, first discoveries, total exploration value
  - Credits balance and session earnings
