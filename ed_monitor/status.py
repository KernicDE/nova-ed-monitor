from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path

from .state import AppState
from .tts import TtsMsg

# Status.json flag bits
FLAG_DOCKED         = 1 << 0
FLAG_LANDED         = 1 << 1
FLAG_LANDING_GEAR   = 1 << 2
FLAG_SHIELDS_UP     = 1 << 3
FLAG_SUPERCRUISE    = 1 << 4
FLAG_FA_OFF         = 1 << 5
FLAG_HARDPOINTS     = 1 << 6
FLAG_MASS_LOCKED    = 1 << 16  # FSD Mass Locked (bit 7 is "In Wing")
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
    tick         = 0

    while True:
        try:
            mtime = os.stat(status_path).st_mtime
            if mtime != last_status:
                _apply_status(status_path, state, lock, tts_q, last_status == 0.0)
                last_status = mtime
        except OSError:
            pass

        # Poll cargo and materials every ~5 s (every 10th tick at 0.5 s)
        if tick % 10 == 0:
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

        tick += 1
        time.sleep(0.5)


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
        def _q(txt: str, pri: bool = False):
            try: tts_q.put_nowait(TtsMsg(text=txt, priority=pri))
            except Exception: pass

        if new_charging and not prev_charging:
            # We let events.py handle the speech to avoid duplicates
            pass
            
        if not first_run:
            if new_gear != prev_gear:
                _q("Landing gear deployed." if new_gear else "Landing gear retracted.")
            if new_scoop != prev_scoop:
                _q("Cargo scoop deployed." if new_scoop else "Cargo scoop retracted.")
            if new_hardpoints != prev_hardpoints:
                _q("Hardpoints deployed." if new_hardpoints else "Hardpoints retracted.")
            if new_lights != prev_lights:
                _q("Lights on." if new_lights else "Lights off.")
            if new_nv != prev_nv:
                _q("Night vision enabled." if new_nv else "Night vision disabled.")
            if new_fa_off != prev_fa_off:
                _q("Flight assist off." if new_fa_off else "Flight assist on.")
            if new_silent != prev_silent:
                _q("Silent running enabled." if new_silent else "Silent running disabled.")
            if new_analysis != prev_analysis and prev_in_main_ship and new_in_main_ship:
                _q("Analysis mode." if new_analysis else "Combat mode.")
            if new_srv != prev_srv:
                _q("S R V deployed." if new_srv else "S R V secured.")
        
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

        v = data.get("Altitude")
        if isinstance(v, (int, float)):
            state.altitude = float(v)
        v = data.get("Latitude")
        if isinstance(v, (int, float)):
            state.lat = float(v)
        v = data.get("Longitude")
        if isinstance(v, (int, float)):
            state.lon = float(v)
        v = data.get("Heading")
        if isinstance(v, (int, float)):
            state.heading = float(v)

        v = data.get("BodyName")
        if isinstance(v, str) and v:
            state.nearest_body = v
            
        dest = data.get("Destination")
        if isinstance(dest, dict) and "Name" in dest:
            state.target_body = dest["Name"]
        else:
            state.target_body = ""

        _check_bio_distance(state, tts_q)

    # Mass lock transition TTS — only when the player was already in the main ship
    # both before and after (suppresses false triggers when boarding/exiting ship)
    if prev_in_main_ship and new_in_main_ship:
        if new_mass_locked and not prev_mass_locked:
            try:
                tts_q.put_nowait(TtsMsg(text="Mass locked.", priority=False))
            except Exception:
                pass
        elif not new_mass_locked and prev_mass_locked:
            try:
                tts_q.put_nowait(TtsMsg(text="Mass lock released.", priority=False))
            except Exception:
                pass


def _compass_away(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Return compass arrow pointing AWAY from (lat2, lon2) as seen from (lat1, lon1)."""
    import math
    dlat = lat1 - lat2  # reversed: direction away from sample
    dlon = lon1 - lon2
    angle = math.degrees(math.atan2(dlon, dlat))
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    idx = round(angle / 45) % 8
    return arrows[idx]


def _check_bio_distance(state: AppState, tts_q: queue.Queue) -> None:
    lat, lon = state.lat, state.lon
    if lat is None or lon is None:
        # Position temporarily unknown — don't wipe last known distances
        return

    body_name   = state.nearest_body
    body_radius = next(
        (b.radius for b in state.bodies if b.name == body_name and b.radius > 0),
        3_389_500.0,
    )

    for sc in state.bio_scans:
        if sc.complete or sc.samples == 0:
            sc.current_dist    = None
            sc.current_bearing = None
            continue

        # Use all recorded sample positions (stored in sample_lats/sample_lons)
        # Fall back to last_lat/last_lon for backward compat (replayed sessions)
        positions = list(zip(sc.sample_lats, sc.sample_lons))
        if not positions and sc.last_lat is not None and sc.last_lon is not None:
            positions = [(sc.last_lat, sc.last_lon)]

        if not positions:
            sc.current_dist    = None
            sc.current_bearing = None
            continue

        # Find nearest previous sample
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

        # Bearing AWAY from nearest sample (direction to fly to increase distance)
        if best_slat is not None and best_slon is not None:
            sc.current_bearing = _compass_away(lat, lon, best_slat, best_slon)
        else:
            sc.current_bearing = None

        if best_dist >= sc.min_dist:
            if not sc.alerted:
                sc.alerted = True
                try:
                    tts_q.put_nowait(TtsMsg(
                        text=(
                            f"{sc.species_localised} ready. "
                            f"Distance {best_dist:.0f} metres. "
                            f"You may scan the next sample."
                        ),
                        priority=False,
                    ))
                except Exception:
                    pass
        else:
            sc.alerted = False


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
    import math
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return radius * 2.0 * math.asin(math.sqrt(min(1.0, a)))
