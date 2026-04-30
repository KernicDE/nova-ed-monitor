# NOVA — Project Reference

## Run
```bash
cd /home/kernic/Development/nova-ed-monitor
python -m ed_monitor
```

## Architecture
- Daemon threads: journal, status, TTS, EDSM, EDSM-dumps, neutron, screenshots, Spansh (optional), twitch (optional), youtube (optional), overlay
- **Thread watchdog** (`__main__.py _spawn_guarded`): daemon threads restart after 5 s on uncaught exception. Log → `nova.watchdog`.
- **Thread heartbeats**: `state.journal_heartbeat` / `state.status_heartbeat` (unix time). FooterBar shows stall warning when >60 s stale while `client_online`.
- `AppState` + `threading.RLock` — threads write, Textual reads via shallow copy at 2 Hz
- Threads never call Textual APIs directly

## DB Resilience (db.py)
All write methods wrap in `try/except Exception: rollback(); raise`. Migrations run inside `with self._conn:` (atomic); leave sentinel unwritten on failure so next launch retries.

`Database.prune_events(days)` wired to `cfg.prune_events_days` at startup (default 0 = disabled).

## Config (config_dir()/config.toml)

**Portable mode** (`NOVA_PORTABLE_ROOT` env var): `config_dir()` → `<root>/config`, `data_dir()` → `<root>/data`, `logs_dir()` → `<root>/logs`. First portable run auto-migrates `~/.config/nova/` and `events.db`.

**System install**: `config_dir()` → `~/.config/nova/` (or `XDG_CONFIG_HOME/nova`), `data_dir()` → `~/.local/share/nova/`.

Config hot-reload: `watchdog` monitors `config.toml` and `voicelines/` dir; changes apply ~2 s via `reload_config()` + `voicelines.reload_all()`.

Settings overlay: `s` key → `SettingsScreen`. All `Static` widgets use `markup=False` (Textual 8.x compat).

## Config keys
- `journal_dir` — override auto-detected journal path
- `twitch_channel` / `youtube_channel` — enable chat monitors (empty = disabled)
- `tts_rate` — edge-tts rate (default: `+10%`)
- `tts_lang` — voiceover language: `en`, `de`, `fr`, `it`, `es`, `pt`, `ru` (default: `en`)
- `tts_voice_<lang>` — voice override per language code
- `overlay_dir` — stream overlay `.txt` files dir (default: `~/.config/nova/overlay/`)
- `default_volume` — 0–100 (default: 50)
- `notable_value_threshold` — min Cr for Overview notable bodies AND `Scan_Notable` TTS trigger (default: 500000)
- `carrier_lookup` — enable Spansh fleet carrier lookup (default: false)
- `screenshot_dir` / `screenshot_dest` — override screenshot source/dest dirs
- `situational_panels` — space-separated abbrevs for panel order (e.g. `OVR BIO MAP MIS ENG BGS COL ROU NTR AST STS`). Legacy aliases still accepted: `WLT`→`AST`, `INV`→`AST`, `DKG`→`OVR`.
- `prune_events_days` — delete event rows older than N days at startup; 0 = disabled

## Voicelines System (voicelines.py)
- `pick(key, lang, **kwargs)` → render pipeline: includes → conditionals → `format_map(_SafeDict)`, falls back to `en`, returns `None` if missing
- Fragment keys (starting with `_`) never spoken directly
- User override: `config_dir()/voicelines/{lang}.toml` — `add`/`replace` per-key semantics; `replace = []` silences an event
- Reference copies: `config_dir()/voicelines/default/{lang}.default.toml` — overwritten on every launch
- `_say(tts_q, key, priority, fallback, **kwargs)` in events.py: calls `pick()`, falls back to `fallback` string
- Old-style user files (`lines = [...]`) auto-migrated to `backup/`

### Voiceline Variable Reference

**`_system_vars(state)`** — available in all events:
| Variable | Content |
|---|---|
| `{system}` | Current star system name |
| `{star_class}` / `{primary_star_class}` | Primary star class |
| `{is_star_scoopable}` | `True`/`False` (bool) — primary star scoopable |
| `{star_scoopable}` | deprecated alias for `{is_star_scoopable}` |
| `{allegiance}`, `{economy}`, `{security}`, `{government}`, `{faction}` | System metadata |
| `{population}`, `{population_raw}` | Population (spoken / integer string) |
| `{nearest_body_*}` | All `_body_vars()` fields prefixed |

