from __future__ import annotations

import json
import os
import queue
import select as _select
import threading
import time
from pathlib import Path
from typing import Optional

from .db import Database
from .events import handle
from .state import AppState, EventCategory, LogEvent
from .tts import TtsMsg


_BODY_EVENTS = frozenset({
    "FSDJump", "CarrierJump", "Location",
    "Scan", "SAAScanComplete", "FSSBodySignals", "SAASignalsFound",
})


def _update_dump_lookups(state: AppState, lock, db: Database) -> None:
    """Query local EDSM dump tables for power state, nearest populated system,
    and next-waypoint stations. Called after every system change and route update."""
    import math as _math
    with lock:
        sys_name   = state.system
        pop        = state.population
        pos        = state.star_pos
        route_next = state.route_next

    if sys_name:
        power, power_state = db.get_system_power(sys_name)
        with lock:
            state.system_power       = power
            state.system_power_state = power_state

    # Nearest populated: only useful when current system is uninhabited
    if pos and sys_name and pop == 0:
        nearest = db.get_nearest_populated(pos[0], pos[1], pos[2], exclude=sys_name)
        if nearest:
            with lock:
                state.nearest_populated_name       = nearest[0]
                state.nearest_populated_dist       = nearest[1]
                state.nearest_populated_allegiance = nearest[2]
        else:
            with lock:
                state.nearest_populated_name = ""
                state.nearest_populated_dist = 0.0
    else:
        with lock:
            state.nearest_populated_name = ""
            state.nearest_populated_dist = 0.0

    # Stations at next waypoint
    if route_next:
        stations = db.get_system_stations(route_next)
        with lock:
            state.route_next_stations = stations
    else:
        with lock:
            state.route_next_stations = []

# ── _get_latest cache ──────────────────────────────────────────────────────────
_latest_cache_time: float = 0.0
_latest_cache_path: Optional[Path] = None
_LATEST_CACHE_TTL: float = 5.0  # seconds between full directory scans


def _rebuild_body_db(journal_dir: Path, db: Database) -> None:
    """Scan all journal files and persist body data to DB.

    Skipped if the journal directory has not changed since the last rebuild.
    Runs in a background daemon thread so the live tail starts immediately.
    """
    try:
        candidates = sorted(
            [p for p in journal_dir.iterdir()
             if p.name.startswith("Journal.") and p.name.endswith(".log")],
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        return

    if not candidates:
        return

    # Skip rebuild if the newest journal file hasn't changed since last rebuild
    latest_mtime = str(candidates[-1].stat().st_mtime)
    stored_mtime = db.get_config("last_rebuild_mtime")
    if stored_mtime == latest_mtime:
        return

    tmp      = AppState()
    tmp_lock = threading.RLock()
    silent_q: queue.Queue = queue.Queue()

    for file_path in candidates:
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except OSError:
            continue

        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_name = ev.get("event", "")
            if ev_name not in _BODY_EVENTS:
                continue

            # Save current bodies before FSDJump/CarrierJump clears them
            if ev_name in ("FSDJump", "CarrierJump"):
                _save_bodies_only(tmp, tmp_lock, db)

            try:
                with tmp_lock:
                    handle(ev, tmp, silent_q)
            except Exception:
                continue

            if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound",
                           "SAAScanComplete", "Location"):
                _save_bodies_only(tmp, tmp_lock, db)

    # Final save for the last system processed
    _save_bodies_only(tmp, tmp_lock, db)

    # Record the mtime so we can skip next time if nothing changed
    db.set_config("last_rebuild_mtime", latest_mtime)


