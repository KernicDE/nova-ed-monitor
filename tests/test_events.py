"""Tests for event handler helpers."""
from __future__ import annotations

import queue
import pytest
from ed_monitor.events import _fmt_credits, _body_vars, handle, is_scoopable, _is_terraformable, _phonetic_sub
from ed_monitor.state import AppState, BodyInfo, EventCategory
from ed_monitor.state import estimate_value_mapped as _ev_mapped


def test_handle_rejects_non_dict_payload():
    """A malformed journal line must not crash the handler."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    # Each of these would have raised AttributeError prior to R-11.
    for bad in ([], "event", 42, None, 3.14):
        assert handle(bad, state, q) is None


def test_handle_rejects_missing_event_field():
    state = AppState()
    q: queue.Queue = queue.Queue()
    assert handle({}, state, q) is None
    assert handle({"event": ""}, state, q) is None


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


def _location_event(system: str = "TestSys") -> dict:
    return {"event": "Location", "StarSystem": system, "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0], "Population": 0, "Economy": "$economy_None;",
            "Government": "$government_None;", "Allegiance": "Independent",
            "Security": "$SYSTEM_SECURITY_low;", "Factions": []}


def _high_g_scan_ev(body_name: str = "TestSys 1") -> dict:
    ev = _make_scan_ev("TestSys", body_name)
    ev["SurfaceGravity"] = 9.80665 * 3.5  # 3.5 G → extreme
    ev["Landable"] = True
    return ev


def test_approach_body_extreme_g_schedules_timers():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_location_event(), state, q)
    handle(_high_g_scan_ev(), state, q)
    handle({"event": "ApproachBody", "Body": "TestSys 1", "BodyID": 1}, state, q)
    assert len(state.high_g_timers) == 2
    assert all(t.is_alive() for t in state.high_g_timers)
    # Clean up so pytest doesn't leave live Timer threads after the test
    for t in state.high_g_timers:
        t.cancel()


def test_leave_body_cancels_high_g_timers():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_location_event(), state, q)
    handle(_high_g_scan_ev(), state, q)
    handle({"event": "ApproachBody", "Body": "TestSys 1", "BodyID": 1}, state, q)
    scheduled = list(state.high_g_timers)
    assert len(scheduled) == 2

    handle({"event": "LeaveBody", "Body": "TestSys 1", "BodyID": 1}, state, q)
    assert state.high_g_timers == []
    # Every previously-scheduled timer is cancelled
    for t in scheduled:
        assert t.finished.is_set()


def test_second_approach_cancels_previous_timers():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_location_event(), state, q)
    handle(_high_g_scan_ev("TestSys 1"), state, q)
    handle({"event": "ApproachBody", "Body": "TestSys 1", "BodyID": 1}, state, q)
    first = list(state.high_g_timers)
    handle(_high_g_scan_ev("TestSys 2"), state, q)
    handle({"event": "ApproachBody", "Body": "TestSys 2", "BodyID": 2}, state, q)
    # Prior timers cancelled, replaced with a fresh pair
    for t in first:
        assert t.finished.is_set()
    assert len(state.high_g_timers) == 2
    for t in state.high_g_timers:
        t.cancel()


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


# ── _body_vars value semantics (issue #108) ───────────────────────────────────

def _make_body(**kw) -> BodyInfo:
    defaults = dict(
        name="Test A 1", body_id=1, level=1,
        planet_class="Rocky body", star_type="", atmosphere="",
        terraform=False, landable=True,
        bio_signals=0, geo_signals=0, bio_genuses=[],
        dist_ls=100.0, value=0,
        first_discovered=False, first_mapped=False,
        mapped=False, fss_scanned=False, radius=500_000.0,
        mass_em=5.0, efficiency_bonus=False, first_footfall=False,
    )
    defaults.update(kw)
    return BodyInfo(**defaults)


def test_body_vars_value_fss_uses_mapped_projection():
    """{value} for an FSS'd body must equal _ev_mapped (mapped projection), not base."""
    b = _make_body(fss_scanned=True, mass_em=5.0)
    vars_ = _body_vars(b)
    assert vars_["value_raw"] == str(_ev_mapped(b))


