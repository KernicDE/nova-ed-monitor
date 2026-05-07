"""Tests for status.py polling rate logic (fast vs slow)."""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

import pytest

from ed_monitor.state import AppState
from ed_monitor.status import _apply_status, FLAG_IN_MAIN_SHIP, FLAG_IN_SRV, FLAG_LANDED


def _write_status(tmp_path: Path, **kwargs) -> Path:
    data = {
        "Flags": kwargs.get("flags", 0),
        "Flags2": 0,
        "Fuel": {"FuelMain": kwargs.get("fuel", 50.0)},
    }
    if "altitude" in kwargs:
        data["Altitude"] = kwargs["altitude"]
    if "latitude" in kwargs:
        data["Latitude"] = kwargs["latitude"]
    if "longitude" in kwargs:
        data["Longitude"] = kwargs["longitude"]
    path = tmp_path / "Status.json"
    path.write_text(json.dumps(data))
    return path


def _fast_poll(state: AppState) -> bool:
    """Mirror the _fast_poll_cache logic from status.py monitor loop."""
    _near_surface = (
        state.landed or state.in_srv or
        state.lat is not None or state.altitude is not None or
        (not state.in_main_ship and not state.in_srv)
    )
    return state.client_online and _near_surface


class TestPollRate:
    def test_deep_space_slow_poll(self, tmp_path: Path):
        """In deep space (no lat/lon/alt) the poll rate should be slow."""
        state = AppState()
        state.in_main_ship = True
        state.client_online = True
        path = _write_status(tmp_path, flags=FLAG_IN_MAIN_SHIP)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert state.lat is None
        assert state.altitude is None
        assert _fast_poll(state) is False

    def test_orbital_cruise_fast_poll(self, tmp_path: Path):
        """Orbital cruise has altitude → fast poll."""
        state = AppState()
        state.in_main_ship = True
        state.client_online = True
        path = _write_status(tmp_path, flags=FLAG_IN_MAIN_SHIP, altitude=15000.0)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert state.altitude == 15000.0
        assert _fast_poll(state) is True

    def test_near_surface_fast_poll(self, tmp_path: Path):
        """Near-surface flight with lat/lon → fast poll."""
        state = AppState()
        state.in_main_ship = True
        state.client_online = True
        path = _write_status(tmp_path, flags=FLAG_IN_MAIN_SHIP, latitude=10.5, longitude=-20.3)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert state.lat == 10.5
        assert _fast_poll(state) is True

    def test_landed_fast_poll(self, tmp_path: Path):
        """Landed state → fast poll regardless of position data."""
        state = AppState()
        state.landed = True
        state.client_online = True
        path = _write_status(tmp_path, flags=FLAG_LANDED)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert _fast_poll(state) is True

    def test_srv_fast_poll(self, tmp_path: Path):
        """SRV state → fast poll."""
        state = AppState()
        state.in_srv = True
        state.client_online = True
        path = _write_status(tmp_path, flags=FLAG_IN_SRV)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert _fast_poll(state) is True

    def test_on_foot_fast_poll(self, tmp_path: Path):
        """On-foot state → fast poll."""
        state = AppState()
        state.client_online = True
        # on-foot = not in ship and not in SRV
        state.in_main_ship = False
        state.in_srv = False
        # On-foot = no ship flags set
        path = _write_status(tmp_path, flags=0)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert _fast_poll(state) is True

    def test_offline_slow_poll(self, tmp_path: Path):
        """Offline state → slow poll."""
        state = AppState()
        state.client_online = False
        state.landed = True
        path = _write_status(tmp_path, flags=FLAG_LANDED)
        _apply_status(path, state, threading.RLock(), queue.Queue())
        assert _fast_poll(state) is False