**`_ship_vars(state)`** — available in all events:
| Variable | Content |
|---|---|
| `{commander}`, `{ship}`, `{ship_type}`, `{ship_name}`, `{ship_ident}` | Identity |
| `{hull}`, `{hull_raw}` | Hull health ("75 percent" / "75") |
| `{fuel}`, `{fuel_raw}`, `{fuel_max_raw}` | Fuel status |
| `{jump_range}`, `{jump_range_raw}` | Max jump range |

**`_target_vars(state)`** — merged into all `_say()` calls that use `_ship_vars`:
| Variable | Content |
|---|---|
| `{target_type}` | "ship" / "body" / "" |
| `{target_ship_*}` | type, pilot, rank, faction, legal, shield, hull, bounty (staged scan) |
| `{target_body}` | Nav destination name |
| `{target_body_*}` | All `_body_vars()` fields for destination body |

**`_body_vars(b)`** — body-specific events and `nearest_body_*` / `target_body_*` prefixes:
| Variable | Content |
|---|---|
| `{body_type}` | Planet class string |
| `{star_type}` | Star type (empty for planets) |
| `{is_scoopable}` | `True`/`False` (bool) — star scoopable |
| `{is_terraformable}` | `True`/`False` (bool) — body terraformable |
| `{scoopable}` | deprecated alias for `{is_scoopable}` |
| `{terra}` | deprecated alias for `{is_terraformable}` |
| `{atmosphere}`, `{volcanism}` | Atmosphere/volcanism strings |
| `{gravity}`, `{gravity_raw}` | Surface gravity ("1.23 G" / "1.23") |
| `{temp}`, `{temp_raw}` | Surface temp ("300 Kelvin" / "300") |
| `{radius}`, `{radius_raw}` | Radius ("6000 kilometres" / "6000") |
| `{mass}`, `{mass_raw}` | Mass ("0.85 Earth masses" / "0.85") |
| `{dist_ls}`, `{dist_ls_raw}` | Distance from arrival star |
| `{value}`, `{value_raw}` | Mapped value projection (`_ev_mapped`) for FSS'd bodies — matches panel display; EDSM value for non-FSS'd |
| `{value_mapped}`, `{value_mapped_raw}` | Projected or actual DSS payout (all bonuses) |
| `{landable}` | "Landable" or "" |
| `{bio_count}`, `{geo_count}` | Signal counts |
| `{first_disc}` | "Undiscovered" or "" |
| `{first_footfall_flag}` | "First footfall" or "" |
| `{has_rings}`, `{ring_count}` | "Ringed" or "" / number of rings |
| `{tidal_lock}` | "Tidal lock" or "" |
| `{orbital_period}`, `{orbital_period_raw}`, `{orbital_period_raw_d/h/m}` | Orbital period |
| `{semi_major_axis}`, `{semi_major_axis_raw}`, `{semi_major_axis_au_raw}` | Semi-major axis |
| `{eccentricity}`, `{orbital_inclination}`, `{orbital_inclination_raw}` | Orbital shape |

**Boolean variables** (`{is_scoopable}`, `{is_terraformable}`, `{is_star_scoopable}`) return Python `bool`. In `WHEN` conditions they are substituted as `"TRUE"`/`"FALSE"` — use `IS TRUE`/`IS FALSE` (not `== "true"`). Deprecated aliases (`{scoopable}`, `{terra}`, `{star_scoopable}`) still work but will be removed in a future version. Other flag variables (`{landable}`, `{first_disc}` etc.) are `""` when absent / non-empty when present.