def monitor(
    state:       AppState,
    lock:        threading.RLock,
    tts_q:       queue.Queue,
    db:          Database,
    journal_dir: Path,
    edsm_q:      Optional[queue.Queue],
    spansh_q:    Optional[queue.Queue] = None,
) -> None:
    current: Optional[Path] = None
    last_file = db.get_config("last_journal_file")
    last_offset_str = db.get_config("last_journal_offset")
    last_offset = int(last_offset_str) if last_offset_str else 0

    # Rebuild body DB in the background — live tail starts immediately without waiting.
    threading.Thread(
        target=_rebuild_body_db,
        args=(journal_dir, db),
        daemon=True,
        name="nova-body-rebuild",
    ).start()

    _process_backlog(
        state, lock, tts_q, db, journal_dir,
        edsm_q, last_file, last_offset
    )

    with lock:
        state.stats = db.get_stats()

    # Populate power/nearest/stations from local EDSM dump data right after startup
    try:
        _update_dump_lookups(state, lock, db)
    except Exception:
        pass

    while True:
        latest = _get_latest(journal_dir)

        if latest != current:
            if current is not None:
                ev = LogEvent.new(EventCategory.System, "New game session.")
                with lock:
                    state.push_event(ev)
                try:
                    tts_q.put_nowait(TtsMsg(text="New game session.", priority=False))
                except Exception:
                    pass

            start_offset = 0
            if latest is not None:
                start_offset = _init_scan(latest, state, lock, journal_dir, db)
                db.set_config("last_journal_file", latest.name)
                db.set_config("last_journal_offset", str(start_offset))

            current = latest

        if current is None:
            time.sleep(2.0)
            continue

        _follow(current, state, lock, tts_q, db, journal_dir, edsm_q,
                start_offset=start_offset, spansh_q=spansh_q)
        current = None

# ── Backlog scan ───────────────────────────────────────────────────────────────

def _process_backlog(
    state:       AppState,
    lock:        threading.RLock,
    tts_q:       queue.Queue,
    db:          Database,
    journal_dir: Path,
    edsm_q:      Optional[queue.Queue],
    last_file:   str,
    last_offset: int,
) -> None:
    try:
        candidates = [
            p for p in journal_dir.iterdir()
            if p.name.startswith("Journal.") and p.name.endswith(".log")
        ]
    except OSError:
        return

    if not candidates:
        return

    # Sort files chronologically: oldest to newest
    candidates.sort(key=lambda p: p.stat().st_mtime)

    # Find the index of the last processed file
    start_idx = -1
    for i, p in enumerate(candidates):
        if p.name == last_file:
            start_idx = i
            break

    # If the file hasn't been found, or we're on the last file and it's 
    # the latest anyway, just parse the latest file from offset 0
    if start_idx == -1:
        start_idx = len(candidates) - 1
        last_offset = 0
        
    # We create a silent queue to avoid TTS spam during backlog catchup
    silent_q: queue.Queue = queue.Queue()

    # Process all files starting from the last known file
    for i in range(start_idx, len(candidates)):
        file_path = candidates[i]
        offset = last_offset if i == start_idx else 0
        
        try:
            with open(file_path, "rb") as f:
                if offset > 0:
                    f.seek(offset)
                raw = f.read()
        except OSError:
            continue
            
        lines = raw.decode("utf-8", errors="replace").splitlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_name = ev.get("event", "")
            effective = ev
            if ev_name == "NavRoute":
                effective = _read_navroute_json(journal_dir) or ev

            with lock:
                sys_name = state.system
            
            # Run the handler, sending TTS output to the silent queue
            try:
                with lock:
                    log_ev = handle(effective, state, silent_q)
            except Exception as exc:
                continue

            # After entering a system, restore saved bodies from DB
            if ev_name in ("FSDJump", "CarrierJump", "Location"):
                _load_system_bodies(state, lock, db)

            if log_ev is not None:
                db.insert(log_ev, sys_name)

                if ev_name in ("HullDamage", "Repair", "RepairAll", "Resurrect", "Died", "LoadGame", "Loadout", "Location", "FSDJump"):
                    with lock:
                        hull = state.hull
                    db.set_hull(hull)

                with lock:
                    state.push_event(log_ev)

    # Merge DB bio_scans (completed scans from prior sessions) into state,
    # then persist — prevents overwriting completed entries with partial replay data
    _load_system_bodies(state, lock, db)
    _save_current_bodies(state, lock, db)


# ── Startup scan ───────────────────────────────────────────────────────────────

