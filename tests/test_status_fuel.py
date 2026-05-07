"""Tests for status.py fuel warning logic."""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

import pytest

from ed_monitor.state import AppState, EventCategory
from ed_monitor.status import _apply_status


def _write_status(tmp_path: Path, fuel: float, fuel_max: float | None = None) -> Path:
    data: dict = {"Flags": 0, "Flags2": 0, "Fuel": {"FuelMain": fuel}}
    if fuel_max is not None:
        data["Fuel"]["FuelMainCapacity"] = fuel_max
    path = tmp_path / "Status.json"
    path.write_text(json.dumps(data))
    return path


def test_fuel_warning_triggers_when_below_threshold(tmp_path: Path):
    state = AppState()
    state.fuel_max = 100.0
    state.fuel_warning_percent = 25
    tts_q: queue.Queue = queue.Queue()
    path = _write_status(tmp_path, 20.0)

    _apply_status(path, state, threading.RLock(), tts_q)

    assert state.fuel_low_announced is True
    assert not tts_q.empty()
    msg = tts_q.get_nowait()
    assert "LowFuel" in str(msg) or "low fuel" in str(msg).lower()
    assert state.events
    assert "Low fuel" in state.events[0].message


def test_fuel_warning_silenced_when_disabled(tmp_path: Path):
    state = AppState()
    state.fuel_max = 100.0
    state.fuel_warning_percent = 0
    tts_q: queue.Queue = queue.Queue()
    path = _write_status(tmp_path, 5.0)

    _apply_status(path, state, threading.RLock(), tts_q)

    assert state.fuel_low_announced is False
    assert tts_q.empty()


def test_fuel_warning_not_repeated_until_refueled(tmp_path: Path):
    state = AppState()
    state.fuel_max = 100.0
    state.fuel_warning_percent = 25
    tts_q: queue.Queue = queue.Queue()
    lock = threading.RLock()

    # First call — below threshold, should trigger
    _apply_status(_write_status(tmp_path, 20.0), state, lock, tts_q)
    assert state.fuel_low_announced is True
    tts_q.get_nowait()  # drain

    # Second call — still below threshold, should NOT trigger again
    _apply_status(_write_status(tmp_path, 18.0), state, lock, tts_q)
    assert state.fuel_low_announced is True
    assert tts_q.empty()


def test_fuel_warning_resets_when_refueled(tmp_path: Path):
    state = AppState()
    state.fuel_max = 100.0
    state.fuel_warning_percent = 25
    tts_q: queue.Queue = queue.Queue()
    lock = threading.RLock()

    _apply_status(_write_status(tmp_path, 20.0), state, lock, tts_q)
    assert state.fuel_low_announced is True
    tts_q.get_nowait()

    # Refuel above threshold
    _apply_status(_write_status(tmp_path, 80.0), state, lock, tts_q)
    assert state.fuel_low_announced is False
    assert tts_q.empty()

    # Drop again — should re-trigger
    _apply_status(_write_status(tmp_path, 20.0), state, lock, tts_q)
    assert state.fuel_low_announced is True
    assert not tts_q.empty()
