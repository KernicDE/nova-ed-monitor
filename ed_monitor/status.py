from __future__ import annotations

import json
import logging
import math
import os
import queue
import threading
import time
from pathlib import Path

from .state import AppState, _DEFAULT_BODY_RADIUS_M
from .tts import TtsMsg, _audio_logger

_log = logging.getLogger("nova.status")
from . import voicelines as _vl
from . import events as _ev

_status_dir_changed: threading.Event = threading.Event()
_status_watchdog_active: bool = False

_STATUS_FILES = frozenset({"Status.json", "Cargo.json", "Materials.json"})


def _start_watchdog_status(journal_dir: Path) -> None:
    global _status_watchdog_active
    try:
        from watchdog.observers import Observer           # type: ignore[import]
        from watchdog.events import FileSystemEventHandler  # type: ignore[import]

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:         # type: ignore[override]
                if not event.is_directory and os.path.basename(event.src_path) in _STATUS_FILES:
                    _status_dir_changed.set()
            def on_created(self, event) -> None:          # type: ignore[override]
                if not event.is_directory and os.path.basename(event.src_path) in _STATUS_FILES:
                    _status_dir_changed.set()

        obs = Observer()
        obs.schedule(_Handler(), str(journal_dir), recursive=False)
        obs.daemon = True
        obs.start()
        _status_watchdog_active = True
        _log.info("Status watching: inotify/watchdog active (zero-CPU idle)")
    except Exception as exc:
        _log.warning(f"Status watching: watchdog failed ({exc}) — falling back to polling")


# Status.json flag bits
# Flags2 bits (Odyssey / Horizons 4.0+)
FLAG2_GLIDE       = 1 << 12  # GlideMode = orbital cruise
FLAG2_LOW_OXYGEN  = 1 << 6   # LowOxygen warning
FLAG2_LOW_HEALTH  = 1 << 7   # LowHealth warning (suit)
FLAG2_COLD        = 1 << 8   # Cold environment
FLAG2_HOT         = 1 << 9   # Hot environment

FLAG_DOCKED         = 1 << 0
FLAG_LANDED         = 1 << 1
FLAG_LANDING_GEAR   = 1 << 2
FLAG_SHIELDS_UP     = 1 << 3
FLAG_SUPERCRUISE    = 1 << 4
FLAG_FA_OFF         = 1 << 5
FLAG_HARDPOINTS     = 1 << 6
FLAG_SRV_HANDBRAKE        = 1 << 12  # SRV handbrake engaged
FLAG_SRV_TURRET_VIEW      = 1 << 13  # SRV using turret view
FLAG_SRV_TURRET_RETRACTED = 1 << 14  # SRV turret retracted
FLAG_SRV_DRIVE_ASSIST     = 1 << 15  # SRV drive assist enabled
FLAG_MASS_LOCKED          = 1 << 16  # FSD Mass Locked (bit 7 is "In Wing")
FLAG_IN_MAIN_SHIP   = 1 << 24  # Player is in the main ship (not on foot, not in SRV)
FLAG_LIGHTS         = 1 << 8
FLAG_CARGO_SCOOP    = 1 << 9
FLAG_SILENT_RUNNING = 1 << 10
FLAG_SCOOPING       = 1 << 11
FLAG_LOW_FUEL       = 1 << 19
FLAG_OVERHEATING    = 1 << 20
FLAG_IN_SRV         = 1 << 26
FLAG_ANALYSIS_MODE  = 1 << 27
FLAG_NIGHT_VISION   = 1 << 28