def _init_scan(
    path:        Path,
    state:       AppState,
    lock:        threading.RLock,
    journal_dir: Path,
    db:          Database,
) -> int:
    """Replay journal from start to rebuild state. Returns byte offset after
    the last byte read, so _follow can start from there."""
    saved_hull = db.get_hull()
    silent_q: queue.Queue = queue.Queue()

    try:
        with open(path, "rb") as f:
            raw      = f.read()
            file_pos = f.tell()
        lines = raw.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return 0

    found_hull_event = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue

        ev_name = ev.get("event", "")

        effective = ev
        if ev_name == "NavRoute":
            effective = _read_navroute_json(journal_dir) or ev

        if ev_name in ("HullDamage", "Repair", "RepairAll", "Resurrect", "Died", "LoadGame", "Loadout", "Location", "FSDJump", "CarrierJump"):
            found_hull_event = True
            with lock:
                handle(effective, state, silent_q)
        elif ev_name in (
            "Fileheader",
            "ShieldState", "NavRoute",
            "Scan", "SAAScanComplete", "FSSDiscoveryScan",
            "FSSBodySignals", "SAASignalsFound", "ScanOrganic",
            "Docked", "Undocked", "Touchdown", "Liftoff", "Disembark",
            "MissionAccepted", "MissionCompleted", "MissionFailed",
            "MissionAbandoned", "MissionRedirected",
            "EngineerProgress", "Materials",
            "MaterialCollected", "MaterialDiscarded",
        ):
            with lock:
                handle(effective, state, silent_q)

    if not found_hull_event:
        with lock:
            state.hull = saved_hull

    _load_system_bodies(state, lock, db)
    return file_pos


# ── Live tail ─────────────────────────────────────────────────────────────────

