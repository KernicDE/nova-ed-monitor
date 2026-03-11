# NOVA — Project Reference

## Run
```bash
cd /home/kernic/Documents/ed-monitor
python -m ed_monitor
```

## Structure
```
ed_monitor/
  __main__.py      entry point: thread launch, NOVAApp
  config.py        k=v config parser (~/.config/nova/config.toml)
  state.py         AppState dataclass, BodyInfo, BioScan, LogEvent, EventCategory
  events.py        handle(ev, state, lock, tts_q, db) — all 50+ journal events
  journal.py       file tail + inode rotation + DB replay on startup
  status.py        Status.json poll + Cargo.json + Materials.json; bio haversine
  edsm.py          EDSM fetch thread (bodies + stations), dedup queue, no API key needed
  db.py            SQLite persistence (~/.local/share/nova/events.db)
  tts.py           edge-tts subprocess + pygame playback, priority queue
  twitch.py        Twitch IRC anonymous chat monitor → ChatLogPanel + TTS
  overlay.py       stream_info.txt writer for OBS/Streamlabs overlays
  ui/
    app.py         Textual App (NOVAApp), CSS layout, keybindings
    panels.py      all Widget subclasses
```

## Architecture
- Daemon threads: journal, status, TTS, EDSM, twitch (optional), overlay
- `AppState` + `threading.RLock` — threads write, Textual reads via shallow copy
- Textual 500ms timer: `_snapshot()` → `update()` each panel
- Threads never call Textual APIs directly

## Layout (app.py CSS)
```
top-row:    [SystemPanel 4fr] [ShipPanel 5fr] [RoutePanel 3fr]
middle-row: [left 4fr: BodiesPanel] [center 5fr: SituationalPanel] [right 3fr: EventLog 2fr / ChatLog 1fr]
footer:     FooterBar (1 row)
```

## Config (~/.config/nova/config.toml)
- `journal_dir` — override auto-detected journal path
- `twitch_channel` — Twitch channel name; leave empty/commented to disable Twitch
- `tts_rate` — edge-tts rate (default: `+10%`)
- `tts_voice_<lang>` — voice per language code: `en`, `de`, `fr`, `it`, `es`, `pt`, `ru`

Migration: if `~/.config/nova/config.toml` doesn't exist, old `~/.config/ed-monitor/config.toml` is copied.

## TTS Language Detection (events.py)
Supported languages and default voices:
| Code | Language   | Default Voice          | Verb      |
|------|-----------|------------------------|-----------|
| en   | English   | en-GB-SoniaNeural      | says      |
| de   | German    | de-DE-KatjaNeural      | sagt      |
| fr   | French    | fr-FR-DeniseNeural     | dit       |
| it   | Italian   | it-IT-ElsaNeural       | dice      |
| es   | Spanish   | es-ES-ElviraNeural     | dice      |
| pt   | Portuguese| pt-PT-RaquelNeural     | diz       |
| ru   | Russian   | ru-RU-SvetlanaNeural   | говорит   |

Detection priority: Cyrillic → ñ/¿/¡ → ã/õ → German umlauts → word list scoring → EN fallback.

Twitch messages prefix the TTS with "Twitch" (e.g. "Twitch user says: hello").

## Status.json Flags (status.py)
| Constant | Bit | Meaning |
|---|---|---|
| FLAG_DOCKED | 1<<0 | Docked |
| FLAG_LANDED | 1<<1 | Landed on surface |
| FLAG_SHIELDS_UP | 1<<3 | Shields up |
| FLAG_SUPERCRUISE | 1<<4 | In supercruise |
| FLAG_FA_OFF | 1<<5 | Flight assist off |
| FLAG_HARDPOINTS | 1<<6 | Hardpoints deployed |
| FLAG_MASS_LOCKED | **1<<16** | FSD mass locked (NOT 1<<7 = In Wing) |
| FLAG_IN_MAIN_SHIP | 1<<24 | Player in main ship |
| FLAG_IN_SRV | 1<<26 | Player in SRV |
| FLAG_ANALYSIS_MODE | 1<<27 | Analysis mode |

## ScanOrganic Handling (events.py)
- `Log` → samples=1, body_name = `state.nearest_body or state.system or "Unknown"`
- `Sample` → `sc.samples = min(sc.samples + 1, 2)` (capped; Analyse sets 3)
- `Analyse` → samples=3, complete=True, value from event data

## Bio Distance (status.py `_check_bio_distance`)
- Returns early if lat/lon is None (preserves last known distances)
- Uses `sample_lats`/`sample_lons` lists on BioScan (falls back to `last_lat/last_lon`)
- Finds nearest sample via haversine, computes bearing away
- TTS fires when `best_dist >= sc.min_dist` and not already alerted

## Mass Lock TTS (status.py)
- Gated on `prev_in_main_ship and new_in_main_ship` — suppresses announce when boarding/exiting ship

## Startup / Shutdown Voice Lines
- On launch: "NOVA active." (suppresses all COVAS callouts from the first Status.json read)
- On `Shutdown` event: "Systems powering down. Farewell, Commander."

## SituationalPanel Modes
Auto-resolve priority: incomplete bio_scans → "bio"; missions+not supercruise → "missions"; else → "overview"
Tab cycles: auto → overview → inventory → bio → missions → engineers → auto

## RoutePanel Context
1. Docked: shows station services (from `state.station_*`, populated by Docked event)
2. ApproachBody set: shows body info
3. Otherwise: shows nav route

## Known Quirks
- BioScan `first_footfall` field exists but detection not implemented
- EDSM fetch is GET-only, no API key required
- `pygame.mixer.init()` called per-track (safe/idempotent)
- ChatLogPanel filters `EventCategory.Chat` only
- Bodies table alternating rows: `row_styles=["", "on rgb(25,25,25)"]`
- hull/shield percentages are rounded (not floored) to match in-game HUD
