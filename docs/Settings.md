# Settings Guide

## In-App Settings Overlay

Press **`s`** from anywhere in NOVA to open the Settings overlay. Navigate with ↑/↓, change toggles and selectors with ←/→, edit text fields with Enter. Press **SAVE** to write the config and apply all changes immediately — no restart needed. Press **ESC** to close without saving.

The overlay covers all settings: TTS language, voice, rate, volume, notable-body threshold, Twitch/YouTube channels, chat TTS, overlay/screenshot dirs, debug log, and fleet carrier lookup.

## Config File

Changes made via the Settings overlay are written to `config.toml`. You can also edit this file directly — NOVA detects changes and applies them **within 2 seconds** (config hot-reload, no restart needed).

| Install type | Path |
|-------------|------|
| Portable (launcher) — Linux | `<script folder>/config/config.toml` |
| Portable (launcher) — Windows | `<script folder>\config\config.toml` |
| System install — Linux | `~/.config/nova/config.toml` |
| System install — Windows | `%USERPROFILE%\.config\nova\config.toml` |

All settings are optional — commented lines use defaults.

---

---

## Journal Directory

```toml
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous
```

NOVA auto-detects the journal directory on most setups. Set this only if auto-detection fails.

**Default locations:**

| Platform | Path |
|----------|------|
| Linux (Steam/Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Windows | `C:\Users\YourName\Saved Games\Frontier Developments\Elite Dangerous` |
| macOS | `~/Library/Application Support/Frontier Developments/Elite Dangerous` |

---

## TTS Voice & Language

```toml
# Language for NOVA's own voiceovers (en, de, fr, it, es, pt, ru):
# tts_lang = en

# Voice speed adjustment (e.g. +10%, -5%, +0%):
# tts_rate = +10%

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural
```

**Supported languages:** `en` (English), `de` (German), `fr` (French), `it` (Italian), `es` (Spanish), `pt` (Portuguese), `ru` (Russian)

Language detection for chat messages and in-game names is **automatic** — NOVA detects the language per message and picks the correct voice.

To find all available edge-tts voices:
```bash
edge-tts --list-voices
```

---

## Twitch Integration

```toml
# Twitch channel name — leave commented to disable:
# twitch_channel = yourchannel
```

Reads chat anonymously (no login, no API key needed). Announces messages via TTS as:
*"User {name} on Twitch says: {message}"*

---

## YouTube Live Chat

```toml
# YouTube channel handle — leave commented to disable:
# youtube_channel = @yourchannel
```

Monitors your live stream chat anonymously (no API key needed). Announces messages via TTS as:
*"User {name} on YouTube says: {message}"*

---

## EDSM Nightly Data

No configuration required. NOVA automatically downloads and refreshes EDSM and Spansh nightly dumps once per day:

| Dump | Data provided |
|------|---------------|
| `systemsPopulated.json.gz` | Nearest inhabited system, allegiance, population |
| `powerPlay.json.gz` | Power Play controlling power and state per system |
| `stations.json.gz` | Stations at next route waypoint and at nearest inhabited system (market, shipyard, outfitting, refuel, repair, rearm) |
| `systems_neutron.json.gz` | Neutron star positions for the local route planner (~50 k systems) |

Data is stored in the local SQLite database (`events.db`). The database grows by roughly 50–80 MB after the first download (EDSM + neutron stars). Downloads happen in the background — NOVA starts immediately and populates data as soon as the import is complete.

---

## Notable Body Value Threshold

```toml
# Minimum body value (Cr) to appear in the Overview notable bodies list.
# ELW / Water / Ammonia worlds, terraform candidates, and bio signals are always shown.
# notable_value_threshold = 500000
```

---

## Screenshot Processing

```toml
# Source folder — ED screenshot directory (leave empty to auto-detect):
# screenshot_dir = /path/to/screenshots

# Destination folder (default: ~/Pictures/Elite Dangerous):
# screenshot_dest = ~/Pictures/Elite Dangerous
```

NOVA watches the ED screenshot folder and automatically:
1. Converts BMP files to PNG (requires the `Pillow` library, installed automatically)
2. Renames each file to `YYYY-MM-DD-HH-MM_CMDR_SYSTEM_BODY.png`
3. Moves the file to the destination folder, creating it if needed

**Auto-detected source directories (checked in order):**

| Platform | Default path |
|----------|-------------|
| Linux (Proton / default Steam) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/…/Pictures/Frontier Developments/Elite Dangerous` |
| Linux (Proton / Flatpak Steam) | `~/.var/app/com.valvesoftware.Steam/…/Pictures/Frontier Developments/Elite Dangerous` |
| Windows / native | `~/Pictures/Frontier Developments/Elite Dangerous` |

If auto-detection fails, set `screenshot_dir` explicitly.

---

## Neutron Route Planner

No configuration required. NOVA downloads the Spansh neutron-star dump (`systems_neutron.json.gz`) once per day and stores it locally. Routes are computed entirely offline — no live API calls.

To use: press `Tab` until the **Neutron** panel is active, then press `n` and type a destination system name. The route appears immediately using your ship's current max jump range (read from the `Loadout` journal event; fly your ship once after launching NOVA to populate it).

Route accuracy: the planner uses a greedy A* algorithm — results are good for most routes. For very long routes in sparse regions, quality approaches the Spansh website's output.

---

## Fleet Carrier Lookup

```toml
# Enable Spansh API lookup for fleet carriers in current system:
# carrier_lookup = false
```

When enabled, NOVA queries the [Spansh](https://spansh.co.uk) API each time you jump to a new system and displays any fleet carriers found in the Overview panel. Results are cached for 5 minutes and at most one API call is made every 3 seconds. **Disabled by default** — enable if you actively use carriers.

---

## Event Log Retention

```toml
# prune_events_days = 0
```

Set to a positive integer to automatically delete event-log rows older than N days at every NOVA launch. Default `0` keeps the entire history (existing behaviour). Useful on portable installs where `events.db` keeps growing — a value of `180` typically keeps the database under a few MB while preserving a full six-month window.

When pruning runs, NOVA logs the deletion count at INFO (visible in the debug log when `debug_log = true`).

---

## Debug Logging

```toml
# debug_log = false
```

When set to `true`, NOVA writes a detailed log file each session:

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/nova-debug.log` |
| Windows | `%USERPROFILE%\.config\nova\nova-debug.log` |

The log is **overwritten on every launch** so it always reflects the latest session. It covers all background processes: journal monitoring, status polling, EDSM/Spansh API calls, TTS generation and playback, Twitch/YouTube connections, and keybindings changes.

**Disabled by default.** Enable it when you need to diagnose a problem and want to share the log with the developer.

---

## Keybindings Backup

No configuration required. NOVA automatically monitors your Elite Dangerous `.binds` file and creates a timestamped backup whenever it changes. Backups are stored in:

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/bindings_backup/` |
| Windows | `%USERPROFILE%\.config\nova\bindings_backup\` |

The last **5 backups** are kept; older ones are deleted automatically. When a backup is created, a `SYS` event appears in the UI event log. Preset switches are also detected and logged. This feature is always active — there is no setting to disable it.

---

## Situational Panel Visibility

You can control which panels appear in the centre **Situation** column and their tab order. By default all panels are shown.

### In-App Settings

Open the Settings overlay with **`s`**, scroll down to the panel list, and enter a number for each panel you want visible:

```
[1 ] Overview
[2 ] Bio
[3 ] Maps
[   ] Missions        ← hidden (no number)
[4 ] Engineers
...
```

- **Lowest number = leftmost tab**, highest = rightmost.
- **Gaps are OK** — numbering like `1, 3, 4, 6` works fine.
- **Empty field = hidden** — the panel will not appear and auto-switching will skip it.
- Press **SAVE** to apply immediately (no restart needed).

### Config File

You can also edit `config.toml` directly:

```toml
# Show only Overview, Bio, and Missions in that order
situational_panels = OVR BIO MIS

# Full list of abbreviations:
#   OVR = Overview      BIO = Bio        MAP = Maps (Galaxy)
#   MIS = Missions      ENG = Engineers  BGS = BGS
#   COL = Colonisation  ROU = Route      NTR = Neutron Plot
#   AST = Assets        STS = Stats
```

Legacy abbreviations (`WLT`, `INV`, `DKG`) are automatically remapped to `AST` and `OVR`.

---

## Stream Overlay (OBS/Streamlabs)

NOVA writes a text file for use as a "Read from file" **Text** source in OBS or Streamlabs.

```toml
# overlay_line_1 = NOVA
# overlay_line_2 = {ship_name} ({ship_type})
# overlay_line_3 = {system} — {position}
# overlay_line_4 = JUMPS: {jumps_left}
# overlay_separator =      ////
# overlay_uppercase = true
# overlay_path = stream_info.txt
```

Lines whose variable evaluates to empty/zero are skipped automatically.

**Available variables:**

| Variable | Example |
|----------|---------|
| `{commander}` | `CMDR Hawk` |
| `{ship_name}` | `Krait Phantom` |
| `{ship_type}` | `KraitPhantom` |
| `{system}` | `Sol` |
| `{position}` | `Hutton Orbital` or `Deep Space` |
| `{jumps_left}` | `4` (line skipped when 0) |
| `{route_next}` | `Alpha Centauri` (line skipped when empty) |
| `{hull_pct}` | `98%` |
| `{fuel_t}` | `28.4t` |
| `{fuel_max_t}` | `32t` |

---

## Voiceline Customisation

On first launch NOVA copies the built-in voiceline files to a **reference folder** in your config directory. Do not edit those — they are overwritten on every launch.

| Purpose | Portable path | System install path (Linux) |
|---------|---------------|-----------------------------|
| Reference (read-only) | `<script folder>/config/voicelines/default/` | `~/.config/nova/voicelines/default/` |
| User overrides | `<script folder>/config/voicelines/` | `~/.config/nova/voicelines/` |

**Windows system install:** replace `~/.config` with `%USERPROFILE%\.config`.

NOVA **hot-reloads** voiceline files — editing your `en.toml` while NOVA is running takes effect within 2 seconds. If your file has a TOML syntax error, NOVA logs a warning in the event log and speaks a TTS alert, then falls back to built-in defaults.

Create a file named `en.toml` (or `de.toml`, `fr.toml`, etc.) in the user overrides folder. Only define the events you want to change — everything else uses the built-in defaults.

### Format

```toml
[FSDJump]
add = [
    "Extra variant one.",
    "Another jump complete, heading to {system}.",
]

[FuelScoop]
replace = [
    "Fuel collected.",
]

[SomeEvent]
replace = []   # empty list = silence this event entirely
```

- **`add`** — appends your lines to the built-in pool (more random variety).
- **`replace`** — replaces the built-in lines entirely for this event.
- **`replace = []`** — silences the event completely.

Keys absent from your file continue to use the built-in defaults. Your file is never overwritten by NOVA updates.

### Template Engine

Templates support two advanced features evaluated before variable substitution:

**Includes** — reusable fragments (key must start with `_`):

```toml
[_ship_status]
add = ["{ship_name} — hull {hull}, fuel {fuel}."]

[FSDJump]
add = ["Arrived in {system}. {_ship_status}"]
# or explicit form (required when key name contains hyphens):
add = ["Arrived in {system}. {include:_ship_status}"]
```

- Missing fragment keys expand to `""` with a warning logged.
- Circular includes are detected (depth > 5) and expand to `""`.
- The shorthand `{_KeyName}` supports letters, digits and underscores only. Use `{include:_key-name}` for hyphens.

**Conditionals** — inline `WHEN condition THEN "text";` blocks:

```toml
[Scan_Notable]
add = ['Scanned {body_short}. WHEN {value_raw} > 500000 THEN "Worth {value}."; WHEN {bio_count} > 0 THEN "{bio_count} bio signals.";']

[FSDJump]
add = ['Jumped to {system}. WHEN {is_star_scoopable} IS TRUE THEN "Scoopable star.";']
```

Condition true → text is inserted. Condition false → the whole `WHEN...;` block is replaced with `""`. The `;` at the end is optional when the block is the last thing in the string.

**Supported operators:**

| Operator | Example |
|----------|---------|
| `IS TRUE` | `WHEN {is_terraformable} IS TRUE THEN "..."` |
| `IS FALSE` | `WHEN {first_disc} IS FALSE THEN "..."` |
| `IS NOT TRUE` | `WHEN {landable} IS NOT TRUE THEN "..."` |
| `==` / `!=` | `WHEN {economy} == "Refinery" THEN "..."` |
| `<` / `>` / `<=` / `>=` | `WHEN {value_raw} > 500000 THEN "..."` |
| `AND` / `OR` | `WHEN {bio_count} > 0 AND {first_disc} IS TRUE THEN "..."` |

Truthy: non-empty value that is not `"0"` or `"false"`. Boolean variables (`{is_terraformable}`, `{is_scoopable}`, `{is_star_scoopable}`) are `True`/`False` — use `IS TRUE` / `IS FALSE`. Flag variables (`{landable}`, `{first_disc}`, etc.) are `""` when absent, so `IS TRUE` works naturally. Unknown `{variable}` names silently expand to `""`.

### Available template variables

Variables differ per event key — see the reference files in `default/` for the full list. Common ones:

| Variable | Meaning |
|----------|---------|
| `{system}` | Destination or current system name |
| `{dist_ly}` | Jump distance formatted for speech |
| `{station}` | Station name |
| `{body}` / `{body_short}` | Full / short body name |
| `{value}` / `{value_raw}` | FSS scan value (formatted / raw number) |
| `{value_mapped}` / `{value_mapped_raw}` | Projected or actual DSS payout with all bonuses |
| `{is_terraformable}` | `True` when terraformable (alias `{terra}`) |
| `{landable}` | Non-empty when landable |
| `{first_disc}` | Non-empty when first discovered |
| `{bio_count}` / `{geo_count}` | Bio / geo signal counts |
| `{name}` | Commander / pilot / species name |
