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
  config.py        paths: config_dir(), data_dir(), logs_dir() — portable-root aware; k=v TOML parser
  state.py         AppState dataclass, BodyInfo, BioScan, LogEvent, EventCategory; body value formula functions
  events.py        handle(ev, state, tts_q) — all 50+ journal events; _say() via voiceline keys
  journal.py       file tail + inode rotation + DB replay on startup
  status.py        Status.json poll + Cargo.json + Materials.json; bio haversine; pips parsing
  voicelines.py    TOML voiceline loader/picker; pick(key, lang, **kwargs); template engine (includes + conditionals)
  voicelines/      en/de/fr/it/es/pt/ru.default.toml — 87 events × 3–5 variants each; user-overridable via config/voicelines/{lang}.toml
  edsm.py          EDSM fetch thread (bodies + stations), dedup queue, no API key needed
  edsm_dumps.py    EDSM nightly dump downloader: systemsPopulated, stations, powerPlay; streams gzip; daily refresh
  spansh.py        Spansh API fleet carrier lookup (POST /api/stations/search); cache 300s; rate limit 3s
  neutron.py       local neutron route planner; downloads systems_neutron.json.gz daily; greedy A* via SQLite
  screenshots.py   ED screenshot watcher; BMP→PNG via Pillow; renames + moves to ~/Pictures/Elite Dangerous
  db.py            SQLite persistence (data_dir()/events.db — portable or ~/.local/share/nova/events.db)
  tts.py           edge-tts subprocess + pygame playback, priority queue
  twitch.py        Twitch IRC anonymous chat monitor → ChatLogPanel + TTS
  youtube.py       YouTube live chat anonymous monitor → ChatLogPanel + TTS
  overlay.py       individual .txt file writer for OBS/Streamlabs overlays (~/.config/nova/overlay/)
  ui/
    app.py         Textual App (NOVAApp), CSS layout, keybindings
    panels.py      all Widget subclasses
```

## Architecture
- Daemon threads: journal, status, TTS, EDSM, EDSM-dumps (`nova-edsm-dumps`), neutron (`nova-neutron`), screenshots (`nova-screenshots`), Spansh (`nova-spansh`, optional), twitch (optional), youtube (optional), overlay
- **Thread watchdog** (`__main__.py _spawn_guarded`): all daemon threads run inside a restart wrapper — if a thread raises an uncaught exception it restarts after 5 s. Log goes to `nova.watchdog` logger.
- **Thread heartbeats**: `state.journal_heartbeat` and `state.status_heartbeat` (float, unix time) are updated each loop iteration. FooterBar shows `⚠ journal/status thread stalled` when either is >60 s stale while `client_online`.
- `AppState` + `threading.RLock` — threads write, Textual reads via shallow copy
- Textual 250ms timer: `_snapshot()` → `update()` each panel
- Threads never call Textual APIs directly
- EDSM nightly dumps: background thread checks hourly, downloads if >24h old; streams gzip via urllib without buffering full files; stores in `edsm_systems` + `edsm_stations` SQLite tables
- Spansh carrier lookup: enabled via `carrier_lookup = true` in config; POST to `/api/stations/search`; results cached 300 s; min 3 s between calls
- Neutron planner: downloads `systems_neutron.json.gz` daily; stores ~50k stars in `neutron_stars` SQLite table; bounding-box spatial queries; greedy A* beam_width=20
- Screenshots: polls ED screenshot dir every 2 s; converts BMP→PNG via Pillow; renames to `YYYY-MM-DD-HH-MM_CMDR_SYSTEM_BODY.png`; moves to dest dir

## DB Resilience (db.py)
All write methods (`insert`, `save_bodies_batch`, `save_bio_scans`, `increment_stat`, `set_hull`, `set_config`) wrap their `executemany`/`execute`+`commit` in `try/except Exception: self._conn.rollback(); raise`. This prevents half-written transactions from leaving the DB in a corrupt state.

Bodies and stats are **kept indefinitely** — no age-based pruning. The `prune_events()` method exists but is not called automatically (events only, 180-day default).

## TTS Path Safety (tts.py)
- Pygame subprocess fallback: path passed as `repr(str(path))` (safe Python literal, handles quotes/backslashes)
- PowerShell MediaPlayer fallback: double-quotes escaped as `` `" `` (PowerShell backtick escape)