def _follow(
    path:         Path,
    state:        AppState,
    lock:         threading.RLock,
    tts_q:        queue.Queue,
    db:           Database,
    journal_dir:  Path,
    edsm_q:       Optional[queue.Queue],
    start_offset: int = 0,
    spansh_q:     Optional[queue.Queue] = None,
) -> None:
    try:
        fd = open(path, "r", errors="replace")
    except OSError:
        return

    initial_ino = os.fstat(fd.fileno()).st_ino
    if start_offset > 0:
        fd.seek(start_offset)
    else:
        fd.seek(0, 2)

    # On startup: fetch EDSM bodies for current system
    if edsm_q is not None:
        with lock:
            sys_name = state.system
        if sys_name and sys_name != "—":
            try:
                edsm_q.put_nowait(("fetch_system", sys_name))
            except Exception:
                pass

    buf = ""
    _lines_since_save = 0
    _OFFSET_SAVE_INTERVAL = 20  # write DB offset at most every N lines
    _CRITICAL_EVENTS = frozenset({"FSDJump", "CarrierJump", "Location", "Died", "Shutdown"})

    try:
        while True:
            chunk = fd.read(65536)
            if not chunk:
                # Flush offset before sleeping so position is never lost
                db.set_config("last_journal_offset", str(fd.tell()))
                _lines_since_save = 0

                # Return if a newer journal file has appeared
                latest = _get_latest(journal_dir)
                if latest is not None and latest != path:
                    return
                try:
                    cur_ino = os.stat(path).st_ino
                except OSError:
                    return
                if cur_ino != initial_ino:
                    return
                time.sleep(0.2)
                continue

            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ev_name   = ev.get("event", "")
                effective = ev
                if ev_name == "NavRoute":
                    effective = _read_navroute_json(journal_dir) or ev

                with lock:
                    sys_name = state.system

                # Before jump: save current bodies
                if ev_name in ("FSDJump", "CarrierJump"):
                    _save_current_bodies(state, lock, db)

                # Run event handler
                try:
                    with lock:
                        log_ev = handle(effective, state, tts_q)
                except Exception as exc:
                    with lock:
                        state.push_event(LogEvent.new(
                            EventCategory.System,
                            f"Handler error [{ev_name}]: {exc}",
                        ))
                    log_ev = None
                    # Still save offset so we don't replay this broken line
                    _lines_since_save += 1
                    if _lines_since_save >= _OFFSET_SAVE_INTERVAL or ev_name in _CRITICAL_EVENTS:
                        db.set_config("last_journal_offset", str(fd.tell()))
                        _lines_since_save = 0
                    continue

                # Session stats (live events only, not replayed during init)
                if ev_name in ("FSDJump", "CarrierJump"):
                    with lock:
                        state.session_jumps += 1
                        state.jump_dist_total += float(effective.get("JumpDist") or 0.0)

                elif ev_name == "Scan":
                    if ev.get("ScanType") == "Detailed" and not ev.get("WasDiscovered"):
                        with lock:
                            state.session_first_disc += 1
                            state.session_value += int(ev.get("EstimatedValue", 0))
                elif ev_name == "SAAScanComplete":
                    with lock:
                        state.session_mapped += 1

                # Persistent statistics (live events only)
                _stat_changed = False
                if ev_name == "FSDJump":
                    db.increment_stat("jump_count")
                    dist_ly = float(effective.get("JumpDist") or 0.0)
                    if dist_ly: db.increment_stat("jump_dist_ly", dist_ly)
                    _stat_changed = True
                elif ev_name == "Scan" and effective.get("ScanType") == "Detailed":
                    if effective.get("PlanetClass") or effective.get("StarType"):
                        db.increment_stat("fss_count")
                        if not effective.get("WasDiscovered"):
                            db.increment_stat("fss_undiscovered")
                        val = int(effective.get("EstimatedValue") or 0)
                        if val: db.increment_stat("fss_value", val)
                        _stat_changed = True
                elif ev_name == "SAAScanComplete":
                    body_nm = effective.get("BodyName", "")
                    db.increment_stat("dss_count")
                    with lock:
                        _bidx = state._bodies_by_name.get(body_nm, -1)
                        _b = state.bodies[_bidx] if 0 <= _bidx < len(state.bodies) else None
                    if _b:
                        if _b.first_discovered: db.increment_stat("dss_undiscovered")
                        if _b.value > 0:        db.increment_stat("dss_value", _b.value)
                    _stat_changed = True
                elif ev_name == "ScanOrganic" and effective.get("ScanType") == "Analyse":
                    db.increment_stat("bio_count")
                    _sp  = effective.get("Species", "")
                    _bid = int(effective.get("Body") or 0)
                    with lock:
                        _bidx2 = state._bodies_by_id.get(_bid, -1)
                        _bn = state.bodies[_bidx2].name if 0 <= _bidx2 < len(state.bodies) else None
                        _sc = next((s for s in state.bio_scans
                                    if s.species == _sp and (_bn is None or s.body == _bn) and s.complete), None)
                    if _sc:
                        if _sc.first_footfall:  db.increment_stat("bio_first_footfall")
                        if _sc.value > 0:       db.increment_stat("bio_value", _sc.value)
                    _stat_changed = True
                elif ev_name in ("Bounty", "FactionKillBond"):
                    db.increment_stat("enemies_destroyed")
                    _stat_changed = True
                elif ev_name == "Died":
                    db.increment_stat("ships_lost")
                    _stat_changed = True
                elif ev_name in ("MultiSellExplorationData", "SellExplorationData"):
                    _e = int((effective.get("BaseValue") or 0) + (effective.get("Bonus") or 0))
                    if _e: db.increment_stat("credits_earned", _e); _stat_changed = True
                elif ev_name == "SellOrganicData":
                    _e = int(effective.get("TotalEarnings") or 0)
                    if _e: db.increment_stat("credits_earned", _e); _stat_changed = True
                elif ev_name == "RedeemVoucher":
                    _e = int(effective.get("Amount") or 0)
                    if _e: db.increment_stat("credits_earned", _e); _stat_changed = True
                elif ev_name == "MissionCompleted":
                    _e = int(effective.get("Reward") or 0)
                    if _e: db.increment_stat("credits_earned", _e); _stat_changed = True
                elif ev_name == "MarketSell":
                    _e = int(effective.get("TotalSale") or 0)
                    if _e: db.increment_stat("credits_earned", _e); _stat_changed = True
                elif ev_name == "MarketBuy":
                    _s = int(effective.get("TotalCost") or 0)
                    if _s: db.increment_stat("credits_spent", _s); _stat_changed = True
                elif ev_name == "ShipyardBuy":
                    _s = int(effective.get("ShipPrice") or 0)
                    if _s: db.increment_stat("credits_spent", _s); _stat_changed = True
                elif ev_name == "ModuleBuy":
                    _s = int(effective.get("BuyPrice") or 0)
                    if _s: db.increment_stat("credits_spent", _s); _stat_changed = True
                elif ev_name in ("BuyAmmo", "RepairAll", "Repair"):
                    _s = int(effective.get("Cost") or 0)
                    if _s: db.increment_stat("credits_spent", _s); _stat_changed = True
                elif ev_name == "BuyDrones":
                    _s = int(effective.get("TotalCost") or 0)
                    if _s: db.increment_stat("credits_spent", _s); _stat_changed = True
                if _stat_changed:
                    with lock:
                        state.stats = db.get_stats()

                # After jump or start: load saved bodies, trigger EDSM fetch
                if ev_name in ("FSDJump", "CarrierJump", "Location"):
                    _load_system_bodies(state, lock, db)
                    with lock:
                        new_sys = state.system
                        pop     = state.population
                        state.carriers_current_system = []
                    if edsm_q is not None and new_sys:
                        try:
                            edsm_q.put_nowait(("fetch_system", new_sys))
                            if pop > 0:
                                edsm_q.put_nowait(("fetch_stations", new_sys))
                        except Exception:
                            pass
                    if spansh_q is not None and new_sys:
                        try:
                            spansh_q.put_nowait(("fetch_carriers", new_sys))
                        except Exception:
                            pass
                    try:
                        _update_dump_lookups(state, lock, db)
                    except Exception:
                        pass

                # After route update: refresh next-waypoint stations
                if ev_name in ("NavRoute", "NavRouteClear"):
                    try:
                        _update_dump_lookups(state, lock, db)
                    except Exception:
                        pass

                # After scan events: save updated bodies and bio scans
                if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound", "SAAScanComplete",
                               "ScanOrganic"):
                    _save_current_bodies(state, lock, db)

                if log_ev is not None:
                    db.insert(log_ev, sys_name)

                    if ev_name in ("HullDamage", "Repair", "RepairAll", "Resurrect", "Died", "LoadGame", "Loadout", "Location", "FSDJump"):
                        with lock:
                            hull = state.hull
                        db.set_hull(hull)

                    with lock:
                        state.push_event(log_ev)

                # Throttle offset saves: write on critical events or every N lines
                _lines_since_save += 1
                if _lines_since_save >= _OFFSET_SAVE_INTERVAL or ev_name in _CRITICAL_EVENTS:
                    db.set_config("last_journal_offset", str(fd.tell()))
                    _lines_since_save = 0

    finally:
        # Always flush the current offset so nothing is replayed on restart
        try:
            db.set_config("last_journal_offset", str(fd.tell()))
        except Exception:
            pass
        fd.close()


