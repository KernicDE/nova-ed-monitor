"""Spansh API integration — fleet carrier lookup for current system.

Spawns a background thread that handles requests from a queue.
API: POST https://spansh.co.uk/api/stations/search
Rate limiting: minimum 3 s between requests; results cached for 300 s per system.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from .state import AppState

_API_URL   = "https://spansh.co.uk/api/stations/search"
_CACHE_TTL = 300.0   # seconds before a cached result is considered stale
_MIN_DELAY = 3.0     # minimum seconds between API calls


def spawn(state: AppState, lock: threading.RLock) -> queue.Queue:
    """Spawn the Spansh worker thread and return its request queue."""
    q: queue.Queue = queue.Queue()
    threading.Thread(
        target=_worker,
        args=(q, state, lock),
        daemon=True,
        name="nova-spansh",
    ).start()
    return q


def _worker(q: queue.Queue, state: AppState, lock: threading.RLock) -> None:
    # cache: system_name → (timestamp, list[dict])
    cache: dict[str, tuple[float, list]] = {}
    last_request_time: float = 0.0

    while True:
        try:
            msg = q.get(timeout=60.0)
        except queue.Empty:
            continue

        if not isinstance(msg, tuple) or len(msg) < 2:
            continue

        kind, system_name = msg[0], msg[1]
        if kind != "fetch_carriers" or not system_name:
            continue

        # Serve from cache if fresh
        now = time.monotonic()
        cached = cache.get(system_name)
        if cached is not None and (now - cached[0]) < _CACHE_TTL:
            with lock:
                state.carriers_current_system = cached[1]
            continue

        # Rate limiting: wait until at least _MIN_DELAY seconds since last call
        elapsed = now - last_request_time
        if elapsed < _MIN_DELAY:
            time.sleep(_MIN_DELAY - elapsed)

        carriers = _fetch_carriers(system_name)
        last_request_time = time.monotonic()

        cache[system_name] = (time.monotonic(), carriers)
        with lock:
            # Only update state if the player is still in the same system
            if state.system == system_name:
                state.carriers_current_system = carriers


def _fetch_carriers(system_name: str) -> list[dict]:
    # Try current system first; if empty, fall back to nearest N carriers galaxy-wide
    carriers = _fetch_carriers_query(system_name=system_name, size=10)
    if not carriers:
        carriers = _fetch_carriers_query(system_name=None, reference_system=system_name, size=20)
    return carriers


def _fetch_carriers_query(
    *,
    system_name: Optional[str] = None,
    reference_system: Optional[str] = None,
    size: int = 10,
) -> list[dict]:
    body: dict = {"type": "Drake-Class Carrier", "size": size}
    if system_name:
        body["system_name"] = system_name
    if reference_system:
        body["reference_system"] = reference_system

    payload = json.dumps(body).encode()

    req = urllib.request.Request(
        _API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "NOVA-ed-monitor/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return []

    results = data.get("results", [])
    carriers = []
    for r in results:
        name       = r.get("name", "")
        dist_ls    = r.get("distance_to_arrival") or 0.0
        updated_at = r.get("updated_at", "")
        sys_name   = r.get("system_name", "")
        sys_x      = float(r.get("system_x") or 0.0)
        sys_y      = float(r.get("system_y") or 0.0)
        sys_z      = float(r.get("system_z") or 0.0)
        market     = bool(r.get("has_market"))
        shipyard   = bool(r.get("has_shipyard"))
        outfitting = bool(r.get("has_outfitting"))
        if name:
            carriers.append({
                "name":        name,
                "system_name": sys_name,
                "dist_ls":     float(dist_ls),
                "updated_at":  updated_at,
                "sys_x":       sys_x,
                "sys_y":       sys_y,
                "sys_z":       sys_z,
                "market":      market,
                "shipyard":    shipyard,
                "outfitting":  outfitting,
            })
    return carriers