## Layout (app.py CSS)
```
top-row:    [PositionPanel 4fr] [ShipPanel 5fr] [RoutePanel 3fr]
middle-row: [left 4fr: BodiesPanel] [center 5fr: SituationalPanel] [right 3fr: EventLog 2fr / ChatLog 1fr]
footer:     FooterBar (1 row)
```

## Config (config_dir()/config.toml)

**Portable mode** (set via `NOVA_PORTABLE_ROOT` env var by launcher scripts): all paths resolve relative to the launcher script directory. `config_dir()` → `<root>/config`, `data_dir()` → `<root>/data`, `logs_dir()` → `<root>/logs`. On first portable run, existing `~/.config/nova/` and `events.db` are auto-migrated (non-destructive).

**System install** (no env var): `config_dir()` → `~/.config/nova/` (or `XDG_CONFIG_HOME/nova`), `data_dir()` → `~/.local/share/nova/` (or `XDG_DATA_HOME/nova`).

Config hot-reload: `__main__.py` uses `watchdog` to monitor `config.toml` and `voicelines/` dir; changes apply within ~2 s via `reload_config()` + `voicelines.reload_all()`.

Settings overlay: `s` key → `SettingsScreen` (app.py). All `Static` widgets in `compose()` use `markup=False` (Textual 8.x compat — `[en]` etc. would be parsed as Rich markup tags and stripped).

## Config keys (~/.config/nova/config.toml or config/config.toml in portable mode)
- `journal_dir` — override auto-detected journal path
- `twitch_channel` — Twitch channel name; leave empty/commented to disable Twitch
- `youtube_channel` — YouTube channel handle (e.g. `@yourchannel`); leave empty/commented to disable YouTube
- `tts_rate` — edge-tts rate (default: `+10%`)
- `tts_lang` — NOVA's voiceover language: `en`, `de`, `fr`, `it`, `es`, `pt`, `ru` (default: `en`)
- `tts_voice_<lang>` — voice per language code: `en`, `de`, `fr`, `it`, `es`, `pt`, `ru`
- `overlay_dir` — directory for individual stream overlay .txt files (default: `~/.config/nova/overlay/`)
- `default_volume` — TTS/audio volume at startup, 0–100 (default: 50)
- `notable_value_threshold` — minimum Cr value for Overview notable bodies list (default: 500000)
- `carrier_lookup` — enable Spansh API fleet carrier lookup for current system (default: false)
- `screenshot_dir` — override auto-detected ED screenshot source directory
- `screenshot_dest` — override destination directory (default: `~/Pictures/Elite Dangerous`)
- `situational_panels` — space-separated abbrevs defining visible panels and order (e.g. `OVR BIO MAP MIS ENG BGS COL ROU NTR WLT INV DKG STS`); empty = all panels in default order

Migration: if `~/.config/nova/config.toml` doesn't exist, old `~/.config/ed-monitor/config.toml` is copied.

## Voicelines System (voicelines.py)
- `pick(key, lang, **kwargs)` → render pipeline: includes → conditionals → `format_map(_SafeDict)`, falls back to `en`, returns `None` if missing
- Fragment keys (starting with `_`) are never spoken directly — `pick("_frag")` returns `None`
- Cache: `_CACHE: dict[str, dict]` per lang; invalidated by `reload(lang)` / `reload_all()` (called on file change)
- Built-in files: `ed_monitor/voicelines/{lang}.default.toml` (87 event keys, 3–5 variants each)
- User override path: `config_dir()/voicelines/{lang}.toml` — uses `add`/`replace` per-key semantics
  - `add = [...]` appends lines to the built-in pool
  - `replace = [...]` replaces built-in lines entirely (empty list = silence that event)
  - `replace = []` now correctly silences events (fixed in v1.32.4); syntax errors in user file → TTS alert + fallback to built-in
- Reference copies: `config_dir()/voicelines/default/{lang}.default.toml` — overwritten on every launch
- Hot-reload: `watchdog` monitors the voicelines dir; changes apply within ~2 s
- `_say(tts_q, key, priority, fallback, **kwargs)` in events.py: calls `pick()`, falls back to `fallback` string
- status.py `_q(key, fallback, pri, **kwargs)`: reads `_ev._TTS_LANG` + `_ev._LANG_VOICES` for correct voice
- Old-style user files (`{lang}.toml` with `lines = [...]`) are migrated to `backup/` on first run

