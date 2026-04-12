"""Tests for event handler helpers."""
from __future__ import annotations

import queue
import pytest
from ed_monitor.events import _fmt_credits, handle
from ed_monitor.state import AppState, BodyInfo, EventCategory


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


def _make_scan_ev(system: str, body_name: str, scan_type: str = "Detailed") -> dict:
    return {
        "event": "Scan",
        "ScanType": scan_type,
        "BodyName": body_name,
        "BodyID": 1,
        "StarSystem": system,
        "SystemAddress": 123456,
        "DistanceFromArrivalLS": 0.0,
        "WasDiscovered": True,
        "WasMapped": True,
        "PlanetClass": "Icy body",
        "Landable": False,
        "MassEM": 0.1,
        "Radius": 1000000.0,
        "SurfaceTemperature": 100.0,
        "SurfaceGravity": 1.0,
    }


def test_scan_sets_fss_scanned_for_detailed():
    """Detailed FSS scan must set fss_scanned=True."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle({"event": "Location", "StarSystem": "TestSys", "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}, state, q)
    handle(_make_scan_ev("TestSys", "TestSys 1", "Detailed"), state, q)
    assert state.bodies
    assert state.bodies[0].fss_scanned is True


def test_scan_sets_fss_scanned_for_autoscan():
    """AutoScan must also set fss_scanned=True (not just Detailed)."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle({"event": "Location", "StarSystem": "TestSys", "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}, state, q)
    ev = _make_scan_ev("TestSys", "TestSys 1", "AutoScan")
    ev["StarType"] = "G"  # make it a star so AutoScan processes it
    ev.pop("PlanetClass", None)
    ev.pop("MassEM", None)
    ev["StellarMass"] = 1.0
    handle(ev, state, q)
    assert state.bodies
    assert state.bodies[0].fss_scanned is True


def test_saa_scan_complete_logs_first_map():
    """SAAScanComplete should include 'First map!' in log when first_mapped is True."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle({"event": "Location", "StarSystem": "TestSys", "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}, state, q)
    scan_ev = _make_scan_ev("TestSys", "TestSys 1")
    scan_ev["WasMapped"] = False  # first map
    handle(scan_ev, state, q)
    assert state.bodies
    assert state.bodies[0].first_mapped is True

    saa_ev = {
        "event": "SAAScanComplete",
        "BodyName": "TestSys 1",
        "BodyID": 1,
        "SystemAddress": 1,
        "ProbesUsed": 6,
        "EfficiencyTarget": 6,
    }
    result = handle(saa_ev, state, q)
    assert result is not None
    assert "First map" in result.message


def test_saa_scan_complete_no_first_map_when_already_mapped():
    """SAAScanComplete should NOT include 'First map!' when body was already mapped."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle({"event": "Location", "StarSystem": "TestSys", "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}, state, q)
    scan_ev = _make_scan_ev("TestSys", "TestSys 1")
    scan_ev["WasMapped"] = True  # already mapped by someone
    handle(scan_ev, state, q)

    saa_ev = {
        "event": "SAAScanComplete",
        "BodyName": "TestSys 1",
        "BodyID": 1,
        "SystemAddress": 1,
        "ProbesUsed": 8,
        "EfficiencyTarget": 6,
    }
    result = handle(saa_ev, state, q)
    assert result is not None
    assert "First map" not in result.message


def test_first_footfall_via_bodyinfo_flag():
    """Disembark should fire first footfall announcement when BodyInfo.first_footfall is set."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle({"event": "Location", "StarSystem": "TestSys", "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}, state, q)
    # Scan with WasFootfalled=False sets BodyInfo.first_footfall=True
    scan_ev = _make_scan_ev("TestSys", "TestSys 1")
    scan_ev["WasFootfalled"] = False
    handle(scan_ev, state, q)
    assert state.bodies[0].first_footfall is True

    # Disembark without journal FirstFootfall flag — should still announce via BodyInfo fallback
    dis_ev = {
        "event": "Disembark",
        "SRV": False,
        "OnStation": False,
        "Body": "TestSys 1",
        "BodyID": 1,
        "OnFoot": True,
    }
    result = handle(dis_ev, state, q, live=True)
    assert result is not None
    assert "FIRST FOOTFALL" in result.message