def monitor(
    state:       AppState,
    lock:        threading.RLock,
    journal_dir: Path,
    tts_q:       queue.Queue,
) -> None:
    status_path  = journal_dir / "Status.json"
    cargo_path   = journal_dir / "Cargo.json"
    mats_path    = journal_dir / "Materials.json"
    last_status  = 0.0
    last_cargo   = 0.0
    last_mats    = 0.0
    _on_surface_cache: bool = False
    _has_active_cache: bool = False

    _start_watchdog_status(journal_dir)

    while True:
        try:
            mtime = os.stat(status_path).st_mtime
            age = time.time() - mtime
            is_recent = age < 300  # 5 minutes

            if mtime != last_status:
                _log.debug(f"Status.json changed (age={age:.0f}s)")
                _apply_status(status_path, state, lock, tts_q, last_status == 0.0)
                last_status = mtime
            else:
                # Status.json hasn't changed but we still want bio distance checks
                # to run at full poll rate (0.2 s) when the player is on a surface,
                # so zone-entry/exit warnings fire promptly without waiting for the
                # next Status.json write (~1 s in-game).
                # Reuse the surface/bio state cached at the end of the previous tick
                # — Status.json is unchanged so state hasn't changed either.
                if _on_surface_cache and _has_active_cache:
                    with lock:
                        _check_bio_distance(state, tts_q)

            if is_recent:
                # Game is active — restore online state if any ship/activity flags are set.
                # Skip if Shutdown was already detected in the journal.
                with lock:
                    active = (state.in_main_ship or state.in_srv or
                              state.supercruise or state.docked or state.landed)
                    if active and not state.client_shutdown_pending:
                        state.client_online = True
            else:
                with lock:
                    state.client_online = False
        except OSError:
            # Status.json not found - ensure we're in offline state
            with lock:
                state.in_main_ship = False
                state.in_srv = False
                state.docked = False
                state.landed = False
                state.supercruise = False
                state.analysis_mode = False
                state.client_online = False
            pass

        # Check cargo and materials on every wakeup (mtime-gated, no re-read unless changed)
        try:
            mtime = os.stat(cargo_path).st_mtime
            if mtime != last_cargo:
                last_cargo = mtime
                _apply_cargo(cargo_path, state, lock)
        except OSError:
            pass
        try:
            mtime = os.stat(mats_path).st_mtime
            if mtime != last_mats:
                last_mats = mtime
                _apply_materials(mats_path, state, lock)
        except OSError:
            pass

        with lock:
            state.status_heartbeat = time.time()
            _on_surface_cache = (state.landed or state.in_srv or
                                 (not state.in_main_ship and not state.in_srv))
            _has_active_cache = any(
                not sc.complete and sc.samples > 0
                for sc in state.bio_scans
            )

        if _status_watchdog_active:
            need_fast = _on_surface_cache and _has_active_cache
            _status_dir_changed.wait(timeout=0.2 if need_fast else 5.0)
            _status_dir_changed.clear()
        else:
            time.sleep(0.2)