### Template Engine (v1.35.0)
Three-step render pipeline inside `pick()`:
1. `_expand_includes(template, lines_map, kwargs, depth=0)` — expands `{include:_KeyName}` (explicit, supports hyphens) and `{_KeyName}` (shorthand, word chars only). Circular includes detected at depth > 5. Missing/non-`_` keys → `""` with warning.
2. `_evaluate_conditionals(template, kwargs)` — replaces `WHEN condition THEN "text";` blocks; `_eval_condition()` handles `AND`/`OR` with `{var}` substitution; `_eval_clause()` evaluates single clauses (IS TRUE/FALSE, ==, !=, <, >, <=, >=).
3. `template.format_map(_SafeDict(kwargs))` — `_SafeDict` returns `""` for missing keys instead of raising `KeyError`.

Key regex: `_INCLUDE_RE = re.compile(r'\{include:([\w-]+)\}|\{(_\w+)\}')` — group 1 explicit, group 2 shorthand; handler rejects non-`_` prefix keys.

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

Chat TTS format: "User {name} on YouTube says: {msg}" / "User {name} on Twitch says: {msg}"

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

## First Footfall (events.py + state.py)
- `WasFootfalled` in Scan event (Detailed): if explicitly `false`, sets `BodyInfo.first_footfall = True` immediately — no need to wait for Touchdown/Disembark
- `upsert_body()` preserves `first_footfall=True` across subsequent upserts (e.g. DSS result)
- Existing Touchdown/Disembark fallback logic remains for cases where Scan data is absent

## FSS Count (panels.py)
- Counts all bodies the player received a `Scan` journal event for (FSS, auto-scan, proximity scan)
- Formula: `sum(1 for b in s.bodies if b.fss_scanned)` — `fss_scanned=True` set for every Scan event
- `fss_scanned` is NOT set for EDSM-injected bodies (those come from network, not journal)

## FSS System Scan Complete (events.py)
- `FSSDiscoveryScan` (honk) sets `state.fss_honk_pending = True`
- `FSSAllBodiesFound` only fires log+voice when `fss_honk_pending` is True; always resets the flag
- Auto-scan completions (game fires `FSSAllBodiesFound` silently) are suppressed
- `fss_honk_pending` resets on FSDJump/CarrierJump

## FuelScoop Logging (events.py)
- Only emits a LogEvent when tank is full: `"Fuel full (Xt)."`
- Intermediate scoop ticks return None (silent in event log)

## Body Value Display (state.py `estimate_value_base` + `estimate_value_mapped`)
Functions moved from panels.py to state.py in v1.33.8 so events.py can import without circular dependency. panels.py re-imports them as `_estimated_value` / `_body_value` aliases.

- `estimate_value_base(b)`: when `b.mass_em > 0` uses exact Frontier formula `max(k*(1+Q*M^0.2), 500) + terraformable_bonus`; else uses `_BODY_EST_VALUES` table. EDSM values are **never used**.
- `estimate_value_mapped(b)`: full projected or actual DSS payout — applies first-mapped (×3.6996), first-disc+mapped (×8.0956), efficiency bonus (×1.25), first-footfall (×1.30). FSS'd unmapped always assumes efficiency bonus (×1.25) = maximum possible payout.
- Terraformable bonus: additive per `_SPECIFIC_BONUS` (HMC=100677, WW=116295, ELW=116295); other types use `BASIC_BONUS_TERRAFORMABLE=93328`
- Color tiers (`_body_value_color`): GOLD = first disc+map, AMBER = first map, white = no bonus, AMBER/DIM = non-FSS'd
- `_body_vars()` in events.py: `{value}/{value_raw}` use formula fallback when `b.value == 0`; `{value_mapped}/{value_mapped_raw}` always use `estimate_value_mapped()`
- Used in Bodies panel value column, Overview notable bodies table, and notable-body threshold check

## Bio Distance (status.py `_check_bio_distance`)
- Returns early if lat/lon is None (preserves last known distances)
- Uses `sample_lats`/`sample_lons` lists on BioScan (falls back to `last_lat/last_lon`)
- Always runs distance/bearing calculation (even while flying in main ship)
- TTS fires only when `on_surface` (landed or in SRV or on foot) and `best_dist >= sc.min_dist` and not already alerted
- `alerted` flag is only reset while on surface — prevents re-arming while ascending
- Per-sample bearings stored in `sc.sample_bearings` (list); point TOWARD each sample
- Bio panel layout: `BAR DIST ARROW1 ARROW2` (one arrow per recorded sample)