### Template Engine
Three-step render pipeline inside `pick()`:
1. `_expand_includes` — `{include:_KeyName}` (explicit) and `{_KeyName}` (shorthand). Circular includes → depth > 5 error.
2. `_evaluate_conditionals` — `WHEN condition THEN "text";` blocks. Operators: `IS TRUE/FALSE`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`.
3. `format_map(_SafeDict)` — unknown keys → `""`.

## TTS Language Detection (events.py)
| Code | Language   | Default Voice          |
|------|-----------|------------------------|
| en   | English   | en-GB-SoniaNeural      |
| de   | German    | de-DE-KatjaNeural      |
| fr   | French    | fr-FR-DeniseNeural     |
| it   | Italian   | it-IT-ElsaNeural       |
| es   | Spanish   | es-ES-ElviraNeural     |
| pt   | Portuguese| pt-PT-RaquelNeural     |
| ru   | Russian   | ru-RU-SvetlanaNeural   |

Detection priority: Cyrillic → ñ/¿/¡ → ã/õ → German umlauts → word list scoring → EN fallback.

## Status.json Flags (status.py)
| Constant | Bit | Meaning |
|---|---|---|
| FLAG_DOCKED | 1<<0 | Docked |
| FLAG_LANDED | 1<<1 | Landed |
| FLAG_SHIELDS_UP | 1<<3 | Shields up |
| FLAG_SUPERCRUISE | 1<<4 | In supercruise |
| FLAG_FA_OFF | 1<<5 | Flight assist off |
| FLAG_HARDPOINTS | 1<<6 | Hardpoints deployed |
| **FLAG_MASS_LOCKED** | **1<<16** | **FSD mass locked (NOT 1<<7 = In Wing)** |
| FLAG_IN_MAIN_SHIP | 1<<24 | Player in main ship |
| FLAG_IN_SRV | 1<<26 | Player in SRV |
| FLAG_ANALYSIS_MODE | 1<<27 | Analysis mode |

## Key Event Handling Notes

**ScanOrganic**: `Log` → samples=1; `Sample` → `min(samples+1, 2)` (capped); `Analyse` → samples=3, complete=True.

**First Footfall**: `WasFootfalled=false` in Scan event sets `BodyInfo.first_footfall = True` immediately. `upsert_body()` preserves `first_footfall=True` across subsequent upserts.

**FSS honk guard**: `FSSDiscoveryScan` sets `fss_honk_pending=True`; `FSSAllBodiesFound` only fires voice when that flag is True. Prevents silent auto-scan completions from triggering voice.

**FuelScoop**: LogEvent only when tank is full; intermediate ticks are silent.

**High-G timers**: `ApproachBody ≥ 3G` schedules two `threading.Timer` objects (at 10 s and 20 s). Tracked on `state.high_g_timers`. Cancelled by `LeaveBody`, `SupercruiseEntry`, `FSDJump`/`CarrierJump`, `Shutdown`, or later `ApproachBody` on different body.

**Mass Lock TTS**: Gated on `prev_in_main_ship and new_in_main_ship and not supercruise and not orbital_cruise`.

**Startup/Shutdown**: `client_shutdown_pending` set True by `Shutdown`, cleared by `LoadGame`/`Location` — prevents `status.py` restoring `client_online=True` while Status.json is still recent.

**`in_hyperspace`**: `True` on `StartJump` (JumpType==Hyperspace), `False` on `FSDJump`/`CarrierJump`. `StartJump` also calls `_trigger(state, "route")` to switch the situational panel.

**BGS log cap**: `_bgs_add()` caps at `_BGS_LOG_CAP = 50` faction×activity pairs per system per day. New entries beyond cap discarded.

## Body Value (state.py)
- `estimate_value_base(b)`: exact Frontier formula `max(k*(1+Q*M^0.2), 500) + terraform_bonus` when `mass_em > 0`; else `_BODY_EST_VALUES` table. EDSM values **never used**.
- `estimate_value_mapped(b)`: full DSS payout. FSS projected: first-disc+mapped → ×8.0956×1.25; first-mapped-only → ×3.6996×1.25; no-bonus → ×3.3333×1.25. First-footfall adds 30%.
- `{value}/{value_raw}` use formula for FSS'd bodies (same base as `{value_mapped}`); EDSM for non-FSS'd.
- Color tiers: GOLD = first disc+map, AMBER = first map, white = no bonus.

## Bio Distance (status.py `_check_bio_distance`)
- Returns early if lat/lon is None (preserves last known distances)
- TTS only when `on_surface` and `best_dist >= min_dist` and not already alerted
- `alerted` only resets while on surface — prevents re-arming while ascending
- Per-sample bearings in `sc.sample_bearings` (point TOWARD each sample)

## SituationalPanel Modes
Panel is in `ed_monitor/ui/situational/` subpackage. `SituationalPanel` in `panel.py`; individual renderers in `overview.py`, `bio.py`, `engineers.py`, `docking.py`, `assets.py`, `bgs.py`, `colonisation.py`, `missions.py`, `maps.py`, `neutron.py`, `route.py`, `stats.py`.

Auto-switching is event-driven via `_trigger(state, panel)` in `events.py` (not a priority resolver). Triggers: FSDJump/CarrierJump→overview, StartJump→route, NavRoute set→route, SupercruiseExit→overview, DockingGranted→overview, SAAScanComplete/ScanOrganic→bio, MissionAccepted/Completed→missions, Shutdown→stats, ColonisationContribution→colonisation. Deduplication: same panel as last auto-switch is skipped; each trigger fires at most once (version counter).

Keys: `←`/`→` cycle visible modes; `a` toggles auto-switching; Tab/Shift+Tab cycle focused panels (not modes).
Abbrevs: `***`=auto, `OVR`, `BIO`, `MAP`, `MIS`, `ENG`, `BGS`, `COL`, `ROU`, `NTR`, `AST`, `STS`. Legacy: `WLT`→`AST`, `INV`→`AST`, `DKG`→`OVR`.

## Overview Sections (`situational/overview.py` `_render_overview`)
Order: system diagram → notable bodies → NEAREST INHABITED SYSTEM (when pop=0) → NEAREST FLEET CARRIER (when carrier_lookup) → system summary/PP/BGS.

## Bio Panel
Pre-scan (DSS'd body with `bio_genuses`): shows genus names, variant, value ranges, total estimated value. Auto-switches to bio mode on approach/landing.

Bio prediction: `predict_bio_species(planet_class, atmosphere, temp, gravity, volcanism, star_type, dist_ls)` → species names. `bio_variant(star_type)` → variant color.

**Prediction approach (v2.4.0+):** Eliminative — first gate is `"thin" not in atmosphere → []` for atmosphere-requiring genera. No-atmosphere genera (Amphora Plant, Brain Trees, Crystalline Shard, Sinuous Tubers) have their own gates (volcanism, star type, temperature, system context). Bark Mounds not predicted (no known rules). Electricae Radialem not predicted (nebula context unavailable). Species names authoritative from `_BIO_SPECIES_VALUES` (differ from EDXD in several cases: Erigia not Fera, Setulus not Setisis, Speculum not Speculumi, Upsilon not Upupam). `predict_bio_species(planet_class, atmosphere, temp, gravity, volcanism, star_type, dist_ls, **system_flags)` — system flags: `system_has_elw`, `system_has_gg_wbl`, `system_has_life`, `system_is_nebula`.

## RoutePanel Context
1. Docked → station services  2. ApproachBody set → body info  3. Otherwise → nav route + next-waypoint stations (EDSM dump, up to 3, icons: M/S/O/R)

## EDSM Dump Lookups (journal.py)
`_update_dump_lookups()` called after FSDJump/CarrierJump/Location, NavRoute/NavRouteClear, and after startup backlog. Updates: `system_power`, `system_power_state`, `nearest_populated_*` (uninhabited only), `route_list_edsm`, `route_next_stations`.

## Known Quirks
- First footfall fires only on `Disembark` (not Touchdown); deduplicated via `state.first_footfall_bodies`
- Shield display: binary UP/DOWN only — ShieldHealth not in Status.json
- Barycentre bodies (AB 4 etc.): shown unindented, sorted after single-star children
- EDSM fetch GET-only, no API key required
- `pygame.mixer.init()` called per-track (safe/idempotent)
- Stats: only live events counted, not journal replay
- Bodies and stats kept indefinitely — no automatic pruning
- `_ODY_ENGINEERS`: frozenset of 9 Odyssey engineers shown with max_rank=1 (not 5)
