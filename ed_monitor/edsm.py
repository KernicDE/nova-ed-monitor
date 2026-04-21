from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from .state import AppState, BodyInfo, LogEvent, EventCategory
from .tts import TtsMsg

_log = logging.getLogger("nova.edsm")


def spawn(state: AppState, lock: threading.RLock, tts_q: queue.Queue) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    t = threading.Thread(target=_run, args=(q, state, lock, tts_q), daemon=True)
    t.start()
    return q


def _run(q: queue.Queue, state: AppState, lock: threading.RLock, tts_q: queue.Queue) -> None:
    from . import events as _ev
    from . import voicelines as _vl
    import httpx
    _UA = "nova-ed-monitor (Elite Dangerous companion; github.com/KernicDE/nova-ed-monitor)"
    client = httpx.Client(timeout=15.0, headers={"User-Agent": _UA})

    try:
        while True:
            # Drain queue and deduplicate by (kind, system)
            pending: dict[tuple, None] = {}
            try:
                msg = q.get(timeout=1.0)
                pending[msg] = None
            except queue.Empty:
                continue

            # Drain remaining without blocking
            while True:
                try:
                    msg = q.get_nowait()
                    pending[msg] = None
                except queue.Empty:
                    break

            # Execute each unique request
            for kind, system in pending:
                _log.debug(f"EDSM request: {kind} for '{system}'")
                try:
                    if kind in ("fetch_system", "fetch_system_silent"):
                        data   = _fetch_system_data(client, system, state, lock)
                        bodies = data.get("bodies") if data is not None else None

                        # Only announce "unknown to EDSM" for live jumps, not on startup,
                        # and only when the API actually responded (data is not None).
                        if kind == "fetch_system" and data is not None:
                            known = data.get("id64") is not None
                            with lock:
                                current_system    = state.system
                                already_announced = state.system_edsm_known is not None

                            if current_system.lower() == system.lower() and not already_announced:
                                with lock:
                                    state.system_edsm_known = known
                                    if not known:
                                        state.push_event(LogEvent.new(
                                            EventCategory.System, "System unknown to EDSM."
                                        ))
                                if not known:
                                    lang  = _ev._TTS_LANG
                                    voice = _ev._LANG_VOICES.get(lang) if lang != "en" else None
                                    if not _vl.is_muted("System_EDSM_Unknown", lang=lang):
                                        text  = _vl.pick("System_EDSM_Unknown", lang=lang) or "System unknown to EDSM."
                                        try:
                                            tts_q.put_nowait(TtsMsg(text=text, priority=False, voice=voice))
                                        except Exception:
                                            pass

                        if bodies:
                            _merge_bodies(state, lock, bodies)
                            _log.debug(f"EDSM merged {len(bodies)} body/bodies for '{system}'")
                    elif kind == "fetch_stations":
                        count = _fetch_station_count(client, system, state, lock)
                        with lock:
                            state.station_count = count
                except Exception as exc:
                    _log.warning(f"EDSM {kind} error for '{system}': {exc}")
                time.sleep(0.5)

    finally:
        client.close()


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _url_encode(s: str) -> str:
    return quote(s, safe="")


def _fetch_system_data(
    client: "httpx.Client",
    system: str,
    state:  AppState,
    lock:   threading.RLock,
) -> Optional[dict]:
    """Fetch system bodies from EDSM.

    Returns the API response dict on success (id64 will be None when EDSM
    genuinely does not know the system), or None on network/HTTP error.
    Callers must treat None as "no determination possible".
    """
    enc     = _url_encode(system)
    tx_time = _now_hms()
    try:
        resp = client.get(f"https://www.edsm.net/api-system-v1/bodies?systemName={enc}")
        rx_time = _now_hms()
        data    = resp.json()
        with lock:
            state.edsm_status.last_tx    = tx_time
            state.edsm_status.last_rx    = rx_time
            state.edsm_status.connected  = True
            state.edsm_status.last_error = None
        return data if isinstance(data, dict) else None
    except Exception as e:
        with lock:
            state.edsm_status.last_tx    = tx_time
            state.edsm_status.last_error = _fmt_err(e)
        return None  # network/parse error — cannot determine EDSM status


def _fetch_station_count(
    client: "httpx.Client",
    system: str,
    state:  AppState,
    lock:   threading.RLock,
) -> int:
    enc = _url_encode(system)
    try:
        resp     = client.get(f"https://www.edsm.net/api-system-v1/stations?systemName={enc}")
        data     = resp.json()
        stations = data.get("stations", []) if isinstance(data, dict) else []
        return len(stations) if isinstance(stations, list) else 0
    except Exception:
        return 0


