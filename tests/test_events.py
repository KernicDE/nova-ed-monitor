"""Tests for event handler helpers."""
from __future__ import annotations

import queue
import pytest
from ed_monitor.events import _fmt_credits, handle
from ed_monitor.state import AppState, EventCategory


def test_fmt_credits_basic():
    assert _fmt_credits(0) == "0 Cr"
    assert _fmt_credits(1000) == "1,000 Cr"
    assert _fmt_credits(1_234_567) == "1,234,567 Cr"
    assert _fmt_credits(500) == "500 Cr"


def test_fsd_jump_clears_bodies():
    state = AppState()
    q: queue.Queue = queue.Queue()
    # Simulate a Location event to set a system
    loc_ev = {
        "event": "Location",
        "StarSystem": "Sol",
        "SystemAddress": 10477373803,
        "StarPos": [0.0, 0.0, 0.0],
        "Population": 22780000000,
        "Economy": "$economy_Industrial;",
        "Government": "$government_Democracy;",
        "Allegiance": "Federation",
        "Security": "$SYSTEM_SECURITY_high;",
        "Factions": [],
    }
    handle(loc_ev, state, q)
    assert state.system == "Sol"

    # FSDJump event
    jump_ev = {
        "event": "FSDJump",
        "StarSystem": "Alpha Centauri",
        "SystemAddress": 5031721931482,
        "StarPos": [-1.8, -1.0, 3.1],
        "JumpDist": 4.3,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    handle(jump_ev, state, q)
    assert state.system == "Alpha Centauri"
    # Bodies must be cleared and indices reset
    assert state.bodies == []
    assert state._bodies_by_name == {}
    assert state._bodies_by_id == {}
