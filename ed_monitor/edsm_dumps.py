"""EDSM nightly dump downloader and local cache.

Downloads systemsPopulated, stations, and powerPlay dumps from EDSM once per
day and stores them in the local SQLite database for offline lookup.

All three imports run in a single background daemon thread (nova-edsm-dumps).
On startup the thread waits 15 s to let the journal catch up, then checks
whether any dump is older than 24 hours. After that it re-checks every hour.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import re
import threading
import time
import urllib.request
import urllib.error
from typing import Optional

_log = logging.getLogger("nova.edsm_dumps")

_DUMPS = {
    "systems":   "https://www.edsm.net/dump/systemsPopulated.json.gz",
    "stations":  "https://www.edsm.net/dump/stations.json.gz",
    "powerplay": "https://www.edsm.net/dump/powerPlay.json.gz",
}

_MAX_AGE = 24 * 3600          # refresh once per 24 hours
_BATCH   = 500                 # rows per DB transaction
_UA      = "NOVA-ED-Monitor/1.0 (github.com/KernicDE/nova-ed-monitor)"
_TIMEOUT = 120                 # HTTP timeout in seconds


# ── Public API ─────────────────────────────────────────────────────────────────

def spawn(state, lock: threading.RLock, db) -> None:
    """Start the background dump-downloader thread."""
    threading.Thread(
        target=_run, args=(state, lock, db),
        daemon=True, name="nova-edsm-dumps",
    ).start()


# ── Background thread ──────────────────────────────────────────────────────────

def _run(state, lock: threading.RLock, db) -> None:
    time.sleep(15)  # let journal init complete first
    while True:
        _check_and_refresh(state, lock, db)
        time.sleep(3600)  # re-check every hour


def _check_and_refresh(state, lock, db) -> None:
    from .state import EventCategory, LogEvent

    def _push(msg: str) -> None:
        with lock:
            state.push_event(LogEvent.new(EventCategory.System, msg))

    now = time.time()
    any_outdated = False
    for name in ("systems", "stations", "powerplay"):
        key = f"edsm_dump_{name}_ts"
        try:
            last_ts = float(db.get_config(key, "0"))
        except ValueError:
            last_ts = 0.0
        if now - last_ts > _MAX_AGE:
            any_outdated = True
            _download_and_import(name, state, lock, db)

    if not any_outdated:
        # All three dumps are within the 24-hour window — let the user know
        oldest_ts = min(
            _safe_ts(db.get_config(f"edsm_dump_{n}_ts", "0"))
            for n in ("systems", "stations", "powerplay")
        )
        age_h = int((now - oldest_ts) / 3600)
        _push(f"EDSM: data up to date (refreshed {age_h}h ago).")


def _safe_ts(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _download_and_import(name: str, state, lock, db) -> None:
    from .state import EventCategory, LogEvent

    url = _DUMPS[name]

    def _push(msg: str) -> None:
        with lock:
            state.push_event(LogEvent.new(EventCategory.System, msg))

    _log.info(f"Downloading EDSM {name} dump")
    _push(f"EDSM: downloading {name} dump…")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if name == "systems":
                count = _import_systems(resp, db)
            elif name == "stations":
                count = _import_stations(resp, db)
            elif name == "powerplay":
                count = _import_powerplay(resp, db)
            else:
                count = 0
        db.set_config(f"edsm_dump_{name}_ts", str(time.time()))
        _log.info(f"EDSM {name} import done ({count:,} records)")
        _push(f"EDSM: {name} import done ({count:,} records).")
    except urllib.error.HTTPError as e:
        _log.warning(f"EDSM {name} download failed — HTTP {e.code}")
        _push(f"EDSM: {name} download failed — HTTP {e.code}")
    except Exception as e:
        _log.warning(f"EDSM {name} download failed — {e}")
        _push(f"EDSM: {name} download failed — {str(e)[:60]}")


# ── Stream parsers ─────────────────────────────────────────────────────────────

def _iter_records(resp):
    """Yield parsed JSON objects from an EDSM nightly dump (line-per-object format)."""
    with gzip.open(resp) as gz:
        for line_bytes in gz:
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line or line in ("[", "]"):
                continue
            if line.endswith(","):
                line = line[:-1]
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    yield obj
            except json.JSONDecodeError:
                continue


def _import_systems(resp, db) -> int:
    """Import systemsPopulated dump → edsm_systems (INSERT OR REPLACE)."""
    batch: list = []
    count = 0
    for rec in _iter_records(resp):
        coords = rec.get("coords") or {}
        row = (
            int(rec.get("id64") or rec.get("id") or 0),
            _s(rec.get("name")),
            float(coords.get("x") or 0.0),
            float(coords.get("y") or 0.0),
            float(coords.get("z") or 0.0),
            _s(rec.get("allegiance")),
            _s(rec.get("government")),
            _clean_economy(rec.get("economy")),
            int(rec.get("population") or 0),
            _clean_security(rec.get("security")),
            _s(rec.get("power")),
            _s(rec.get("powerState")),
        )
        batch.append(row)
        if len(batch) >= _BATCH:
            db.import_edsm_systems_batch(batch)
            count += len(batch)
            batch.clear()
    if batch:
        db.import_edsm_systems_batch(batch)
        count += len(batch)
    return count


def _import_stations(resp, db) -> int:
    """Import stations dump → edsm_stations (INSERT OR REPLACE)."""
    batch: list = []
    count = 0
    for rec in _iter_records(resp):
        other = rec.get("otherServices") or []
        services = "|".join(str(s) for s in other) if isinstance(other, list) else ""
        row = (
            int(rec.get("id") or 0),
            _s(rec.get("name")),
            int(rec.get("systemId64") or rec.get("systemId") or 0),
            _s(rec.get("systemName")),
            _s(rec.get("type")),
            float(rec.get("distanceToArrival") or 0.0),
            _s(rec.get("allegiance")),
            _s(rec.get("government")),
            _clean_economy(rec.get("economy")),
            int(bool(rec.get("haveMarket"))),
            int(bool(rec.get("haveShipyard"))),
            int(bool(rec.get("haveOutfitting"))),
            services,
        )
        batch.append(row)
        if len(batch) >= _BATCH:
            db.import_edsm_stations_batch(batch)
            count += len(batch)
            batch.clear()
    if batch:
        db.import_edsm_stations_batch(batch)
        count += len(batch)
    return count


def _import_powerplay(resp, db) -> int:
    """Import powerPlay dump → upsert into edsm_systems (insert new, update power fields only)."""
    batch: list = []
    count = 0
    for rec in _iter_records(resp):
        coords = rec.get("coords") or {}
        row = (
            int(rec.get("id64") or rec.get("id") or 0),
            _s(rec.get("name")),
            float(coords.get("x") or 0.0),
            float(coords.get("y") or 0.0),
            float(coords.get("z") or 0.0),
            _s(rec.get("allegiance")),
            _s(rec.get("government")),
            "",   # economy not present in powerplay dump
            0,    # population not present in powerplay dump
            "",   # security not present in powerplay dump
            _s(rec.get("power")),
            _s(rec.get("powerState")),
        )
        batch.append(row)
        if len(batch) >= _BATCH:
            db.upsert_edsm_powerplay_batch(batch)
            count += len(batch)
            batch.clear()
    if batch:
        db.upsert_edsm_powerplay_batch(batch)
        count += len(batch)
    return count


# ── Data cleanup helpers ───────────────────────────────────────────────────────

def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _clean_economy(v) -> str:
    s = _s(v).strip("$; ")
    if s.startswith("economy_"):
        s = s[8:]
    # CamelCase → "Camel Case"
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return s


def _clean_security(v) -> str:
    s = _s(v).strip("$; ").upper()
    for pfx in ("SYSTEM_SECURITY_",):
        if s.startswith(pfx):
            s = s[len(pfx):]
    return s.title()
