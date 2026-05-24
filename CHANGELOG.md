# Changelog

## v2.15.2 — 2026-05-24

### Bug Fixes

- **TTS audio engine stops after extended use**
  - `pygame.mixer.quit()` was never called after playback. The mixer was initialised on every TTS message but never shut down, leaking audio resources until the process exited. When another application (e.g. a Python overlay using edge-tts/pygame) competed for the same audio device, the mixer would eventually stop responding.
  - Added `pygame.mixer.quit()` in `finally` blocks on Windows and in the Linux subprocess fallback.

- **PipeWire audio routing improved**
  - Reordered Linux audio backends: plain `mpg123` is now tried before `mpg123 -o pulse`. On PipeWire systems the ALSA route is often more reliable when multiple apps compete for the audio device.

---

## v2.15.0 — 2026-05-24

### Features

- **Complete TTS unit localization for all supported languages**
  - NOVA now speaks units, measurements, and status phrases in the user's configured `tts_lang` instead of mixing English into non-English sentences.
  - Localized: light years/seconds, credits, population (million/billion), temperature (Kelvin), distance (kilometres), mass (Earth masses), gravity (G), orbital period (minutes/hours/days), and many more.
  - Added `[units]` tables to all 7 built-in voiceline TOMLs (`en`, `de`, `fr`, `es`, `it`, `pt`, `ru`) so every unit word is translated.

- **Slavic plural support for Russian TTS**
  - Russian uses 3 plural forms (1 / 2–4 / 5+). NOVA now correctly selects "световой год" (1), "световых года" (2–4), or "световых лет" (5+) based on the number.
  - Added `_slavic_plural()` helper and `unit_for()` with plural dispatch to `voicelines.py`.

- **Localized FSDJump suffixes**
  - Star class, scoopable status, remaining jumps, and population are now spoken in the target language.
  - Example (German): "Ankunft in Zeessze. Sprung über 11,2 Lichtjahre. Stern Typ K, tankbar. 3 Sprünge verbleiben. Bevölkerung: 37 Millionen."

### Bug Fixes

- **Fixed duplicate `[FSDJump_Home]` key in `en.default.toml`**
  - The duplicate table caused `tomllib` to reject the entire English voiceline file, silently breaking all English TTS fallback paths.

- **Translated `FSDJump_Home` in all non-English languages**
  - Previously this line was always spoken in English regardless of language setting.

- **Eliminated `{bio_word}` / `{verb}` dependency in bio scan voicelines**
  - These variables only worked for English grammar ("is" / "are", "bio" / "bios"). Each language now uses its own natural sentence structure.

- **Moved `First footfall bonus applied` into WHEN...THEN blocks**
  - Previously hardcoded English string; now localized per language via conditional voiceline templates.

---

## v2.14.10 — 2026-05-10

### Bug Fixes

- **Clean up localisation tokens in target names**
  - Elite Dangerous sometimes emits raw internal keys like `$MULTIPLAYER_SCENARIO79_TITLE;` in `Status.json Destination.Name` when a localised string is missing (e.g. for new Frontline zones, Megaships, etc.). This produced unreadable text in the Target panel.
  - Added `_clean_localised()` in `events.py` which strips the `$...;` wrapper and turns underscores into readable Title Case text.
  - Applied to `target_body`, `target_body_system`, `target_body_body`, and `nearest_body` in `status.py` so every destination read from `Status.json` is sanitised at the source.

---

## v2.14.9 — 2026-05-10

### Features

- **Improved target information for all target types**
  - Surface settlements / planetary ports now show their parent **body** (planet/moon) when targeted.
  - Cross-system targets (bodies, stations, or settlements in another system) now display the **target system** name.
  - Unknown targets (systems or bodies not in the local database) now show any available **EDSM route data** (population, allegiance) if the target happens to be a route waypoint.
  - `_render_target()` fallback no longer displays a bare name — it always provides context (system, body, or EDSM metadata).

---

## v2.14.8 — 2026-05-10

### Features

- **Station targeting in Target panel**
  - When a station is targeted (via left-panel nav or galaxy map), the Target panel now displays EDSM station data instead of falling through to "No target".
  - Shows: station name, type (Coriolis, Outpost, etc.), distance from star, and services icons (M=Market, S=Shipyard, O=Outfitting, R=Repair, F=Refuel, N=Restock).
  - If the station is in a different system, the system name is shown too.
  - Implementation: `status.py` reads `Destination.System` from `Status.json`; `journal.py` fetches current-system stations from the local EDSM dump; `panels.py` looks up the target in current/route/nearest station lists and renders the info.

---

## v2.14.7 — 2026-05-10

### Bug Fixes

- **Volume control — +/- keys still reset to config default**
  - v2.14.6 fixed the reload loop caused by `config.toml.example` writes, but the watchdog path still fired on *every* file change inside `~/.config/nova/`. This meant overlay `.txt` writes (1 Hz) and bindings backups triggered spurious config reloads, which unconditionally reset `state.volume` to `default_volume`.
  - Fixed by filtering the `watchdog` event handler so it only reacts to `config.toml` and `*.toml` files directly inside `voicelines/`. All other files in the config directory (overlay, bindings_backup, cache, etc.) are now ignored.

---

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