def test_body_vars_value_non_fss_uses_edsm():
    """{value} for a non-FSS'd body with EDSM data must use the EDSM value."""
    b = _make_body(fss_scanned=False, value=50_000, mass_em=0.0)
    vars_ = _body_vars(b)
    assert vars_["value_raw"] == str(50_000)


def test_body_vars_scoopable_is_boolean():
    """{is_scoopable} must be a proper bool; legacy alias {scoopable} also present."""
    scoopable_star = _make_body(star_type="G")
    vars_s = _body_vars(scoopable_star)
    assert vars_s["is_scoopable"] is True
    assert vars_s["scoopable"] is True   # backward-compat alias

    non_scoopable_star = _make_body(star_type="N")
    vars_ns = _body_vars(non_scoopable_star)
    assert vars_ns["is_scoopable"] is False
    assert vars_ns["scoopable"] is False

    planet = _make_body(star_type="")
    vars_p = _body_vars(planet)
    assert vars_p["is_scoopable"] is False
    assert vars_p["scoopable"] is False


def test_body_vars_terraformable_is_boolean():
    """{is_terraformable} must be a proper bool; legacy alias {terra} also present."""
    terraformable = _make_body(terraform=True)
    vars_t = _body_vars(terraformable)
    assert vars_t["is_terraformable"] is True
    assert vars_t["terra"] is True   # backward-compat alias

    not_terra = _make_body(terraform=False)
    vars_nt = _body_vars(not_terra)
    assert vars_nt["is_terraformable"] is False
    assert vars_nt["terra"] is False


def test_is_scoopable_normalizes_star_class_tokens():
    """is_scoopable must handle journal star types with extra text or whitespace."""
    assert is_scoopable("K") is True
    assert is_scoopable("k") is True
    assert is_scoopable(" K (Yellow-Orange) Star ") is True
    assert is_scoopable("G (White-Yellow) Star") is True
    assert is_scoopable("N") is False
    assert is_scoopable("White Dwarf") is False
    assert is_scoopable("") is False


def test_is_terraformable_handles_journal_variants():
    """_is_terraformable must handle $-prefixed tokens and plain English."""
    assert _is_terraformable("Terraformable") is True
    assert _is_terraformable("$PLANET_TERRAFORMABLE;") is True
    assert _is_terraformable("Terraforming") is True
    assert _is_terraformable("$PLANET_TERRAFORMING;") is True
    assert _is_terraformable("Not terraformable") is False
    assert _is_terraformable("$PLANET_NOTERRAFORMABLE;") is False
    assert _is_terraformable("") is False
    assert _is_terraformable("$TERRAFORMSTATE_NONE;") is False