def _apply_status(
    path:  Path,
    state: AppState,
    lock:  threading.RLock,
    tts_q: queue.Queue,
    first_run: bool = False,
) -> None:
    try:
        text = path.read_text(errors="replace")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return

    flags = data.get("Flags", 0)
    if not isinstance(flags, int):
        flags = 0

    with lock:
        prev_mass_locked        = state.mass_locked
        prev_in_main_ship       = state.in_main_ship
        prev_gear               = state.landing_gear
        prev_scoop              = state.cargo_scoop
        prev_hardpoints         = state.hardpoints
        prev_lights             = state.lights_on
        prev_nv                 = state.night_vision
        prev_fa_off             = state.flight_assist_off
        prev_silent             = state.silent_running
        prev_analysis           = state.analysis_mode
        prev_srv                = state.in_srv
        prev_on_foot            = not state.in_main_ship and not state.in_srv
        prev_charging           = getattr(state, "_fsd_charging", False)

        state.docked            = bool(flags & FLAG_DOCKED)
        state.landed            = bool(flags & FLAG_LANDED)
        state.landing_gear      = bool(flags & FLAG_LANDING_GEAR)
        state.shields_up        = bool(flags & FLAG_SHIELDS_UP)
        state.supercruise       = bool(flags & FLAG_SUPERCRUISE)
        state.flight_assist_off = bool(flags & FLAG_FA_OFF)
        state.hardpoints        = bool(flags & FLAG_HARDPOINTS)
        state.mass_locked       = bool(flags & FLAG_MASS_LOCKED)
        state.cargo_scoop       = bool(flags & FLAG_CARGO_SCOOP)
        state.lights_on         = bool(flags & FLAG_LIGHTS)
        state.night_vision      = bool(flags & FLAG_NIGHT_VISION)
        state.silent_running    = bool(flags & FLAG_SILENT_RUNNING)
        state.scooping          = bool(flags & FLAG_SCOOPING)
        state.low_fuel          = bool(flags & FLAG_LOW_FUEL)
        state.overheating       = bool(flags & FLAG_OVERHEATING)
        state.in_srv            = bool(flags & FLAG_IN_SRV)
        state.analysis_mode     = bool(flags & FLAG_ANALYSIS_MODE)
        state.in_main_ship      = bool(flags & FLAG_IN_MAIN_SHIP)

        # SRV-specific flags (bits 12–15 only meaningful when in_srv)
        state.srv_handbrake        = bool(flags & FLAG_SRV_HANDBRAKE)
        state.srv_turret_view      = bool(flags & FLAG_SRV_TURRET_VIEW)
        state.srv_turret_retracted = bool(flags & FLAG_SRV_TURRET_RETRACTED)
        state.srv_drive_assist     = bool(flags & FLAG_SRV_DRIVE_ASSIST)

        # Power distribution pips — only valid when in main ship
        pips = data.get("Pips", [])
        if isinstance(pips, list) and len(pips) >= 3 and state.in_main_ship:
            state.pips_sys = pips[0] / 2.0
            state.pips_eng = pips[1] / 2.0
            state.pips_wep = pips[2] / 2.0

        flags2 = data.get("Flags2", 0)
        if not isinstance(flags2, int):
            flags2 = 0
        prev_orbital_cruise    = state.orbital_cruise
        state.orbital_cruise   = bool(flags2 & FLAG2_GLIDE)
        new_orbital_cruise     = state.orbital_cruise

        # On-foot Flags2 warnings
        state.low_oxygen      = bool(flags2 & FLAG2_LOW_OXYGEN)
        state.low_health_suit = bool(flags2 & FLAG2_LOW_HEALTH)
        state.suit_cold       = bool(flags2 & FLAG2_COLD)
        state.suit_hot        = bool(flags2 & FLAG2_HOT)

        # On-foot suit fields — only update when on foot
        v = data.get("Oxygen")
        if isinstance(v, (int, float)):
            state.suit_oxygen = float(v)
        v = data.get("Health")
        if isinstance(v, (int, float)) and not state.in_main_ship and not state.in_srv:
            state.suit_health = float(v)
        v = data.get("SelectedWeapon")
        if isinstance(v, str):
            state.selected_weapon = v
        v = data.get("Gravity")
        if isinstance(v, (int, float)):
            state.on_foot_gravity = float(v)

        new_mass_locked  = state.mass_locked
        new_in_main_ship = state.in_main_ship
        new_gear         = state.landing_gear
        new_scoop        = state.cargo_scoop
        new_hardpoints   = state.hardpoints
        new_lights       = state.lights_on
        new_nv           = state.night_vision
        new_fa_off       = state.flight_assist_off
        new_silent       = state.silent_running
        new_analysis     = state.analysis_mode
        new_srv          = state.in_srv
        new_charging     = bool(flags & 0x20000)
        state._fsd_charging = new_charging

        # COVAS Switch Callouts
        def _q(key: str, fallback: str, pri: bool = False, **kwargs):
            lang  = _ev._TTS_LANG
            voice = _ev._LANG_VOICES.get(lang) if lang != "en" else None
            if _vl.is_muted(key, lang=lang):
                return
            text  = _vl.pick(key, lang=lang, **kwargs) or fallback
            try:
                tts_q.put_nowait(TtsMsg(text=text, priority=pri, voice=voice))
            except Exception:
                pass

        if new_charging and not prev_charging:
            # We let events.py handle the speech to avoid duplicates
            pass

        if not first_run:
            if new_gear != prev_gear:
                if new_gear:
                    _q("LandingGear_Deployed", "Landing gear deployed.")
                else:
                    # Suppress retract callout when the game is shutting down — the
                    # gear collapses as part of the shutdown sequence, not a player action.
                    if not state.client_shutdown_pending:
                        _q("LandingGear_Retracted", "Landing gear retracted.")
            if new_scoop != prev_scoop:
                if new_scoop:
                    _q("CargoScoop_Deployed", "Cargo scoop deployed.")
                else:
                    _q("CargoScoop_Retracted", "Cargo scoop retracted.")
            if new_hardpoints != prev_hardpoints:
                if new_hardpoints:
                    _q("Hardpoints_Deployed", "Hardpoints deployed.")
                else:
                    _q("Hardpoints_Retracted", "Hardpoints retracted.")
            if new_lights != prev_lights and new_srv == prev_srv:
                # Suppress light toggle announcements when SRV state also changed
                # this tick — the light flag change is just a vehicle switch artefact.
                if new_lights:
                    _q("Lights_On", "Lights on.")
                else:
                    _q("Lights_Off", "Lights off.")
            if new_nv != prev_nv:
                if new_nv:
                    _q("NightVision_On", "Night vision enabled.")
                else:
                    _q("NightVision_Off", "Night vision disabled.")
            if new_fa_off != prev_fa_off:
                if new_fa_off:
                    _q("FlightAssist_Off", "Flight assist off.")
                else:
                    _q("FlightAssist_On", "Flight assist on.")
            if new_silent != prev_silent:
                if new_silent:
                    _q("SilentRunning_On", "Silent running enabled.")
                else:
                    _q("SilentRunning_Off", "Silent running disabled.")
            if new_analysis != prev_analysis and prev_in_main_ship and new_in_main_ship:
                if new_analysis:
                    _q("AnalysisMode", "Analysis mode.")
                else:
                    _q("CombatMode", "Combat mode.")
            if new_srv != prev_srv:
                if new_srv:
                    if prev_on_foot:
                        # Player was on foot and boarded an already-deployed SRV
                        _q("SRV_Boarded", "S R V boarded.")
                    else:
                        # Deployed from main ship
                        _q("SRV_Deployed", "S R V deployed.")
                else:
                    if new_in_main_ship:
                        # SRV recalled back into ship bay
                        _q("SRV_Secured", "S R V secured.")
                    else:
                        # Exited SRV on foot — SRV remains deployed on surface
                        _q("SRV_Exited", "S R V exited.")

        v = data.get("Heat")
        if isinstance(v, (int, float)):
            # Normalize: some versions use 0-1, others 0-100
            # If it's 0.7, it's likely 70%. If it's 70.0, it's 70%.
            # We target 0-100 for the state.
            if 0.0 < v < 1.0:
                state.heat = float(v * 100.0)
            else:
                state.heat = float(v)
        elif bool(flags & 0x100000): # Overheating flag fallback
            state.heat = max(state.heat, 100.0)
        else:
            if state.heat > 99.0: state.heat = 99.0 # Clamp if flag cleared

        fuel = data.get("Fuel")
        if isinstance(fuel, dict):
            v = fuel.get("FuelMain")
            if isinstance(v, (int, float)):
                state.fuel = float(v)
            v = fuel.get("FuelReservoir")
            if isinstance(v, (int, float)):
                state.fuel_reservoir = float(v)

        v = data.get("Cargo")
        if isinstance(v, (int, float)):
            state.cargo = int(v)
            
        # Reset fuel announcement flag if level drops
        if state.fuel_max > 0 and state.fuel < state.fuel_max * 0.9:
            state.fuel_announced = False

        # Always overwrite positional fields from Status.json — clear them when absent
        # so leaving a body/surface doesn't leave stale values frozen in the UI.
        v = data.get("Altitude")
        state.altitude = float(v) if isinstance(v, (int, float)) else None
        v = data.get("Latitude")
        state.lat = float(v) if isinstance(v, (int, float)) else None
        v = data.get("Longitude")
        state.lon = float(v) if isinstance(v, (int, float)) else None
        v = data.get("Heading")
        state.heading = float(v) if isinstance(v, (int, float)) else None

        v = data.get("BodyName")
        state.nearest_body = v if isinstance(v, str) and v else ""
            
        dest = data.get("Destination")
        if isinstance(dest, dict) and "Name" in dest:
            state.target_body = dest["Name"]
        else:
            state.target_body = ""

        _check_bio_distance(state, tts_q)

    # Mass lock transition TTS — only when the player was already in the main ship
    # both before and after (suppresses false triggers when boarding/exiting ship).
    # Also suppressed while in supercruise: the game re-sets mass lock when entering
    # supercruise near a body (hyperspace still blocked), but that's expected and
    # not actionable — announcing it there just creates noise.
    if prev_in_main_ship and new_in_main_ship and not state.supercruise and not state.orbital_cruise:
        lang  = _ev._TTS_LANG
        voice = _ev._LANG_VOICES.get(lang) if lang != "en" else None
        if new_mass_locked and not prev_mass_locked:
            if not _vl.is_muted("MassLocked", lang=lang):
                try:
                    text = _vl.pick("MassLocked", lang=lang) or "Mass locked."
                    tts_q.put_nowait(TtsMsg(text=text, priority=False, voice=voice))
                except Exception:
                    pass
        elif not new_mass_locked and prev_mass_locked:
            if not _vl.is_muted("MassLockReleased", lang=lang):
                try:
                    text = _vl.pick("MassLockReleased", lang=lang) or "Mass lock released."
                    tts_q.put_nowait(TtsMsg(text=text, priority=False, voice=voice))
                except Exception:
                    pass


