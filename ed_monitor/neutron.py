"""Neutron star route planner — Spansh API only.

Submits an async job to the Spansh neutron router and polls until the result
arrives. Every system in the Spansh response (boosted and non-boosted) is
forwarded to the UI as-is.

Queue messages: ("plot", target_system_name)
State written: neutron_route, neutron_route_to, neutron_route_status
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from .state import AppState

_log = logging.getLogger("nova.neutron")

_SPANSH_ROUTE_URL   = "https://spansh.co.uk/api/route"
_SPANSH_RESULTS_URL = "https://spansh.co.uk/api/results/{}"
_SPANSH_TIMEOUT     = 120   # seconds to wait for result


def spawn(state: AppState, lock: threading.RLock) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    threading.Thread(
        target=_worker,
        args=(q, state, lock),
        daemon=True,
        name="nova-neutron",
    ).start()
    return q


# ── Worker ─────────────────────────────────────────────────────────────────────

def _worker(q: queue.Queue, state: AppState, lock: threading.RLock) -> None:
    while True:
        try:
            msg = q.get(timeout=300.0)
        except queue.Empty:
            continue

        if not isinstance(msg, tuple) or len(msg) < 2 or msg[0] != "plot":
            continue

        target_name: str = msg[1]
        if not target_name:
            continue

        with lock:
            jump_range = state.jump_range_last if state.jump_range_last > 0 else state.jump_range
            cur_system = state.system

        if not cur_system or jump_range <= 0.0:
            with lock:
                state.neutron_route_status = "error"
                state.neutron_route        = []
                state.neutron_route_to     = target_name
            _log.warning("Neutron plotter: no system or jump range available.")
            continue

        with lock:
            state.neutron_route_status = "plotting"
            state.neutron_route        = []
            state.neutron_route_to     = target_name

        _log.info(f"Neutron plotter: {cur_system} → {target_name}  range={jump_range:.1f} ly")

        route = _spansh_route(cur_system, target_name, jump_range)

        with lock:
            state.neutron_route        = route or []
            state.neutron_route_to     = target_name
            state.neutron_route_status = "done" if route else "error"

        _log.info(f"Neutron plotter: {len(route) if route else 0} hops.")


# ── Spansh API ─────────────────────────────────────────────────────────────────

def _spansh_route(src: str, dst: str, jump_range: float) -> Optional[list[dict]]:
    """Submit neutron route job to Spansh, poll until done.
    Returns list of {system, neutron, distance} or None on failure."""

    params = urllib.parse.urlencode({
        "from":       src,
        "to":         dst,
        "efficiency": 60,
        "range":      f"{jump_range:.2f}",
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
            _log.warning(f"Spansh: unexpected submit response: {data}")
            return None
    except Exception as exc:
        _log.warning(f"Spansh submit failed: {exc}")
        return None

    _log.info(f"Spansh job: {job_id}")
    poll_url = _SPANSH_RESULTS_URL.format(job_id)

    for _ in range(_SPANSH_TIMEOUT):
        time.sleep(1.0)
        try:
            req = urllib.request.Request(poll_url, headers={"User-Agent": "NOVA-ed-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            _log.debug(f"Spansh poll error: {exc}")
            continue

        status = data.get("status", "")
        if status == "ok":
            jumps = (data.get("result") or {}).get("system_jumps") or []
            _log.info(f"Spansh done: {len(jumps)} hops")
            route = []
            for j in jumps:
                dist = float(j.get("distance_jumped") or j.get("distance") or 0.0)
                route.append({
                    "system":   j.get("system", "?"),
                    "neutron":  bool(j.get("neutron_star", False)),
                    "distance": dist,
                    "jumps":    int(j.get("jumps") or 0),  # regular hops to reach this waypoint
                })
            return route or None
        elif status == "error":
            _log.warning(f"Spansh error: {data}")
            return None

    _log.warning(f"Spansh timed out after {_SPANSH_TIMEOUT}s")
    return None
