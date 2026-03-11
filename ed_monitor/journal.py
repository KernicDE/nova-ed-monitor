from __future__ import annotations

import json
import os
import queue
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


def _rebuild_body_db(journal_dir: Path, db: Database) -> None:
    """Scan all journal files and persist body data to DB.

    Runs on every startup so bodies scanned before NOVA was running are
    always available via _load_system_bodies.
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
                _save_current_bodies(tmp, tmp_lock, db)

            try:
                with tmp_lock:
                    handle(ev, tmp, silent_q)
            except Exception:
                continue

            if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound",
                           "SAAScanComplete", "Location"):
                _save_current_bodies(tmp, tmp_lock, db)

    # Final save for the last system processed
    _save_current_bodies(tmp, tmp_lock, db)


def monitor(
    state:       AppState,
    lock:        threading.RLock,
    tts_q:       queue.Queue,
    db:          Database,
    journal_dir: Path,
    edsm_q:      Optional[queue.Queue],
) -> None:
    current: Optional[Path] = None
    last_file = db.get_config("last_journal_file")
    last_offset_str = db.get_config("last_journal_offset")
    last_offset = int(last_offset_str) if last_offset_str else 0

    # Scan all journal files to rebuild the body DB from scratch.
    # This covers bodies scanned before NOVA was ever running.
    _rebuild_body_db(journal_dir, db)

    _process_backlog(
        state, lock, tts_q, db, journal_dir,
        edsm_q, last_file, last_offset
    )

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
                start_offset=start_offset)
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

    # Persist whatever bodies we built during backlog replay
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
            "Docked", "Undocked", "Touchdown", "Liftoff",
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
) -> None:
    try:
        fd = open(path, "r", errors="replace")
    except OSError:
        return

    try:
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
        while True:
            chunk = fd.read(65536)
            if not chunk:
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
                    continue

                # Session stats (live events only, not replayed during init)
                if ev_name in ("FSDJump", "CarrierJump"):
                    with lock:
                        state.session_jumps += 1
                elif ev_name == "Scan":
                    if ev.get("ScanType") == "Detailed" and not ev.get("WasDiscovered"):
                        with lock:
                            state.session_first_disc += 1
                            state.session_value += int(ev.get("EstimatedValue", 0))
                elif ev_name == "SAAScanComplete":
                    with lock:
                        state.session_mapped += 1

                # After jump or start: load saved bodies, trigger EDSM fetch
                if ev_name in ("FSDJump", "CarrierJump", "Location"):
                    _load_system_bodies(state, lock, db)
                    if edsm_q is not None:
                        with lock:
                            new_sys = state.system
                            pop     = state.population
                        if new_sys:
                            try:
                                edsm_q.put_nowait(("fetch_system", new_sys))
                                if pop > 0:
                                    edsm_q.put_nowait(("fetch_stations", new_sys))
                            except Exception:
                                pass

                # After scan events: save updated bodies
                if ev_name in ("Scan", "FSSBodySignals", "SAASignalsFound", "SAAScanComplete"):
                    _save_current_bodies(state, lock, db)

                if log_ev is not None:
                    db.insert(log_ev, sys_name)

                    if ev_name in ("HullDamage", "Repair", "RepairAll", "Resurrect", "Died", "LoadGame", "Loadout", "Location", "FSDJump"):
                        with lock:
                            hull = state.hull
                        db.set_hull(hull)

                    with lock:
                        state.push_event(log_ev)
                        
                db.set_config("last_journal_offset", str(fd.tell()))

    finally:
        fd.close()


# ── Body DB helpers ────────────────────────────────────────────────────────────

def _save_current_bodies(state: AppState, lock: threading.RLock, db: Database) -> None:
    with lock:
        system = state.system
        bodies = list(state.bodies)
    if not system or system == "—":
        return
    for body in bodies:
        db.save_body(system, body)


def _load_system_bodies(state: AppState, lock: threading.RLock, db: Database) -> None:
    with lock:
        system = state.system
    if not system or system == "—":
        return
    saved = db.load_bodies(system)
    if not saved:
        return
    with lock:
        for body in saved:
            state.upsert_body(body)


# ── File helpers ───────────────────────────────────────────────────────────────

def _read_navroute_json(journal_dir: Path) -> Optional[dict]:
    try:
        text = (journal_dir / "NavRoute.json").read_text(errors="replace")
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None


def _get_latest(journal_dir: Path) -> Optional[Path]:
    try:
        candidates = [
            p for p in journal_dir.iterdir()
            if p.name.startswith("Journal.") and p.name.endswith(".log")
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
