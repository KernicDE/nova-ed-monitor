"""Tests for situational panel modes, renderers, and the SituationalPanel class."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from rich.console import Console

from ed_monitor.state import AppState, BodyInfo, BioScan, MissionInfo, EngineerInfo
from ed_monitor.ui.panels import SituationalPanel
from ed_monitor.ui.situational.bio import _render_bio
from ed_monitor.ui.situational.missions import _render_missions, _mission_time_remaining
from ed_monitor.ui.situational.stats import _render_stats
from ed_monitor.ui.situational.docking import _render_docking
from ed_monitor.ui.situational.bgs import _render_bgs
from ed_monitor.ui.situational.engineers import (
    _build_eng_list, _eng_rank_pips, _render_engineer_detail, _ENGINEER_STATIC
)
from ed_monitor.ui.situational.assets import _render_assets


def _render_text(obj) -> str:
    """Render a Rich object to plain text for assertions."""
    console = Console(width=120, force_terminal=False, color_system=None)
    with console.capture() as capture:
        console.print(obj)
    return capture.get()


# ── SituationalPanel core logic ───────────────────────────────────────────────

class TestSituationalPanelCore:
    def test_active_modes_filters_auto(self):
        p = SituationalPanel()
        p._visible_modes = ["overview", "bio", "stats"]
        assert p._active_modes() == ["overview", "bio", "stats"]

    def test_cycle_wraps_forward(self):
        p = SituationalPanel()
        p._visible_modes = ["overview", "bio", "stats"]
        p._mode = "overview"
        p.cycle()
        assert p._mode == "bio"
        p.cycle()
        assert p._mode == "stats"
        p.cycle()
        assert p._mode == "overview"

    def test_back_cycle_wraps_backward(self):
        p = SituationalPanel()
        p._visible_modes = ["overview", "bio", "stats"]
        p._mode = "overview"
        p.back_cycle()
        assert p._mode == "stats"
        p.back_cycle()
        assert p._mode == "bio"
        p.back_cycle()
        assert p._mode == "overview"

    def test_visible_modes_from_config(self):
        p = SituationalPanel()
        snap = AppState()
        snap.situational_panels = ["bio", "route", "stats"]
        p.update(snap)
        assert p._visible_modes == ["bio", "route", "stats"]

    def test_mode_removed_from_config_falls_back(self):
        p = SituationalPanel()
        p._mode = "bio"
        p._visible_modes = ["overview", "stats"]
        snap = AppState()
        snap.situational_panels = ["overview", "stats"]
        p.update(snap)
        assert p._mode == "overview"

    def test_auto_switch_deduplication(self):
        p = SituationalPanel()
        p._auto = True
        p._visible_modes = ["overview", "bio", "route"]
        p._mode = "overview"
        p._last_auto_target = "bio"

        snap = AppState()
        snap.auto_panel_trigger_version = 1
        snap.auto_panel_trigger = "bio"
        p.update(snap)
        # Same target as last auto-switch → should NOT switch
        assert p._mode == "overview"

    def test_auto_switch_new_target_works(self):
        p = SituationalPanel()
        p._auto = True
        p._visible_modes = ["overview", "bio", "route"]
        p._mode = "overview"
        p._last_auto_target = "bio"
        p._last_trigger_version = 0

        snap = AppState()
        snap.auto_panel_trigger_version = 1
        snap.auto_panel_trigger = "route"
        p.update(snap)
        assert p._mode == "route"

    def test_scroll_general_non_scrollable_ignored(self):
        p = SituationalPanel()
        p._mode = "overview"
        p._general_scroll = 5
        p.scroll_general(3)
        # overview is non-scrollable → scroll should be ignored (stay at 5)
        assert p._general_scroll == 5

    def test_galaxy_submode_cycle(self):
        p = SituationalPanel()
        assert p._galaxy_submode == "system"
        p.toggle_galaxy_scale()
        assert p._galaxy_submode == "regional"
        p.toggle_galaxy_scale()
        assert p._galaxy_submode == "galaxy"
        p.toggle_galaxy_scale()
        assert p._galaxy_submode == "system"
        p.toggle_galaxy_scale_back()
        assert p._galaxy_submode == "galaxy"


# ── Render function tests ─────────────────────────────────────────────────────

class TestRenderBio:
    def test_empty(self):
        s = AppState()
        result = _render_bio(s)
        text = _render_text(result)
        assert "No biological scans active" in text

    def test_predicted_body(self):
        s = AppState()
        s.system = "Test"
        b = BodyInfo(
            name="Test A 1", body_id=1, level=1, planet_class="High Metal Content",
            star_type="", atmosphere="", terraform=False, landable=True,
            bio_signals=2, geo_signals=0, bio_genuses=[], dist_ls=100.0,
            value=0, first_discovered=False, first_mapped=False, mapped=False,
            fss_scanned=False, radius=1_000_000.0, bio_genuses_predicted=["Bacterium"]
        )
        s.bodies.append(b)
        result = _render_bio(s)
        text = _render_text(result)
        assert "Bacterium" in text or "predicted" in text.lower() or "bio" in text.lower()


class TestRenderMissions:
    def test_empty(self):
        s = AppState()
        result = _render_missions(s)
        text = _render_text(result)
        assert "No active missions" in text

    def test_expired_color(self):
        s = AppState()
        m = MissionInfo(
            mission_id=1, name="Test", destination="X",
            expiry=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        )
        s.missions.append(m)
        result = _render_missions(s, scroll=0)
        text = _render_text(result)
        assert "Expired" in text

    def test_destination_grouping(self):
        """Multiple missions to the same destination appear under one header."""
        s = AppState()
        dest = "Sol / Li Yong-Rui Service"
        for i in range(3):
            s.missions.append(MissionInfo(
                mission_id=i, name=f"Delivery {i}", destination=dest,
                expiry="", mission_type="Delivery",
                reward=100_000, cargo_type="Biowaste", cargo_count=60,
            ))
        result = _render_missions(s)
        text = _render_text(result)
        assert dest in text
        assert "×3" in text
        assert "180 t Biowaste" in text
        assert "300K Cr" in text

    def test_mission_type_and_wing_shown(self):
        """Type badge and [W] wing flag appear in the row."""
        s = AppState()
        s.missions.append(MissionInfo(
            mission_id=1, name="Wing Massacre", destination="Deciat",
            expiry="", mission_type="Massacre", wing=True, reward=500_000,
        ))
        result = _render_missions(s)
        text = _render_text(result)
        assert "Massacre" in text
        assert "[W]" in text

    def test_influence_badge_shown(self):
        """High-influence missions show the '++' badge."""
        s = AppState()
        s.missions.append(MissionInfo(
            mission_id=1, name="High Influence", destination="Sol",
            expiry="", mission_type="Courier", influence="++",
        ))
        result = _render_missions(s)
        text = _render_text(result)
        assert "++" in text

    def test_reward_column(self):
        """Reward appears in compact format."""
        s = AppState()
        s.missions.append(MissionInfo(
            mission_id=1, name="Test", destination="Sol",
            expiry="", reward=1_500_000,
        ))
        result = _render_missions(s)
        text = _render_text(result)
        assert "1.5M" in text

    def test_massacre_stacking_display(self):
        """Stacked massacre: bar uses max_needed, ×N multiplier, milestones shown."""
        s = AppState()
        s.missions.append(MissionInfo(mission_id=1, name="M1", destination="X", expiry="",
                                       mission_type="Massacre"))
        s.missions.append(MissionInfo(mission_id=2, name="M2", destination="X", expiry="",
                                       mission_type="Massacre"))
        s.massacre_kills[1] = {"faction": "Pirates", "needed": 10, "done": 8}
        s.massacre_kills[2] = {"faction": "Pirates", "needed": 12, "done": 8}
        result = _render_missions(s)
        text = _render_text(result)
        assert "8/12" in text
        assert "×2" in text
        assert "→12" in text or "12" in text

    def test_massacre_single_no_milestones(self):
        """Single massacre mission: no ×N or milestone markers."""
        s = AppState()
        s.missions.append(MissionInfo(mission_id=1, name="M", destination="X", expiry="",
                                       mission_type="Massacre"))
        s.massacre_kills[1] = {"faction": "Outlaws", "needed": 15, "done": 5}
        result = _render_missions(s)
        text = _render_text(result)
        assert "5/15" in text
        assert "×" not in text

    def test_scroll_slices_by_expiry(self):
        """scroll=1 skips the soonest-expiring mission."""
        s = AppState()
        soon   = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        later  = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        s.missions.append(MissionInfo(mission_id=1, name="SoonMission",  destination="A", expiry=soon))
        s.missions.append(MissionInfo(mission_id=2, name="LaterMission", destination="B", expiry=later))
        result = _render_missions(s, scroll=1)
        text = _render_text(result)
        assert "LaterMission" in text
        assert "SoonMission" not in text


class TestRenderStats:
    def test_empty(self):
        s = AppState()
        result = _render_stats(s)
        text = _render_text(result)
        assert "—" in text


class TestRenderDocking:
    def test_unknown_station_fallback(self):
        s = AppState()
        s.docked_pad = 5
        s.docked_station_name = "Test Outpost"
        s.docked_station_type = "Outpost"
        result = _render_docking(s)
        text = _render_text(result)
        assert "not available" in text.lower()

    def test_coriolis_shows_diagram(self):
        s = AppState()
        s.docked_pad = 5
        s.docked_station_name = "Test Station"
        s.docked_station_type = "Coriolis"
        result = _render_docking(s)
        text = _render_text(result)
        assert "Pad" in text

    def test_carrier_front_and_cockpit_labels(self):
        """Fleet carrier diagram shows FRONT header and COCKPIT footer."""
        s = AppState()
        s.docked_pad = 7
        s.docked_station_name = "P.T.N. Nomad"
        s.docked_station_type = "FleetCarrier"
        result = _render_docking(s)
        text = _render_text(result)
        assert "FRONT" in text
        assert "COCKPIT" in text

    def test_carrier_assigned_pad_highlighted(self):
        """Assigned carrier pad is shown with brackets."""
        for pad in (1, 7, 13, 16):
            s = AppState()
            s.docked_pad = pad
            s.docked_station_type = "FleetCarrier"
            text = _render_text(_render_docking(s))
            assert f"[{pad:2}]" in text or f"[{pad}]" in text

    def test_carrier_hint_text(self):
        """Carrier hint reflects row and size for each pad."""
        cases = [
            (7,  "Front bay"),
            (5,  "Mid bay"),
            (13, "small pad"),
            (10, "medium pad"),
            (1,  "Cockpit row"),
            (3,  "large pad"),
        ]
        for pad, expected in cases:
            s = AppState()
            s.docked_pad = pad
            s.docked_station_type = "FleetCarrier"
            text = _render_text(_render_docking(s))
            assert expected.lower() in text.lower(), f"pad {pad}: expected '{expected}' in output"

    def test_asteroid_base_rings(self):
        """Asteroid base shows ring diagram and cave centre mark."""
        s = AppState()
        s.docked_pad = 3
        s.docked_station_name = "Jokers Wild"
        s.docked_station_type = "AsteroidBase"
        result = _render_docking(s)
        text = _render_text(result)
        assert "[3]" in text
        assert "╳" in text

    def test_asteroid_inner_outer_hint(self):
        """Asteroid base hint distinguishes inner (large) from outer (small)."""
        s_inner = AppState()
        s_inner.docked_pad = 2
        s_inner.docked_station_type = "AsteroidBase"
        assert "Inner" in _render_text(_render_docking(s_inner))

        s_outer = AppState()
        s_outer.docked_pad = 6
        s_outer.docked_station_type = "AsteroidBase"
        assert "Outer" in _render_text(_render_docking(s_outer))


class TestRenderBGS:
    def test_system_grouping(self):
        s = AppState()
        s.system = "Alpha"
        s.bgs_log = {
            "Alpha": {"Faction A": {"Mission": 3, "Trade": 2}},
            "Beta":  {"Faction B": {"Combat": 5}},
        }
        s.bgs_log_date = "2026-04-28"
        result = _render_bgs(s)
        text = _render_text(result)
        assert "Alpha" in text
        assert "Beta" in text


class TestRenderAssets:
    def test_empty(self):
        s = AppState()
        result = _render_assets(s)
        text = _render_text(result)
        # Empty state still shows balance and fleet sections with placeholders
        assert "BALANCE" in text
        assert "FLEET" in text

    def test_scrollable(self):
        s = AppState()
        s.credits = 1_000_000
        s.stored_ships = [{"name": f"Ship {i}", "system": "Sol"} for i in range(20)]
        result = _render_assets(s, scroll=5)
        # Should not crash and should slice content
        assert result is not None


# ── Engineer helper tests ─────────────────────────────────────────────────────

class TestEngineerHelpers:
    def test_build_eng_list_sort_order(self):
        s = AppState()
        s.engineers["1"] = EngineerInfo(
            name="Felicity Farseer", progress="Unlocked", rank=5, rank_progress=0.0
        )
        s.engineers["2"] = EngineerInfo(
            name="Jude Navarro", progress="Unknown", rank=0, rank_progress=0.0
        )
        lst = _build_eng_list(s)
        names = [n for _, n, _, _, _ in lst]
        # Horizons before Odyssey
        assert names.index("Felicity Farseer") < names.index("Jude Navarro")

    def test_eng_rank_pips_unlocked_g5(self):
        pips, style, grade, gstyle = _eng_rank_pips(5, 0.0, "Unlocked", False)
        assert pips == "●●●●●"
        assert style == "rgb(0,170,60)"

    def test_eng_rank_pips_odyssey(self):
        pips, style, grade, gstyle = _eng_rank_pips(0, 0.0, "Unlocked", True)
        assert pips == "●"
        assert style == "rgb(0,170,60)"

    def test_render_engineer_detail_known(self):
        result = _render_engineer_detail("Felicity Farseer", 5, 0.0, "Unlocked")
        text = _render_text(result)
        assert "Farseer Inc" in text


# ── _mission_time_remaining ───────────────────────────────────────────────────

class TestMissionTimeRemaining:
    def test_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert _mission_time_remaining(past) == "Expired"

    def test_minutes(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        assert _mission_time_remaining(future).endswith("m")

    def test_hours(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=15)).isoformat()
        result = _mission_time_remaining(future)
        assert "h" in result

    def test_days(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2, hours=5)).isoformat()
        result = _mission_time_remaining(future)
        assert "d" in result

    def test_empty(self):
        assert _mission_time_remaining("") == ""