def test_scan_terraform_state_detects_dollar_prefixed():
    """Scan events with $-prefixed TerraformState must set body.terraform correctly."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_location_event(), state, q)

    ev = _make_scan_ev("TestSys", "TestSys 1")
    ev["TerraformState"] = "$PLANET_TERRAFORMABLE;"
    handle(ev, state, q)
    assert state.bodies[0].terraform is True

    ev2 = _make_scan_ev("TestSys", "TestSys 2")
    ev2["BodyID"] = 2
    ev2["TerraformState"] = "$PLANET_NOTERRAFORMABLE;"
    handle(ev2, state, q)
    idx2 = state._bodies_by_name["TestSys 2"]
    assert state.bodies[idx2].terraform is False


# ── _build_eng_list return type ───────────────────────────────────────────────

def test_build_eng_list_returns_flat_tuples():
    """_build_eng_list must return 5-tuples (era_tag, name, rank, rp, prog)."""
    from ed_monitor.ui.panels import _build_eng_list
    state = AppState()
    result = _build_eng_list(state)
    assert len(result) > 0
    for entry in result:
        assert len(entry) == 5
        era_tag, name, rank, rp, prog = entry
        assert era_tag in ("H", "O")
        assert isinstance(name, str)
        assert isinstance(rank, int)
        assert isinstance(rp, float)
        assert isinstance(prog, str)


def test_build_eng_list_horizons_before_odyssey():
    """Horizons engineers must appear before Odyssey engineers in the output."""
    from ed_monitor.ui.panels import _build_eng_list, _ODY_ENGINEERS
    state = AppState()
    result = _build_eng_list(state)
    eras = [e[0] for e in result]
    last_h = max((i for i, e in enumerate(eras) if e == "H"), default=-1)
    first_o = next((i for i, e in enumerate(eras) if e == "O"), len(eras))
    assert last_h < first_o


def test_build_eng_list_unknown_engineers_shown():
    """All ~40 static engineers appear even when s.engineers is empty."""
    from ed_monitor.ui.panels import _build_eng_list, _ENGINEER_STATIC
    state = AppState()
    result = _build_eng_list(state)
    names_in_result = {e[1] for e in result}
    assert names_in_result == set(_ENGINEER_STATIC.keys())


# ── UnderAttack cooldown & formatting (issue #114) ────────────────────────────

import time


def _under_attack_ev(target: str = "You") -> dict:
    return {"event": "UnderAttack", "Target": target}


def test_under_attack_cooldown_blocks_spam():
    """Only the first UnderAttack in a 30 s window should fire."""
    state = AppState()
    q: queue.Queue = queue.Queue()

    result1 = handle(_under_attack_ev(), state, q)
    assert result1 is not None
    assert "Under attack" in result1.message

    # Immediate repeat must be suppressed
    result2 = handle(_under_attack_ev(), state, q)
    assert result2 is None


def test_under_attack_uses_attacker_name_and_ship():
    """When ShipTargeted info is present, message should name the attacker + ship."""
    state = AppState()
    state.target_ship_pilot = "Ardan Voss"
    state.target_ship = "Vulture"
    q: queue.Queue = queue.Queue()

    result = handle(_under_attack_ev(), state, q)
    assert result is not None
    assert "Attacker: Ardan Voss (Vulture)" in result.message


def test_under_attack_ignores_useless_target_you():
    """When the only target info is 'You', fall back to the generic warning."""
    state = AppState()
    state.target_ship_pilot = ""
    state.target_ship = ""
    q: queue.Queue = queue.Queue()

    result = handle(_under_attack_ev("You"), state, q)
    assert result is not None
    assert result.message == "Warning! Under attack!"
    assert "Target: You" not in result.message


def test_under_attack_sets_flash_timer():
    """A successful UnderAttack should set under_attack_flash_until ~5 s ahead."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    before = time.time()

    handle(_under_attack_ev(), state, q)

    after = time.time()
    assert state.under_attack_flash_until >= before + 5.0
    assert state.under_attack_flash_until <= after + 5.0


# ── Route arrival / clearing ──

