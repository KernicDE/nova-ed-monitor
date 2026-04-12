from __future__ import annotations

import json
import logging
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

_log = logging.getLogger("nova.journal")


_BODY_EVENTS = frozenset({
    "FSDJump", "CarrierJump", "Location",
    "Scan", "SAAScanComplete", "FSSBodySignals", "SAASignalsFound",
})

# Estimated base values by planet class — fallback when body value is 0 (e.g. EDSM pre-populated)
_STAT_EST_VALUES: dict[str, int] = {
    "Earthlike body":                    2_500_000,
    "Water world":                         170_000,
    "Ammonia world":                       235_000,
    "Metal rich body":                     100_000,
    "High metal content body":              22_000,
    "Rocky body":                            3_500,
    "Rocky ice body":                        4_000,
    "Icy body":                              2_500,
    "Sudarsky class I gas giant":            3_500,
    "Sudarsky class II gas giant":          15_000,
    "Sudarsky class III gas giant":          4_500,
    "Sudarsky class IV gas giant":           5_500,
    "Sudarsky class V gas giant":            6_000,
    "Helium rich gas giant":                 3_500,
    "Gas giant with water-based life":      19_000,
    "Gas giant with water based life":      19_000,
    "Gas giant with ammonia-based life":    22_000,
    "Gas giant with ammonia based life":    22_000,
    "Water giant":                           4_000,
}


def _stat_est_value(b) -> int:
    """Estimate body base value when b.value == 0 (EDSM-populated bodies without scan data)."""
    return _STAT_EST_VALUES.get(b.planet_class, 0)


_route_edsm_lock        = threading.Lock()
_route_bodies_edsm_lock = threading.Lock()


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
            near_stations = db.get_system_stations(nearest[0], limit=50)
            with lock:
                state.nearest_populated_name       = nearest[0]
                state.nearest_populated_dist       = nearest[1]
                state.nearest_populated_allegiance = nearest[2]
                state.nearest_populated_stations   = near_stations
        else:
            with lock:
                state.nearest_populated_name     = ""
                state.nearest_populated_dist     = 0.0
                state.nearest_populated_stations = []
    else:
        with lock:
            state.nearest_populated_name     = ""
            state.nearest_populated_dist     = 0.0
            state.nearest_populated_stations = []

    # Stations at next waypoint
    if route_next:
        stations = db.get_system_stations(route_next)
        with lock:
            state.route_next_stations = stations
    else:
        with lock:
            state.route_next_stations = []

    # EDSM enrichment for full route list (system presence + metadata)
    with lock:
        route         = list(state.route_list)
        prev_edsm     = dict(state.route_list_edsm)   # preserve any previously live-fetched data
        prev_bodies   = dict(state.route_bodies_edsm)
    if route:
        names     = [e.get("StarSystem", "") for e in route if e.get("StarSystem")]
        edsm_data = db.get_systems_info_batch(names)
        # Preserve live-discovered entries for systems not in the local dump
        preserved = {n: d for n, d in prev_edsm.items() if d.get("live_known") and n not in edsm_data}
        with lock:
            state.route_list_edsm = {**edsm_data, **preserved}
        # Preserve already-fetched bodies data for systems still in route
        route_names_set = set(names)
        kept_bodies = {n: d for n, d in prev_bodies.items() if n in route_names_set}
        with lock:
            state.route_bodies_edsm = kept_bodies
    else:
        with lock:
            state.route_list_edsm   = {}
            state.route_bodies_edsm = {}

    # Kick off background live EDSM lookup — only one fetch thread at a time
    if route and _route_edsm_lock.acquire(blocking=False):
        t = threading.Thread(
            target=_fetch_route_edsm_live,
            args=(route, state, lock, db),
            daemon=True,
            name="nova-route-edsm",
        )
        t.start()

    # Kick off background bodies fetch (bio/geo signal counts) — only one at a time
    if route and _route_bodies_edsm_lock.acquire(blocking=False):
        t2 = threading.Thread(
            target=_fetch_route_bodies_live,
            args=(route, state, lock, db),
            daemon=True,
            name="nova-route-bodies",
        )
        t2.start()