## Mass Lock TTS (status.py)
- Gated on `prev_in_main_ship and new_in_main_ship and not state.supercruise and not state.orbital_cruise`
- Suppresses announce when boarding/exiting ship, in supercruise, or in glide (orbital cruise) mode

## Startup / Shutdown Voice Lines
- On launch: "NOVA active." (suppresses all COVAS callouts from the first Status.json read)
- On `Shutdown` event: "Systems powering down. Farewell, Commander."
- `client_shutdown_pending` flag (AppState): set True by `Shutdown`, cleared by `LoadGame`/`Location`. Prevents `status.py` from restoring `client_online=True` while Status.json is still recent (race condition fix for docked/on-foot shutdown scenarios).

## SituationalPanel Modes
Default order: auto → overview → bio → galaxy → missions → engineers → bgs → colonisation → route → neutron → wealth → inventory → docking → stats → auto
Auto-resolve priority (highest first):
1. offline → stats
2. **in_hyperspace + route_hops > 0 → route** (shows remaining route while jumping)
3. docking_granted → docking
4. incomplete bio_scans → bio
5. DSS'd body with bio_genuses → bio
6. colonisation active in current system → colonisation
7. missions + not supercruise → missions
8. **route_hops > 0 → route** (auto-switch when route set and no higher-priority task active)
9. → overview (default)

## in_hyperspace Flag (state.py + events.py)
- `state.in_hyperspace = True` set by `StartJump` (JumpType == "Hyperspace")
- `state.in_hyperspace = False` cleared by `FSDJump | CarrierJump`
- Used by `_auto_resolve` to show Route panel during the jump animation

## Position Panel Layout (panels.py PositionPanel, formerly SystemPanel — renamed v1.33.7)
Two-column table (left: exploration data, right: BGS/human data). When `nearest_body` is set in state (approaching a body), a body detail section appears below the table showing: type, gravity (red ≥3G / yellow ≥1.5G), radius, temp, atmosphere, bio/geo counts, volcanism, terraform flag. Position footer: `At <body>     Pos <lat, lon>     Alt <n m>` — "At <body>" only shown when no body detail section is present. Panel `update()` key includes `nearest_body + rounded lat/lon/alt` for movement-triggered refreshes.
- Stars always count as FSS-done in the `fss_done` counter

## Overview Sections (panels.py `_render_overview`)
Order: system diagram → notable bodies → NEAREST INHABITED SYSTEM → NEAREST FLEET CARRIER → system summary / PP / BGS

**NEAREST INHABITED SYSTEM** (only when `population == 0`):
- Row 1: `[System name]      [X ly]      [~N jumps]`  — jumps from `jump_range_last or jump_range`
- Row 2: `[Allegiance]      [N stn]      [Service1, Service2, ...]`

**NEAREST FLEET CARRIER** (when `carrier_lookup` enabled and carrier found):
- Row 1: `[Carrier name]  (orange, bold)   [dist_ls or ly]      [~N jumps]`
- Row 2: `[Last seen]      [Services ...]`

## BGS Log Cap (events.py)
- `_bgs_add()` caps at `_BGS_LOG_CAP = 50` faction×activity pairs per system per day
- New entries beyond the cap are silently discarded (existing counts still increment)
Tab/Shift+Tab cycle through _visible_modes (filtered/ordered by situational_panels config or default _MODES)
`a` key toggles `_auto_locked` — freezes current resolved view without changing _mode
Mode abbrevs: ***=auto, OVR=overview, BIO=bio, MAP=galaxy, MIS=missions, ENG=engineers, BGS=bgs, COL=colonisation, ROU=route, NTR=neutron, WLT=wealth, INV=inventory, DKG=docking, STS=stats
Active/resolved mode shows full name in border title (e.g. BIOLOGICAL); others show abbrev
_ODY_ENGINEERS: frozenset of 9 Odyssey engineers shown with max_rank=1 (not 5)

## Bio Panel Pre-scan Display
When a body is DSS'd with biological signals (`bio_genuses` set on BodyInfo), the Bio panel shows genus names + value ranges (from `_BIO_GENUS_VALUE_RANGE`) and total estimated value before any sample is taken. Auto-switches to bio mode when approaching/landing on such a body.

