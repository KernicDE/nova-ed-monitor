"""Neutron star route planner.

Primary: Spansh API (async job, real system names, high quality).
Fallback: local greedy search against the downloaded neutron-star dump.

Receives messages via queue: ("plot", target_system_name).
Writes results to state.neutron_route / neutron_route_to / neutron_route_status /
neutron_route_source.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .state import AppState

_log = logging.getLogger("nova.neutron")

_DUMP_URL   = "https://downloads.spansh.co.uk/systems_neutron.json.gz"
_DATA_DIR   = Path.home() / ".local" / "share" / "nova"
_DUMP_PATH  = _DATA_DIR / "systems_neutron.json.gz"
_MAX_AGE    = 86_400.0   # refresh daily
_NEUTRON_BOOST = 4.0     # boosted range multiplier
_BEAM_WIDTH    = 40      # candidates per step for local fallback
_MAX_JUMPS     = 2_000   # safety cap

_SPANSH_ROUTE_URL   = "https://spansh.co.uk/api/route"
_SPANSH_RESULTS_URL = "https://spansh.co.uk/api/results/{}"
_SPANSH_TIMEOUT     = 120  # seconds to wait for Spansh API result


def spawn(state: AppState, lock: threading.RLock, db) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    threading.Thread(
        target=_worker,
        args=(q, state, lock, db),
        daemon=True,
        name="nova-neutron",
    ).start()
    return q


# ── Worker ─────────────────────────────────────────────────────────────────────

def _worker(q: queue.Queue, state: AppState, lock: threading.RLock, db) -> None:
    # Ensure dump table exists
    _ensure_table(db)

    # Download dump if stale (non-blocking; done in this thread before first query)
    _refresh_dump_if_needed(db)

    # Update star count in state so the panel can show it
    with db._lock:
        count = db._conn.execute("SELECT COUNT(*) FROM neutron_stars").fetchone()[0]
    with lock:
        state.neutron_star_count = count

    while True:
        try:
            msg = q.get(timeout=60.0)
        except queue.Empty:
            # Periodic refresh check
            _refresh_dump_if_needed(db)
            with db._lock:
                count = db._conn.execute("SELECT COUNT(*) FROM neutron_stars").fetchone()[0]
            with lock:
                state.neutron_star_count = count
            continue

        if not isinstance(msg, tuple) or len(msg) < 2 or msg[0] != "plot":
            continue

        target_name: str = msg[1]
        if not target_name:
            continue

        # Grab current position + jump range from state
        with lock:
            star_pos   = state.star_pos
            jump_range = state.jump_range
            cur_system = state.system

        if not star_pos or jump_range <= 0.0:
            with lock:
                state.neutron_route_status = "error"
                state.neutron_route        = []
                state.neutron_route_to     = target_name
            _log.warning("Neutron plotter: no position or jump range available.")
            continue

        with lock:
            state.neutron_route_status = "plotting"
            state.neutron_route        = []
            state.neutron_route_to     = target_name
            state.neutron_route_source = ""

        _log.info(f"Neutron plotter: {cur_system} → {target_name}  range={jump_range:.1f} ly")

        # ── Try Spansh API first ───────────────────────────────────────────────
        route = _spansh_route(cur_system, target_name, jump_range)
        source = "Spansh"

        if route is None:
            # ── Local fallback ─────────────────────────────────────────────────
            _log.info("Spansh API failed — using local neutron-star fallback.")
            target_pos = _lookup_system(db, target_name)
            if target_pos is None:
                with lock:
                    state.neutron_route_status = "error"
                    state.neutron_route        = []
                    state.neutron_route_to     = target_name
                _log.warning(f"Target '{target_name}' not found in EDSM/neutron data.")
                continue
            route  = _plan_route(db, star_pos, target_pos, target_name, jump_range)
            source = "local"

        with lock:
            state.neutron_route        = route
            state.neutron_route_to     = target_name
            state.neutron_route_status = "done" if route else "error"
            state.neutron_route_source = source if route else ""

        _log.info(f"Neutron plotter ({source}): {len(route)} jumps planned.")


# ── Spansh API ─────────────────────────────────────────────────────────────────

def _spansh_route(src_name: str, dst_name: str, jump_range: float) -> Optional[list[dict]]:
    """Submit a neutron route job to Spansh and poll until complete.
    Returns list of jump dicts or None on any failure."""
    import urllib.parse

    params = urllib.parse.urlencode({
        "source":      src_name,
        "destination": dst_name,
        "efficiency":  60,
        "range":       f"{jump_range:.2f}",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            _SPANSH_ROUTE_URL,
            data=params,
            headers={
                "User-Agent":   "NOVA-ed-monitor/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        job_id = data.get("job")
        if not job_id:
            _log.warning(f"Spansh route: unexpected response: {data}")
            return None
    except Exception as exc:
        _log.warning(f"Spansh route submit failed: {exc}")
        return None

    _log.info(f"Spansh route job submitted: {job_id}")
    poll_url = _SPANSH_RESULTS_URL.format(job_id)

    for _ in range(_SPANSH_TIMEOUT):
        time.sleep(1.0)
        try:
            req = urllib.request.Request(
                poll_url,
                headers={"User-Agent": "NOVA-ed-monitor/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            _log.debug(f"Spansh poll error: {exc}")
            continue

        status = data.get("status", "")
        if status == "ok":
            jumps = (data.get("result") or {}).get("system_jumps") or []
            _log.info(f"Spansh route done: {len(jumps)} waypoints")
            route = []
            for j in jumps:
                dist = float(j.get("distance_jumped") or j.get("distance") or 0.0)
                route.append({
                    "system":   j.get("system", "?"),
                    "neutron":  bool(j.get("neutron_star", False)),
                    "distance": dist,
                })
            return route or None
        elif status == "error":
            _log.warning(f"Spansh route error: {data}")
            return None
        # else: still pending

    _log.warning(f"Spansh route timed out after {_SPANSH_TIMEOUT}s")
    return None


# ── Local route algorithm (fallback) ───────────────────────────────────────────

def _plan_route(
    db,
    src: tuple,
    dst: tuple,
    dst_name: str,
    jump_range: float,
) -> list[dict]:
    """Return list of jump dicts: {system, neutron, distance}."""
    boosted = jump_range * _NEUTRON_BOOST
    cx, cy, cz = src
    tx, ty, tz = dst

    route: list[dict] = []
    visited: set[str] = set()

    for _ in range(_MAX_JUMPS):
        dist_to_target = math.sqrt((cx-tx)**2 + (cy-ty)**2 + (cz-tz)**2)

        # Can we reach the target directly?
        if dist_to_target <= jump_range:
            route.append({"system": dst_name, "neutron": False,
                          "distance": round(dist_to_target, 2)})
            return route

        # Find neutron stars within boosted range
        candidates = _nearest_neutron_stars(db, cx, cy, cz, boosted, _BEAM_WIDTH, visited)

        # Only keep candidates that actually reduce remaining distance
        candidates = [
            c for c in candidates
            if math.sqrt((c["x"]-tx)**2 + (c["y"]-ty)**2 + (c["z"]-tz)**2) < dist_to_target
        ]
        if not candidates:
            # All nearby neutron stars are off-path — step directly toward target
            if dist_to_target > jump_range * 1.5:
                scale = jump_range / dist_to_target
                cx += (tx - cx) * scale
                cy += (ty - cy) * scale
                cz += (tz - cz) * scale
                route.append({"system": "", "neutron": False,
                              "distance": round(jump_range, 2)})
                continue
            else:
                route.append({"system": dst_name, "neutron": False,
                              "distance": round(dist_to_target, 2)})
                return route

        # Pick the star that minimises remaining distance to target
        best = min(
            candidates,
            key=lambda c: math.sqrt((c["x"]-tx)**2 + (c["y"]-ty)**2 + (c["z"]-tz)**2),
        )

        step_dist = math.sqrt(
            (cx - best["x"])**2 + (cy - best["y"])**2 + (cz - best["z"])**2
        )
        route.append({"system": best["name"], "neutron": True,
                      "distance": round(step_dist, 2)})
        visited.add(best["name"])
        cx, cy, cz = best["x"], best["y"], best["z"]

    # Exceeded safety cap
    return route


def _nearest_neutron_stars(
    db, cx: float, cy: float, cz: float,
    max_range: float, limit: int, visited: set,
) -> list[dict]:
    """Return up to *limit* neutron stars within *max_range* ly."""
    r2 = max_range * max_range
    with db._lock:
        rows = db._conn.execute(
            """SELECT name, x, y, z,
                      (x-?1)*(x-?1)+(y-?2)*(y-?2)+(z-?3)*(z-?3) AS dist2
               FROM neutron_stars
               WHERE x BETWEEN ?1-?4 AND ?1+?4
                 AND y BETWEEN ?2-?4 AND ?2+?4
                 AND z BETWEEN ?3-?4 AND ?3+?4
                 AND (x-?1)*(x-?1)+(y-?2)*(y-?2)+(z-?3)*(z-?3) <= ?5
               ORDER BY dist2
               LIMIT ?6""",
            (cx, cy, cz, max_range, r2, limit),
        ).fetchall()
    return [
        {"name": r[0], "x": r[1], "y": r[2], "z": r[3]}
        for r in rows
        if r[0] not in visited
    ]


def _lookup_system(db, name: str) -> Optional[tuple]:
    """Return (x, y, z) for *name* from edsm_systems, or None. Case-insensitive."""
    with db._lock:
        row = db._conn.execute(
            "SELECT x, y, z FROM edsm_systems WHERE name = ? COLLATE NOCASE LIMIT 1", (name,)
        ).fetchone()
    if row:
        return (float(row[0]), float(row[1]), float(row[2]))
    # Also check neutron_stars table
    with db._lock:
        row = db._conn.execute(
            "SELECT x, y, z FROM neutron_stars WHERE name = ? COLLATE NOCASE LIMIT 1", (name,)
        ).fetchone()
    if row:
        return (float(row[0]), float(row[1]), float(row[2]))
    return None


# ── DB table ───────────────────────────────────────────────────────────────────

def _ensure_table(db) -> None:
    with db._lock:
        try:
            db._conn.executescript("""
                CREATE TABLE IF NOT EXISTS neutron_stars (
                    name TEXT PRIMARY KEY,
                    x    REAL NOT NULL DEFAULT 0,
                    y    REAL NOT NULL DEFAULT 0,
                    z    REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_neutron_x ON neutron_stars(x);
                CREATE INDEX IF NOT EXISTS idx_neutron_y ON neutron_stars(y);
                CREATE INDEX IF NOT EXISTS idx_neutron_z ON neutron_stars(z);
                CREATE TABLE IF NOT EXISTS neutron_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            db._conn.commit()
        except Exception as exc:
            _log.debug(f"neutron table init: {exc}")


def _get_last_download(db) -> float:
    with db._lock:
        row = db._conn.execute(
            "SELECT value FROM neutron_meta WHERE key='last_download'"
        ).fetchone()
    return float(row[0]) if row else 0.0


def _set_last_download(db, ts: float) -> None:
    with db._lock:
        db._conn.execute(
            "INSERT OR REPLACE INTO neutron_meta(key,value) VALUES('last_download',?)",
            (str(ts),),
        )
        db._conn.commit()


# ── Dump download & import ─────────────────────────────────────────────────────

def _refresh_dump_if_needed(db) -> None:
    last = _get_last_download(db)
    if time.time() - last < _MAX_AGE:
        # Still fresh — but re-import if table is empty (e.g. previous import failed)
        with db._lock:
            count = db._conn.execute("SELECT COUNT(*) FROM neutron_stars").fetchone()[0]
        if count > 0:
            return
        _log.info("Neutron star table is empty despite recent download — re-importing.")
        _import_dump(db)
        return

    _log.info("Downloading neutron star dump from Spansh…")
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _DUMP_PATH.with_suffix(".tmp")
    try:
        req = urllib.request.Request(
            _DUMP_URL,
            headers={"User-Agent": "NOVA-ed-monitor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)  # 1 MB chunks
                    if not chunk:
                        break
                    f.write(chunk)
        tmp.replace(_DUMP_PATH)
        _log.info("Neutron star dump downloaded.")
    except Exception as exc:
        _log.warning(f"Neutron dump download failed: {exc}")
        tmp.unlink(missing_ok=True)
        return

    _import_dump(db)
    _set_last_download(db, time.time())


def _import_dump(db) -> None:
    """Parse gzip JSON dump and import into neutron_stars table."""
    _log.info("Importing neutron star data…")
    count = 0
    batch: list[tuple] = []
    _BATCH = 5_000

    def _flush():
        nonlocal count
        if not batch:
            return
        with db._lock:
            db._conn.executemany(
                "INSERT OR REPLACE INTO neutron_stars(name,x,y,z) VALUES(?,?,?,?)",
                batch,
            )
            db._conn.commit()
        count += len(batch)
        batch.clear()

    try:
        with gzip.open(_DUMP_PATH, "rt", encoding="utf-8") as f:
            # The file is a JSON array; stream it line by line for memory efficiency
            # Spansh dumps are newline-delimited arrays: "[", "{...}", ",{...}", "]"
            for line in f:
                line = line.strip()
                if not line or line in ("[", "]"):
                    continue
                if line.startswith(","):
                    line = line[1:]
                if line.endswith(","):
                    line = line[:-1]
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name   = obj.get("name") or obj.get("system", "")
                coords = obj.get("coords") or {}
                x = coords.get("x") if coords else None
                if x is None: x = obj.get("x")
                y = coords.get("y") if coords else None
                if y is None: y = obj.get("y")
                z = coords.get("z") if coords else None
                if z is None: z = obj.get("z")
                if name and x is not None:
                    batch.append((name, float(x), float(y), float(z)))
                    if len(batch) >= _BATCH:
                        _flush()
        _flush()
        _log.info(f"Neutron star import complete: {count} systems.")
    except Exception as exc:
        _log.warning(f"Neutron dump import failed: {exc}")