def test_fsd_jump_final_hop_announces_arrival():
    """Jumping into the destination system must announce 'Target reached.'"""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.route_hops = 1
    state.route_destination = "Dest"
    state.route_list = [
        {"StarSystem": "Prev", "StarPos": [0, 0, 0]},
        {"StarSystem": "Dest", "StarPos": [1, 0, 0]},
    ]

    ev = {
        "event": "FSDJump",
        "StarSystem": "Dest",
        "SystemAddress": 1,
        "StarPos": [1.0, 0.0, 0.0],
        "JumpDist": 1.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert result.message == "Target reached."
    assert state.route_arrived is True
    assert state.route_hops == 0


def test_fsd_jump_without_route_does_not_announce_arrival():
    """A normal FSDJump with no active route must not trigger arrival text."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.route_hops = 0

    ev = {
        "event": "FSDJump",
        "StarSystem": "Sol",
        "SystemAddress": 1,
        "StarPos": [0.0, 0.0, 0.0],
        "JumpDist": 5.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert "Arrived in Sol" in result.message
    assert "Target reached" not in result.message


def test_nav_route_clear_after_arrival_is_silent():
    """NavRouteClear after arrival must be silent (already announced in FSDJump)."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.route_arrived = True

    result = handle({"event": "NavRouteClear"}, state, q)

    assert result is None
    assert state.route_arrived is False


def test_nav_route_clear_manual_says_route_cleared():
    """Manually clearing an active route must say 'Route cleared.'"""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.route_arrived = False
    state.route_hops = 3

    result = handle({"event": "NavRouteClear"}, state, q)

    assert result is not None
    assert result.message == "Route cleared."
    assert state.route_hops == 0


# ── Home system ──

def test_fsd_jump_home_system_triggers_special_voiceline():
    """Arriving in the configured home system must speak FSDJump_Home."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.home_system = "Sol"

    ev = {
        "event": "FSDJump",
        "StarSystem": "Sol",
        "SystemAddress": 1,
        "StarPos": [0.0, 0.0, 0.0],
        "JumpDist": 5.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert "Welcome home" in result.message
    assert not q.empty()


def test_fsd_jump_other_system_uses_normal_voiceline():
    """Arriving in a non-home system must use the normal FSDJump voiceline."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.home_system = "Sol"

    ev = {
        "event": "FSDJump",
        "StarSystem": "Alpha Centauri",
        "SystemAddress": 1,
        "StarPos": [0.0, 0.0, 0.0],
        "JumpDist": 5.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert "Welcome home" not in result.message
    assert "Arrived in Alpha Centauri" in result.message


def test_fsd_jump_home_system_case_insensitive():
    """Home system match must be case-insensitive."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.home_system = "sol"

    ev = {
        "event": "FSDJump",
        "StarSystem": "SOL",
        "SystemAddress": 1,
        "StarPos": [0.0, 0.0, 0.0],
        "JumpDist": 5.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert "Welcome home" in result.message


def test_fsd_jump_no_home_system_skips_check():
    """When home_system is empty, normal FSDJump voiceline is used."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.home_system = ""

    ev = {
        "event": "FSDJump",
        "StarSystem": "Sol",
        "SystemAddress": 1,
        "StarPos": [0.0, 0.0, 0.0],
        "JumpDist": 5.0,
        "Population": 0,
        "Economy": "$economy_None;",
        "Government": "$government_None;",
        "Allegiance": "Independent",
        "Security": "$SYSTEM_SECURITY_low;",
        "Factions": [],
    }
    result = handle(ev, state, q)

    assert result is not None
    assert "Welcome home" not in result.message


class TestPhoneticSub:
    def test_kernic_replacement(self):
        assert "Kernik" in _phonetic_sub("kernicde", "en")
        assert "Kernik" in _phonetic_sub("KernicDE", "en")

    def test_ly_replacement(self):
        assert _phonetic_sub("10 ly", "en") == "10 light years"

    def test_cr_replacement(self):
        assert _phonetic_sub("100 cr", "en") == "100 credits"

    def test_hyphen_replacement_german(self):
        assert _phonetic_sub("System c12-a", "de") == "System c12 Strich a"
        assert _phonetic_sub("G65434-2", "de") == "G65434 Strich 2"

    def test_hyphen_replacement_english(self):
        assert _phonetic_sub("System c12-a", "en") == "System c12 dash a"

    def test_hyphen_replacement_french(self):
        assert _phonetic_sub("System c12-a", "fr") == "System c12 tiret a"

    def test_hyphen_replacement_russian(self):
        assert _phonetic_sub("System c12-a", "ru") == "System c12 тире a"

    def test_no_hyphen_replacement_when_lang_missing(self):
        # Unknown language falls back to no replacement
        assert _phonetic_sub("System c12-a", "xx") == "System c12-a"

    def test_regular_text_unchanged(self):
        assert _phonetic_sub("Hello world", "de") == "Hello world"