## RoutePanel Context
1. Docked: shows station services (from `state.station_*`, populated by Docked event)
2. ApproachBody set: shows body info
3. Otherwise: shows nav route + stations at next waypoint (from EDSM dump data, up to 3 closest stations with service icons [M=market S=shipyard O=outfitting R=refuel])

## EDSM Dump Lookups (journal.py)
`_update_dump_lookups(state, lock, db)` is called:
- After FSDJump / CarrierJump / Location events
- After NavRoute / NavRouteClear events
- Once after `_process_backlog()` on startup

It updates:
- `state.system_power` / `state.system_power_state` — from `edsm_systems` by current system name
- `state.nearest_populated_name/dist/allegiance` — only when `state.population == 0` (uninhabited)
- `state.route_list_edsm` — dict name→{x,y,z,population,allegiance} for all systems in `route_list`
- `state.route_next_stations` — list of station dicts for the next nav route waypoint

## EDSM DB Tables
- `edsm_systems`: id64 PK, name, x/y/z, allegiance, government, economy, population, security, power, power_state + idx on name
- `edsm_stations`: id PK, name, system_id64, system_name, type, dist_ls, allegiance, government, economy, has_market, has_shipyard, has_outfitting, other_services + idx on system_name
- Powerplay upsert: `ON CONFLICT(id64) DO UPDATE SET power=..., power_state=... WHERE excluded.power != ''` (preserves population data from systemsPopulated import)

## Neutron DB Tables
- `neutron_stars`: id INTEGER PK, name TEXT, x/y/z REAL + separate indexes on x, y, z (bounding-box queries)
- `neutron_meta`: key TEXT PK, value TEXT — stores `last_updated` timestamp for daily refresh logic

## AppState EDSM Fields
```python
system_power:                 str   = ""      # Power Play controlling power
system_power_state:           str   = ""      # Exploited / Control / Fortified / etc.
nearest_populated_name:       str   = ""      # Name of nearest inhabited system
nearest_populated_dist:       float = 0.0     # Distance in ly
nearest_populated_allegiance: str   = ""      # Allegiance of nearest inhabited system
nearest_populated_stations:   list  = []      # list of station dicts for nearest inhabited system
route_next_stations:          list  = []      # list of station dicts for next waypoint
carriers_current_system:      list  = []      # list of carrier dicts from Spansh API
```

## AppState New Fields (v1.19.0)
```python
high_g_extreme:       bool  = False  # True while approaching ≥3G body (not landed/SRV)
credits:              int   = 0      # current credit balance
stored_ships:         list  = []     # StoredShips event data
suit_loadout:         dict  = {}     # SuitLoadout event data
backpack:             dict  = {}     # Backpack/BackpackChange event data
jump_range:           float = 0.0    # max jump range from Loadout event
neutron_route:        list  = []     # list of dicts: {system, dist, neutron}
neutron_route_to:     str   = ""     # destination system name
neutron_route_status: str   = ""     # "plotting" / "done" / error message
```

## AppState Pips Fields
```python
pips_sys: float = 4.0   # SYS pips (0.0–4.0, half-pip = 0.5 step; only valid in_main_ship)
pips_eng: float = 2.0   # ENG pips
pips_wep: float = 2.0   # WEP pips
```
Status.json `Pips` field: `[SYS, ENG, WEP]` array, each int 0–8 (game internal); divide by 2 to get displayed pip count.

## Spansh API (spansh.py)
- Endpoint: `POST https://spansh.co.uk/api/stations/search`
- Body: `{"system_name": "...", "type": "Drake-Class Carrier", "size": 10}`
- Cache TTL: 300 s per system; min delay 3 s between requests
- Spawned only when `cfg.carrier_lookup = True`
- Queue message: `("fetch_carriers", system_name)`
- Clears `state.carriers_current_system = []` on system change before fetch completes

## SRV TTS Callouts (status.py)
- Ship → SRV: "SRV deployed" (`SRV_Deployed`)
- On foot → SRV (boarding already-deployed SRV): "SRV boarded" (`SRV_Boarded`)
- SRV → ship (recalled): "SRV secured" (`SRV_Secured`)
- SRV → on foot (exiting, SRV stays on surface): "SRV exited" (`SRV_Exited`)
- Lights TTS suppressed when SRV state also changed in the same tick (vehicle switch artefact)
- ShipPanel border title shows "Glide" (not "Orbital Cruise") when `orbital_cruise` is True