def _compass_toward(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Return compass arrow pointing TOWARD (lat2, lon2) from (lat1, lon1)."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    angle = math.degrees(math.atan2(dlon, dlat))
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    idx = round(angle / 45) % 8
    return arrows[idx]


def _check_bio_distance(state: AppState, tts_q: queue.Queue) -> None:
    lat, lon = state.lat, state.lon
    if lat is None or lon is None:
        # Position temporarily unknown — don't wipe last known distances
        return

    # TTS alerts are only valid on a surface (landed in ship, in SRV, or on foot).
    # While flying in main ship, still update distance/bearing for display but suppress TTS.
    on_surface = state.landed or state.in_srv or (not state.in_main_ship and not state.in_srv)

    body_name = state.nearest_body
    _bidx     = state._bodies_by_name.get(body_name, -1)
    _sb       = state.bodies[_bidx] if 0 <= _bidx < len(state.bodies) else None
    body_radius = _sb.radius if _sb and _sb.radius > 0 else _DEFAULT_BODY_RADIUS_M

    for sc in state.bio_scans:
        if sc.complete or sc.samples == 0:
            sc.current_dist    = None
            sc.current_bearing = None
            sc.sample_bearings = []
            continue

        # Skip scans from other bodies — distance calculations would be meaningless
        # and could trigger false BioReady alerts when leaving a different body.
        if body_name and sc.body != body_name:
            sc.current_dist    = None
            sc.current_bearing = None
            sc.sample_bearings = []
            continue

        # Determine nav targets.
        # Priority: unvisited COMP-scanned positions (not within 100m of any
        # foot sample AND at least min_dist from all foot samples) → navigate
        # to those. Otherwise: navigate toward foot-scanned sample positions.
        #
        # Both "close_to_foot" (< 100 m) and "too_close_to_foot" (< min_dist)
        # are per-foot-sample distance checks; a COMP marker qualifies only
        # when *neither* triggers. Combined: no foot sample within
        # max(100, min_dist). Collapsing to a single comparison halves the
        # number of haversine calls per tick (this runs at up to 5 Hz on
        # foot, with dozens of comp markers on long bio hunts).
        foot_positions = list(zip(sc.sample_lats, sc.sample_lons))
        exclusion = max(100.0, sc.min_dist)

        unvisited_comp = []
        if foot_positions:
            for clat, clon in zip(sc.comp_lats, sc.comp_lons):
                # Early-exit inner loop: one foot-sample within the exclusion
                # zone is enough to disqualify this comp marker.
                ok = True
                for slat, slon in foot_positions:
                    if _haversine(clat, clon, slat, slon, body_radius) < exclusion:
                        ok = False
                        break
                if ok:
                    unvisited_comp.append((clat, clon))
        else:
            # No foot samples yet — every comp marker qualifies as unvisited.
            unvisited_comp = list(zip(sc.comp_lats, sc.comp_lons))

        if unvisited_comp:
            positions = unvisited_comp
        else:
            # Fall back to foot-scanned positions; then last_lat/last_lon for backward compat
            positions = foot_positions
            if not positions and sc.last_lat is not None and sc.last_lon is not None:
                positions = [(sc.last_lat, sc.last_lon)]

        if not positions:
            sc.current_dist    = None
            sc.current_bearing = None
            sc.sample_bearings = []
            continue

        # Compute per-target bearings
        sc.sample_bearings = [
            _compass_toward(lat, lon, slat, slon)
            for slat, slon in positions
        ]

        # Find nearest target for distance display
        best_dist   = float("inf")
        best_slat   = sc.last_lat
        best_slon   = sc.last_lon
        for slat, slon in positions:
            d = _haversine(lat, lon, slat, slon, body_radius)
            if d < best_dist:
                best_dist = d
                best_slat = slat
                best_slon = slon

        sc.current_dist = best_dist
        # Keep current_bearing for backward compat (now points toward nearest target)
        sc.current_bearing = _compass_toward(lat, lon, best_slat, best_slon) if best_slat is not None else None

        lang  = _ev._TTS_LANG
        voice = _ev._LANG_VOICES.get(lang) if lang != "en" else None

        if best_dist >= sc.min_dist:
            # Player is outside the exclusion zone — may scan next sample.
            # Supercruise and orbital cruise (glide) are the only hard suppressors.
            # unvisited_comp guard: player still navigating to a COMP-scanned marker,
            # not yet ready to sample.
            can_sample = (not state.supercruise and not state.orbital_cruise
                          and not unvisited_comp)
            if not sc.alerted and can_sample:
                sc.alerted = True
                if not _vl.is_muted("BioReady", lang=lang):
                    try:
                        fallback = f"{sc.species_localised} ready. You may scan the next sample."
                        _bvars = _ev._body_vars(_sb) if _sb is not None else {}
                        text = _vl.pick("BioReady", lang=lang,
                                        species=sc.species_localised,
                                        **_ev._bio_scan_vars(sc, state),
                                        **_bvars) or fallback
                        dedup_key = f"BioReady-{sc.species}-{sc.body}-{sc.samples}"
                        _audio_logger.info(f"BioReady TTS queued: species={sc.species}, body={sc.body}, samples={sc.samples}, key={dedup_key}")
                        tts_q.put_nowait(TtsMsg(
                            text=text,
                            priority=False,
                            voice=voice,
                            deduplication_key=dedup_key,
                        ))
                    except Exception as e:
                        _audio_logger.error(f"BioReady TTS error: {e}")
        else:
            # Player is inside the exclusion zone (too close to a previous sample).
            if on_surface:
                if sc.alerted:
                    # Player WAS outside (alerted=True) but moved back inside — warn.
                    # Reset alerted so the ready TTS fires again when they move away.
                    sc.alerted = False
                    if not _vl.is_muted("BioTooClose", lang=lang):
                        try:
                            fallback = f"Too close to {sc.species_localised} sample. Move away before scanning."
                            _bvars2 = _ev._body_vars(_sb) if _sb is not None else {}
                            text = _vl.pick("BioTooClose", lang=lang,
                                            species=sc.species_localised,
                                            **_ev._bio_scan_vars(sc, state),
                                            **_bvars2) or fallback
                            dedup_key = f"BioTooClose-{sc.species}-{sc.body}-{sc.samples}"
                            tts_q.put_nowait(TtsMsg(
                                text=text,
                                priority=False,
                                voice=voice,
                                deduplication_key=dedup_key,
                            ))
                        except Exception:
                            pass
                # else: already inside zone, alerted already False — do nothing


def _apply_cargo(path: Path, state: AppState, lock: threading.RLock) -> None:
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return
    inventory = data.get("Inventory")
    if not isinstance(inventory, list):
        return
    items = []
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        name   = entry.get("Name_Localised") or entry.get("Name", "")
        count  = int(entry.get("Count", 0))
        stolen = bool(entry.get("Stolen", 0))
        if name and count > 0:
            items.append({"name": name, "count": count, "stolen": stolen})
    items.sort(key=lambda x: x["name"].lower())
    with lock:
        state.cargo_items = items


def _apply_materials(path: Path, state: AppState, lock: threading.RLock) -> None:
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return

    def _parse(section) -> dict:
        result = {}
        for m in (section or []):
            if not isinstance(m, dict): continue
            loc = m.get("Name_Localised") or m.get("Name", "")
            cnt = int(m.get("Count", 0))
            if loc and cnt > 0:
                result[loc] = cnt
        return result

    with lock:
        state.materials_raw = _parse(data.get("Raw"))
        state.materials_mfg = _parse(data.get("Manufactured"))
        state.materials_enc = _parse(data.get("Encoded"))


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float, radius: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return radius * 2.0 * math.asin(math.sqrt(min(1.0, a)))