# ── Body DB helpers ────────────────────────────────────────────────────────────

def _save_current_bodies(state: AppState, lock: threading.RLock, db: Database) -> None:
    with lock:
        system = state.system
        bodies = list(state.bodies)
        bio_scans = list(state.bio_scans)
    if not system or system == "—":
        return
    db.save_bodies_batch(system, bodies)
    db.save_bio_scans(system, bio_scans)


def _save_bodies_only(state: AppState, lock: threading.RLock, db: Database) -> None:
    """Save only body data — never touches bio_scans in DB."""
    with lock:
        system = state.system
        bodies = list(state.bodies)
    if not system or system == "—":
        return
    db.save_bodies_batch(system, bodies)


def _load_system_bodies(state: AppState, lock: threading.RLock, db: Database) -> None:
    with lock:
        system = state.system
    if not system or system == "—":
        return
    saved = db.load_bodies(system)
    if saved:
        with lock:
            for body in saved:
                state.upsert_body(body)
    saved_scans = db.load_bio_scans(system)
    if saved_scans:
        with lock:
            for sc in saved_scans:
                existing = next(
                    (s for s in state.bio_scans if s.species == sc.species and s.body == sc.body),
                    None,
                )
                if existing is None:
                    state.bio_scans.append(sc)
                elif sc.samples > existing.samples or (sc.complete and not existing.complete):
                    # DB record is more complete than what journal replay produced — replace it
                    state.bio_scans.remove(existing)
                    state.bio_scans.append(sc)
            # Restore first-footfall announcements so they don't re-fire on bodies
            # the player has already visited with first footfall
            for sc in state.bio_scans:
                if sc.first_footfall and sc.body:
                    state.first_footfall_bodies.add(sc.body)


# ── File helpers ───────────────────────────────────────────────────────────────

def _read_navroute_json(journal_dir: Path) -> Optional[dict]:
    try:
        text = (journal_dir / "NavRoute.json").read_text(errors="replace")
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None


def _get_latest(journal_dir: Path) -> Optional[Path]:
    global _latest_cache_time, _latest_cache_path
    now = time.monotonic()
    if now - _latest_cache_time < _LATEST_CACHE_TTL:
        return _latest_cache_path
    try:
        candidates = [
            p for p in journal_dir.iterdir()
            if p.name.startswith("Journal.") and p.name.endswith(".log")
        ]
        result = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
    except OSError:
        result = None
    _latest_cache_time = now
    _latest_cache_path = result
    return result