## High-G Warning (events.py + app.py)
- `ApproachBody`: reads `surface_gravity` (m/s²) from `BodyInfo`, divides by 9.80665 to get G
- ≥1.5 G: single TTS warning (`HighGWarning`), `state.high_g_alerted = False` reset on each approach
- ≥3.0 G: three TTS warnings at 0/10/20 s (`HighGExtreme`), sets `state.high_g_extreme = True`, orange border + dark background flash in CSS
- `state.high_g_extreme` cleared by `LeaveBody` and `SupercruiseEntry`; flash also gated on `not snap.landed and not snap.in_srv`
- CSS class `high-g-flash` on Screen: orange borders `rgb(220,100,0)`, background `rgb(50,20,0)`; alternates every 1 s via `int(time.time()) % 2 == 0`

## Neutron Planner (neutron.py)
- Download: `https://downloads.spansh.co.uk/systems_neutron.json.gz` streamed via urllib, stored in `neutron_stars` SQLite table
- `spawn(state, lock, db) -> queue.Queue` — starts `nova-neutron` daemon thread, returns queue
- Worker handles `("plot", target_name)` messages; sets `neutron_route_status = "plotting"` then populates `neutron_route`
- `_plan_route(db, origin_xyz, target_xyz, jump_range)`: greedy A* with beam_width=20, max_jumps=2000; bounding-box SQLite query per step
- Target coord lookup: tries `edsm_systems` first, then `neutron_stars`
- `NeutronInputScreen` (app.py): `n` key when in neutron mode opens Input overlay; Enter puts `("plot", dest)` on queue
- Voicelines: no new TTS events — status shown in panel text

## Screenshot Watcher (screenshots.py)
- `monitor(state, lock, cfg)` main function — runs as `nova-screenshots` daemon
- Auto-detects source dir: Proton default Steam → Proton Flatpak Steam → native Windows/Linux paths
- Polls every 2 s; tracks seen files by `(path, mtime)` to avoid reprocessing
- BMP files: converted to PNG via `PIL.Image` (wrapped in `ImportError` try/except for graceful fallback)
- Rename pattern: `YYYY-MM-DD-HH-MM_{cmdr}_{system}_{body}.png` (spaces → underscores)
- Moves to `screenshot_dest` (default `~/Pictures/Elite Dangerous`), creates dir if needed

## EngineerInfo Dataclass (state.py)
```python
@dataclass
class EngineerInfo:
    name:          str
    rank:          int   = 0
    rank_progress: float = 0.0
    progress:      str   = ""   # "Known" / "Invited" / "Acquainted" / ""
    engineer_id:   int   = 0
```
- Replaces old `(rank, progress)` tuples in `state.engineers` dict
- `EngineerProgress` handler checks `isinstance(existing, EngineerInfo)` before update
- `_ENGINEER_STATIC` in panels.py: ~36 engineers keyed by name → `{specialty, system}`

## GitHub Release Notes
- Release notes should contain the **changelog** (what changed, what was fixed), NOT installation instructions.
- Installation instructions live in the README only.

## Known Quirks
- BioScan `first_footfall` detected via `Touchdown` or `Disembark` (Apex/Frontline fallback); matched by body name and body ID
- First footfall: fires only on `Disembark` (not Touchdown); deduplicated per body via `state.first_footfall_bodies` (set, persisted across restarts via `sc.first_footfall` in bio_scans DB)
- Shield display: binary UP/DOWN only — ShieldHealth not present in Status.json
- Barycentre bodies (AB 4 etc.): shown unindented, sorted after single-star children in Bodies panel and Overview diagram
- EDSM fetch is GET-only, no API key required
- `pygame.mixer.init()` called per-track (safe/idempotent)
- ChatLogPanel filters `EventCategory.Chat` only
- Bodies table alternating rows: `row_styles=["", "on rgb(38,38,38)"]`
- FSS count in System panel: counts all bodies with planet_class or star_type (includes auto-scanned, excludes belt clusters)
- Stats (persistent): written to `stats` SQLite table; only live events counted, not journal replay
- Bodies and stats data kept indefinitely — no automatic pruning
