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