# Cache TTL for route EDSM live lookup (7 days)
_ROUTE_EDSM_CACHE_DAYS = 7


def _fetch_route_edsm_live(route: list, state: AppState, lock, db: Database) -> None:
    """Background: query EDSM live API for route systems not in the local dump.
    Results cached for 7 days in edsm_route_cache. Updates state.route_list_edsm."""
    import time as _time
    from datetime import datetime, timedelta

    try:
        try:
            import httpx
        except ImportError:
            return

        names = [e.get("StarSystem", "") for e in route if e.get("StarSystem")]
        if not names:
            return

        # Which systems are already in local dump? Those are already "known".
        with lock:
            local_known = set(state.route_list_edsm.keys())

        need_check = [n for n in names if n not in local_known]
        if not need_check:
            return

        # Check local cache first
        cutoff = (datetime.utcnow() - timedelta(days=_ROUTE_EDSM_CACHE_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        cached = db.get_route_edsm_cache(need_check)
        fresh_cached = {n: d for n, d in cached.items() if d.get("cached_at", "") >= cutoff}
        to_fetch = [n for n in need_check if n not in fresh_cached]

        # Apply fresh cache to state immediately (both found and not-found)
        if fresh_cached:
            updates = {n: {"live_known": bool(d["known"])} for n, d in fresh_cached.items()}
            with lock:
                state.route_list_edsm = {**state.route_list_edsm, **updates}

        if not to_fetch:
            return

        # Batch query EDSM — up to 50 names per request
        _EDSM_BATCH = 50
        _EDSM_URL = "https://www.edsm.net/api-v1/systems"
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        new_cache_entries: list[dict] = []

        try:
            client = httpx.Client(timeout=15.0)
            for i in range(0, len(to_fetch), _EDSM_BATCH):
                batch = to_fetch[i:i + _EDSM_BATCH]
                params = [("systemName[]", n) for n in batch]
                params.append(("showId", "1"))
                try:
                    resp = client.get(_EDSM_URL, params=params)
                    resp.raise_for_status()
                    found = {s["name"] for s in resp.json() if isinstance(s, dict) and "name" in s}
                except Exception:
                    found = set()

                for name in batch:
                    known = name in found
                    new_cache_entries.append({
                        "name": name, "known": int(known),
                        "scoopable": -1, "cached_at": now_str,
                    })

                # Mark all checked systems: True if found in EDSM, False if not
                updates = {n: {"live_known": n in found} for n in batch}
                with lock:
                    state.route_list_edsm = {**state.route_list_edsm, **updates}

                if i + _EDSM_BATCH < len(to_fetch):
                    _time.sleep(1.0)  # be polite to EDSM API

            client.close()
        except Exception:
            pass

        if new_cache_entries:
            try:
                db.upsert_route_edsm_cache(new_cache_entries)
            except Exception:
                pass

    finally:
        _route_edsm_lock.release()


def _fetch_route_bodies_live(route: list, state: AppState, lock, db: Database) -> None:
    """Background: query EDSM /bodies per system for bio/geo signal totals.
    Results cached for 7 days. Updates state.route_bodies_edsm progressively."""
    import time as _time
    from datetime import datetime, timedelta
    from urllib.parse import quote as _quote

    try:
        try:
            import httpx
        except ImportError:
            return

        names = [e.get("StarSystem", "") for e in route if e.get("StarSystem")]
        if not names:
            return

        cutoff = (datetime.utcnow() - timedelta(days=_ROUTE_EDSM_CACHE_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
        cached = db.get_route_bodies_cache(names)
        fresh  = {n: d for n, d in cached.items() if d.get("cached_at", "") >= cutoff}

        # Apply fresh cache immediately
        if fresh:
            updates = {
                n: {"bio": d["bio_count"], "bodies": d["body_count"]}
                for n, d in fresh.items()
            }
            with lock:
                state.route_bodies_edsm = {**state.route_bodies_edsm, **updates}

        to_fetch = [n for n in names if n not in fresh]
        if not to_fetch:
            return

        _EDSM_BODIES_URL = "https://www.edsm.net/api-system-v1/bodies"
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        new_cache_entries: list[dict] = []

        try:
            client = httpx.Client(timeout=15.0)
            for i, name in enumerate(to_fetch):
                enc = _quote(name, safe="")
                bio_total  = 0
                body_count = 0
                try:
                    resp = client.get(f"{_EDSM_BODIES_URL}?systemName={enc}")
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict):
                        all_bodies = data.get("bodies") or []
                        body_count = len(all_bodies)
                        for body in all_bodies:
                            sigs = body.get("signals") or {}
                            for sig in sigs.get("signals") or []:
                                if "Biological" in sig.get("type", ""):
                                    bio_total += int(sig.get("count", 0))
                except Exception:
                    pass  # cache as 0/0

                new_cache_entries.append({
                    "system_name": name, "bio_count": bio_total,
                    "geo_count": 0, "body_count": body_count, "cached_at": now_str,
                })
                with lock:
                    state.route_bodies_edsm = {
                        **state.route_bodies_edsm,
                        name: {"bio": bio_total, "bodies": body_count},
                    }

                if i < len(to_fetch) - 1:
                    _time.sleep(1.0)  # be polite to EDSM API

            client.close()
        except Exception:
            pass

        if new_cache_entries:
            try:
                db.upsert_route_bodies_cache(new_cache_entries)
            except Exception:
                pass

    finally:
        _route_bodies_edsm_lock.release()


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

            # Save current bodies before system-changing events.
            # FSDJump/CarrierJump clear bodies themselves in events.py.
            # Location does NOT clear bodies in events.py, so we save + clear
            # here to prevent bodies from the old system being stored under the
            # new system name when Location crosses a system boundary.
            if ev_name in ("FSDJump", "CarrierJump", "Location"):
                _save_bodies_only(tmp, tmp_lock, db)
                if ev_name == "Location":
                    with tmp_lock:
                        tmp.bodies.clear()

            try:
                with tmp_lock:
                    handle(ev, tmp, silent_q, live=False)
            except Exception:
                continue

            if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound",
                           "SAAScanComplete"):
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
        commander = state.commander
    with lock:
        state.stats = db.get_stats(commander=commander)

    # Restore stored fleet from previous session
    ships_json = db.get_config("stored_ships_json")
    if ships_json:
        try:
            with lock:
                state.stored_ships = json.loads(ships_json)
        except Exception:
            pass

    # Restore nav route from previous session (journal replay will override if NavRoute present)
    route_json = db.get_config("route_snapshot_json")
    if route_json:
        try:
            snap = json.loads(route_json)
            with lock:
                if snap.get("destination") and not state.route_destination:
                    state.route_destination    = snap.get("destination", "")
                    state.route_hops           = snap.get("hops", 0)
                    state.route_next           = snap.get("next", "")
                    state.route_next_star      = snap.get("next_star", "")
                    state.route_next_scoopable = snap.get("scoopable", False)
                    state.route_dist           = snap.get("dist", 0.0)
                    state.route_next_dist      = snap.get("next_dist", 0.0)
                    state.route_list           = snap.get("list", [])
        except Exception:
            pass

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
                _log.info(f"Journal file: {latest.name}")
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
    _log.info(f"Backlog: {len(candidates)} journal file(s), last={last_file or 'none'}, offset={last_offset}")

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

            # Run the handler and capture pre-handle system + post-handle commander in one lock
            try:
                with lock:
                    sys_name  = state.system
                    log_ev    = handle(effective, state, silent_q, live=False)
                    commander = state.commander  # updated by LoadGame handler
            except Exception:
                continue

            # After entering a system, restore saved bodies from DB
            if ev_name in ("FSDJump", "CarrierJump", "Location"):
                _load_system_bodies(state, lock, db)

            if log_ev is not None:
                db.insert(log_ev, sys_name, commander=commander)

                if ev_name in ("HullDamage", "Repair", "RepairAll", "Resurrect", "Died", "LoadGame", "Loadout", "Location", "FSDJump"):
                    with lock:
                        hull = state.hull
                        state.push_event(log_ev)
                    db.set_hull(hull)
                else:
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
                handle(effective, state, silent_q, live=False)
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
                handle(effective, state, silent_q, live=False)

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

    _log.debug(f"Tailing: {path.name} from offset {start_offset}")
    initial_ino = os.fstat(fd.fileno()).st_ino
    if start_offset > 0:
        fd.seek(start_offset)
    else:
        fd.seek(0, 2)

    # On startup: fetch EDSM bodies for current system (silent — no unknown-to-EDSM announcement)
    if edsm_q is not None:
        with lock:
            sys_name = state.system
        if sys_name and sys_name != "—":
            try:
                edsm_q.put_nowait(("fetch_system_silent", sys_name))
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
                with lock:
                    state.journal_heartbeat = time.time()
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
                    sys_name  = state.system
                    prev_cmdr = state.commander

                # Before jump: save current bodies
                if ev_name in ("FSDJump", "CarrierJump"):
                    _save_current_bodies(state, lock, db)

                # Run event handler
                if ev_name in _CRITICAL_EVENTS:
                    _log.info(f"Event: {ev_name}")
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

                # Read commander after handle (LoadGame updates it)
                with lock:
                    commander = state.commander

                # Detect commander switch (different commander logged in mid-session)
                if ev_name == "LoadGame" and commander and prev_cmdr and commander != prev_cmdr:
                    _handle_commander_switch(commander, state, lock, db)

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
                    db.increment_stat("jump_count", commander=commander)
                    dist_ly = float(effective.get("JumpDist") or 0.0)
                    if dist_ly: db.increment_stat("jump_dist_ly", dist_ly, commander=commander)
                    _stat_changed = True
                elif ev_name == "Scan" and effective.get("ScanType") == "Detailed":
                    if effective.get("PlanetClass") or effective.get("StarType"):
                        db.increment_stat("fss_count", commander=commander)
                        first_disc = not effective.get("WasDiscovered")
                        if first_disc:
                            db.increment_stat("fss_undiscovered", commander=commander)
                        val = int(effective.get("EstimatedValue") or 0)
                        if val:
                            # Apply first-discovery bonus (2.6×) to match payout at cartographics
                            if first_disc:
                                val = int(val * 2.6)
                            db.increment_stat("fss_value", val, commander=commander)
                        _stat_changed = True
                elif ev_name == "SAAScanComplete":
                    body_nm  = effective.get("BodyName", "")
                    # Use WasDiscovered/WasMapped from the event directly — more reliable than body lookup
                    dss_disc = not effective.get("WasDiscovered")
                    dss_map  = not effective.get("WasMapped")
                    probes   = int(effective.get("ProbesUsed") or 0)
                    eff_tgt  = int(effective.get("EfficiencyTarget") or 0)
                    db.increment_stat("dss_count", commander=commander)
                    if dss_disc:
                        db.increment_stat("dss_undiscovered", commander=commander)
                    with lock:
                        _bidx = state._bodies_by_name.get(body_nm, -1)
                        _b = state.bodies[_bidx] if 0 <= _bidx < len(state.bodies) else None
                    if _b:
                        _bval = _b.value or _stat_est_value(_b)
                        if _bval > 0:
                            # Apply first-mapping bonus (3.3×) and optional efficiency bonus (+25%)
                            if dss_map:
                                _bval = int(_bval * 3.3)
                            if eff_tgt > 0 and probes <= eff_tgt:
                                _bval = int(_bval * 1.25)
                            db.increment_stat("dss_value", _bval, commander=commander)
                    _stat_changed = True
                elif ev_name == "ScanOrganic" and effective.get("ScanType") == "Analyse":
                    db.increment_stat("bio_count", commander=commander)
                    _sp  = effective.get("Species", "")
                    _bid = int(effective.get("Body") or 0)
                    with lock:
                        _bidx2 = state._bodies_by_id.get(_bid, -1)
                        _bn = state.bodies[_bidx2].name if 0 <= _bidx2 < len(state.bodies) else None
                        _sc = next((s for s in state.bio_scans
                                    if s.species == _sp and (_bn is None or s.body == _bn) and s.complete), None)
                    if _sc:
                        if _sc.first_footfall:  db.increment_stat("bio_first_footfall", commander=commander)
                        if _sc.value > 0:       db.increment_stat("bio_value", _sc.value, commander=commander)
                    _stat_changed = True
                elif ev_name in ("Bounty", "FactionKillBond"):
                    db.increment_stat("enemies_destroyed", commander=commander)
                    _stat_changed = True
                elif ev_name == "Died":
                    db.increment_stat("ships_lost", commander=commander)
                    _stat_changed = True
                elif ev_name in ("MultiSellExplorationData", "SellExplorationData"):
                    _e = int((effective.get("BaseValue") or 0) + (effective.get("Bonus") or 0))
                    if _e: db.increment_stat("credits_earned", _e, commander=commander); _stat_changed = True
                elif ev_name == "SellOrganicData":
                    _e = int(effective.get("TotalEarnings") or 0)
                    if _e: db.increment_stat("credits_earned", _e, commander=commander); _stat_changed = True
                elif ev_name == "RedeemVoucher":
                    _e = int(effective.get("Amount") or 0)
                    if _e: db.increment_stat("credits_earned", _e, commander=commander); _stat_changed = True
                elif ev_name == "MissionCompleted":
                    _e = int(effective.get("Reward") or 0)
                    if _e: db.increment_stat("credits_earned", _e, commander=commander); _stat_changed = True
                elif ev_name == "MarketSell":
                    _e = int(effective.get("TotalSale") or 0)
                    if _e: db.increment_stat("credits_earned", _e, commander=commander); _stat_changed = True
                elif ev_name == "MarketBuy":
                    _s = int(effective.get("TotalCost") or 0)
                    if _s: db.increment_stat("credits_spent", _s, commander=commander); _stat_changed = True
                elif ev_name == "ShipyardBuy":
                    _s = int(effective.get("ShipPrice") or 0)
                    if _s: db.increment_stat("credits_spent", _s, commander=commander); _stat_changed = True
                elif ev_name == "ModuleBuy":
                    _s = int(effective.get("BuyPrice") or 0)
                    if _s: db.increment_stat("credits_spent", _s, commander=commander); _stat_changed = True
                elif ev_name in ("BuyAmmo", "RepairAll", "Repair"):
                    _s = int(effective.get("Cost") or 0)
                    if _s: db.increment_stat("credits_spent", _s, commander=commander); _stat_changed = True
                elif ev_name == "BuyDrones":
                    _s = int(effective.get("TotalCost") or 0)
                    if _s: db.increment_stat("credits_spent", _s, commander=commander); _stat_changed = True
                if _stat_changed:
                    with lock:
                        state.stats = db.get_stats(commander=commander)

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

                # Persist fleet list so it survives restarts
                if ev_name == "StoredShips":
                    with lock:
                        ships_snap = list(state.stored_ships)
                    db.set_config("stored_ships_json", json.dumps(ships_snap))

                # After route update: refresh next-waypoint stations and persist route
                if ev_name in ("NavRoute", "NavRouteClear"):
                    try:
                        _update_dump_lookups(state, lock, db)
                    except Exception:
                        pass
                    try:
                        with lock:
                            route_snap = {
                                "destination": state.route_destination,
                                "hops":        state.route_hops,
                                "next":        state.route_next,
                                "next_star":   state.route_next_star,
                                "scoopable":   state.route_next_scoopable,
                                "dist":        state.route_dist,
                                "next_dist":   state.route_next_dist,
                                "list":        list(state.route_list),
                            }
                        db.set_config("route_snapshot_json", json.dumps(route_snap))
                    except Exception:
                        pass

                # After scan events: save updated bodies and bio scans
                if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound", "SAAScanComplete",
                               "ScanOrganic"):
                    _save_current_bodies(state, lock, db)

                if log_ev is not None:
                    db.insert(log_ev, sys_name, commander=commander)

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


# ── Commander switch ──────────────────────────────────────────────────────────

def _handle_commander_switch(
    new_cmdr: str,
    state:    AppState,
    lock:     threading.RLock,
    db:       Database,
) -> None:
    """Called when a different commander logs in during the live tail.
    Clears all in-memory commander-specific state and reloads from DB."""
    from .state import MAX_EVENTS
    _log.info(f"Commander switch → {new_cmdr}")

    with lock:
        state.bodies.clear()
        state._bodies_by_name.clear()
        state._bodies_by_id.clear()
        state.bio_scans.clear()
        state.events.clear()
        state.missions.clear()
        state.engineers.clear()
        state.stored_ships.clear()
        state.bgs_log.clear()
        state.massacre_kills.clear()
        state.colonisation_sites.clear()
        state.credits = 0
        state.hull    = 1.0
        state.first_footfall_bodies.clear()
        state.route_destination    = ""
        state.route_hops           = 0
        state.route_next           = ""
        state.route_next_star      = ""
        state.route_next_scoopable = False
        state.route_dist           = 0.0
        state.route_next_dist      = 0.0
        state.route_list.clear()

    # Reload events, hull, stats for the new commander
    recent = db.get_recent_events(MAX_EVENTS, commander=new_cmdr)
    with lock:
        for ev in recent:
            state.events.appendleft(ev)
        state.hull  = db.get_hull()
        state.stats = db.get_stats(commander=new_cmdr)

    # Restore persisted route (global key; will be overridden quickly by journal replay)
    route_json = db.get_config("route_snapshot_json")
    if route_json:
        try:
            snap = json.loads(route_json)
            with lock:
                if snap.get("destination"):
                    state.route_destination    = snap.get("destination", "")
                    state.route_hops           = snap.get("hops", 0)
                    state.route_next           = snap.get("next", "")
                    state.route_next_star      = snap.get("next_star", "")
                    state.route_next_scoopable = snap.get("scoopable", False)
                    state.route_dist           = snap.get("dist", 0.0)
                    state.route_next_dist      = snap.get("next_dist", 0.0)
                    state.route_list           = snap.get("list", [])
        except Exception:
            pass

    # Restore stored fleet (global key)
    ships_json = db.get_config("stored_ships_json")
    if ships_json:
        try:
            with lock:
                state.stored_ships = json.loads(ships_json)
        except Exception:
            pass

    # Load current system bodies/bio_scans for the new commander
    _load_system_bodies(state, lock, db)


# ── Body DB helpers ────────────────────────────────────────────────────────────

def _save_current_bodies(state: AppState, lock: threading.RLock, db: Database) -> None:
    with lock:
        system    = state.system
        commander = state.commander
        bodies    = list(state.bodies)
        bio_scans = list(state.bio_scans)
    if not system or system == "—":
        return
    db.save_bodies_batch(system, bodies)
    db.save_bio_scans(system, bio_scans, commander=commander)


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
        system    = state.system
        commander = state.commander
    if not system or system == "—":
        return
    saved = db.load_bodies(system)
    if saved:
        with lock:
            for body in saved:
                state.upsert_body(body)
    saved_scans = db.load_bio_scans(system, commander=commander)
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