def _merge_bodies(state: AppState, lock: threading.RLock, bodies: list) -> None:
    with lock:
        for body in bodies:
            if not isinstance(body, dict):
                continue
            name = body.get("name", "")
            if not name:
                continue

            body_id   = int(body.get("bodyId", 0))
            btype     = body.get("type", "")
            sub_type  = body.get("subType", "")
            dist_ls   = float(body.get("distanceToArrival", 0.0))
            landable  = bool(body.get("isLandable", False))
            terr_raw  = body.get("terraformingState", "")
            terraform = terr_raw in ("Candidate for terraforming", "Terraformable", "Terraforming")
            atm       = body.get("atmosphereType", "")
            if isinstance(atm, str) and ("No atmosphere" in atm or not atm):
                atm = ""
            value = int(body.get("valueMax") or body.get("estimatedValue") or 0)

            if btype == "Star":
                level = 0
            else:
                parents = body.get("parents", [])
                level   = 2 if (
                    isinstance(parents, list) and parents
                    and isinstance(parents[0], dict)
                    and next(iter(parents[0]), "") == "Planet"
                ) else 1

            if btype == "Star":
                star_type    = _edsm_star_type(sub_type)
                if not star_type:
                    continue
                planet_class = ""
            else:
                planet_class = _edsm_planet_class(sub_type)
                if not planet_class:
                    continue
                star_type = ""

            _eidx = state._bodies_by_name.get(name, -1)
            found = 0 <= _eidx < len(state.bodies)
            if found:
                b = state.bodies[_eidx]
                if b.dist_ls == 0.0 and dist_ls > 0.0:
                    b.dist_ls = dist_ls
                # Only fill in type from EDSM if player hasn't scanned
                if not b.planet_class and not b.star_type:
                    b.planet_class = planet_class
                    b.star_type    = star_type
                # Fill value only if player hasn't FSS'd this body yet
                if b.value == 0 and value > 0 and not b.fss_scanned:
                    b.value = value

            if not found:
                state.upsert_body(BodyInfo(
                    name=name, body_id=body_id, level=level,
                    planet_class=planet_class, star_type=star_type, atmosphere=atm,
                    terraform=terraform, landable=landable,
                    bio_signals=0, geo_signals=0, bio_genuses=[],
                    dist_ls=dist_ls, value=value,
                    first_discovered=False, first_mapped=False,
                    mapped=False, fss_scanned=False, radius=0.0,
                ))


def _edsm_star_type(sub: str) -> str:
    if "Neutron"     in sub: return "N"
    if "Black Hole"  in sub: return "H"
    if "White Dwarf" in sub: return "D"
    if sub.startswith("O"): return "O"
    if sub.startswith("B"): return "B"
    if sub.startswith("A"): return "A"
    if sub.startswith("F"): return "F"
    if sub.startswith("G"): return "G"
    if sub.startswith("K"): return "K"
    if sub.startswith("M"): return "M"
    if sub.startswith("L"): return "L"
    if sub.startswith("T"): return "T"
    if sub.startswith("Y"): return "Y"
    return ""


def _edsm_planet_class(sub: str) -> str:
    return {
        "Earthlike world":                   "Earthlike body",
        "Water world":                        "Water world",
        "Ammonia world":                      "Ammonia world",
        "High metal content world":           "High metal content body",
        "Metal-rich body":                    "Metal rich body",
        "Rocky body":                         "Rocky body",
        "Rocky ice world":                    "Rocky ice body",
        "Icy body":                           "Icy body",
        "Class I gas giant":                  "Sudarsky class I gas giant",
        "Class II gas giant":                 "Sudarsky class II gas giant",
        "Class III gas giant":                "Sudarsky class III gas giant",
        "Class IV gas giant":                 "Sudarsky class IV gas giant",
        "Class V gas giant":                  "Sudarsky class V gas giant",
        "Helium-rich gas giant":              "Helium rich gas giant",
        "Gas giant with water-based life":    "Gas giant with water-based life",
        "Gas giant with ammonia-based life":  "Gas giant with ammonia-based life",
    }.get(sub, "")


def _fmt_err(e: Exception) -> str:
    if hasattr(e, "response") and e.response is not None:
        return f"HTTP {e.response.status_code}"
    return "Network error"
