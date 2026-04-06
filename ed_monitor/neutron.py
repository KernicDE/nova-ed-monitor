"""Neutron star route planner.

Downloads the Spansh neutron-star dump (systems_neutron.json.gz) once per day,
stores positions in a local SQLite table, and computes routes locally using a
greedy A* / beam-search approach — no live API calls needed.

Route quality is good for most journeys. The algorithm:
  1. From current position, find all neutron stars within 4× jump range
     (neutron boost = 4× fuel-optimal range).
  2. Score candidates by: progress toward target / distance from current.
  3. Pick the best candidate; repeat until the target is within 1× jump range.
  4. Append the final jump to target.

Receives messages via queue: ("plot", target_system_name).
Writes results to state.neutron_route / neutron_route_to / neutron_route_status.
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
_BEAM_WIDTH    = 20      # candidates evaluated per step
_MAX_JUMPS     = 2_000   # safety cap


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

    while True:
        try:
            msg = q.get(timeout=60.0)
        except queue.Empty:
            # Periodic refresh check
            _refresh_dump_if_needed(db)
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

        # Look up target coords
        target_pos = _lookup_system(db, target_name)
        if target_pos is None:
            with lock:
                state.neutron_route_status = "error"
                state.neutron_route        = []
                state.neutron_route_to     = target_name
            _log.warning(f"Neutron plotter: target '{target_name}' not found in EDSM data.")
            continue

        with lock:
            state.neutron_route_status = "plotting"
            state.neutron_route        = []
            state.neutron_route_to     = target_name

        _log.info(f"Neutron plotter: {cur_system} → {target_name}  range={jump_range:.1f} ly")

        route = _plan_route(db, star_pos, target_pos, target_name, jump_range)

        with lock:
            state.neutron_route        = route
            state.neutron_route_to     = target_name
            state.neutron_route_status = "done" if route else "error"

        _log.info(f"Neutron plotter: {len(route)} jumps planned.")


# ── Route algorithm ────────────────────────────────────────────────────────────

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

        # Find neutron stars within boosted range that make progress
        candidates = _nearest_neutron_stars(db, cx, cy, cz, boosted, _BEAM_WIDTH, visited)

        if not candidates:
            # No neutron stars in range — try regular jump toward target
            # (step ~jump_range ly toward target)
            if dist_to_target > jump_range * 1.5:
                route.append({"system": f"(direct jump)", "neutron": False,
                              "distance": round(jump_range, 2)})
                # Move current position jump_range toward target
                scale = jump_range / dist_to_target
                cx += (tx - cx) * scale
                cy += (ty - cy) * scale
                cz += (tz - cz) * scale
                continue
            else:
                route.append({"system": dst_name, "neutron": False,
                              "distance": round(dist_to_target, 2)})
                return route

        # Score: progress toward target (maximise)
        # dot product of step vector with target direction
        tx_n = (tx - cx); ty_n = (ty - cy); tz_n = (tz - cz)
        tlen = math.sqrt(tx_n**2 + ty_n**2 + tz_n**2) or 1.0

        best = max(
            candidates,
            key=lambda c: (
                (c["x"] - cx) * tx_n / tlen
                + (c["y"] - cy) * ty_n / tlen
                + (c["z"] - cz) * tz_n / tlen
            ),
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
    """Return (x, y, z) for *name* from edsm_systems, or None."""
    with db._lock:
        row = db._conn.execute(
            "SELECT x, y, z FROM edsm_systems WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
    if row:
        return (float(row[0]), float(row[1]), float(row[2]))
    # Also check neutron_stars table
    with db._lock:
        row = db._conn.execute(
            "SELECT x, y, z FROM neutron_stars WHERE name = ? LIMIT 1", (name,)
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
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name   = obj.get("name", "") or obj.get("system", "")
                coords = obj.get("coords") or {}
                x = coords.get("x")
                y = coords.get("y")
                z = coords.get("z")
                if name and x is not None:
                    batch.append((name, float(x), float(y), float(z)))
                    if len(batch) >= _BATCH:
                        _flush()
        _flush()
        _log.info(f"Neutron star import complete: {count} systems.")
    except Exception as exc:
        _log.warning(f"Neutron dump import failed: {exc}")
