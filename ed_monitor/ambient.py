"""
NOVA Ambient Commentary — periodic, unprompted situational remarks.

Fires roughly every ambient_interval_min_s..ambient_interval_max_s seconds
(randomised) with a short AI-generated remark about the current situation.
Requires voice_engine != "static" — meaningless without AI generation, so
when static is active this thread simply idles (still spawned unconditionally
via _spawn_guarded, matching the twitch/youtube convention: config checked
inside the loop, not at the spawn call site).

Toggle: ambient_commentary_enabled in config.toml / Settings overlay.
"""
from __future__ import annotations

import logging
import random
import threading
import time

from . import ai_voice

_log = logging.getLogger("nova.ambient")

_CHUNK_S = 5.0   # sleep granularity — lets toggling off / stop_evt take effect promptly


def _sleep_chunked(total_s: float, stop_evt: threading.Event, is_still_enabled) -> bool:
    """Sleep for total_s seconds in small chunks. Returns False if interrupted
    (stop requested or config disabled mid-wait), True if slept to completion."""
    remaining = total_s
    while remaining > 0:
        if stop_evt.is_set() or not is_still_enabled():
            return False
        time.sleep(min(_CHUNK_S, remaining))
        remaining -= _CHUNK_S
    return True


def _snapshot_situation(state, lock) -> dict:
    """Build a compact situation summary from AppState under the RLock."""
    with lock:
        summary = {
            "system": state.system,
            "commander": state.commander,
            "ship": state.ship_type or state.ship_name,
            "docked": state.docked,
            "landed": state.landed,
            "supercruise": state.supercruise,
            "station": state.station,
            "fuel_percent": round(state.fuel / state.fuel_max * 100) if state.fuel_max else None,
            "cargo": state.cargo,
            "cargo_capacity": state.cargo_capacity,
            "nearest_body": state.nearest_body,
            "hull_percent": round(state.hull * 100),
            "low_fuel": state.low_fuel,
            "overheating": state.overheating,
            "in_srv": state.in_srv,
            "mission_count": len(state.missions),
        }
    return {k: v for k, v in summary.items() if v not in (None, "", 0, False)}


def monitor(state, lock, tts_q, cfg_getter, stop_evt: threading.Event) -> None:
    """Daemon thread entry point (registered via _spawn_guarded as 'nova-ambient')."""
    while not stop_evt.is_set():
        cfg = cfg_getter()

        def _enabled() -> bool:
            c = cfg_getter()
            return bool(c.ambient_commentary_enabled) and c.voice_engine != "static"

        if not _enabled():
            if not _sleep_chunked(_CHUNK_S, stop_evt, lambda: True):
                continue
            continue

        interval = random.uniform(cfg.ambient_interval_min_s, cfg.ambient_interval_max_s)
        if not _sleep_chunked(interval, stop_evt, _enabled):
            continue  # disabled or stopped mid-wait — re-check from the top

        if stop_evt.is_set() or not _enabled():
            continue

        situation = _snapshot_situation(state, lock)
        details = ", ".join(f"{k}={v}" for k, v in situation.items())
        ai_voice.submit(ai_voice.AiVoiceRequest(
            prompt_intent="Make a brief, unprompted remark about the current situation.",
            context=situation,
            fallback_text="",   # AI-only feature — say nothing if generation fails
            priority=False,
            cacheable=False,
            groupable=False,
        ))
        _log.debug("Ambient commentary requested: %s", details)
