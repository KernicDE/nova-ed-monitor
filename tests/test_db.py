"""Tests for Database operations."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from ed_monitor.db import Database
from ed_monitor.state import BioScan, BodyInfo


def _db() -> Database:
    tmp = tempfile.mktemp(suffix=".db")
    return Database(Path(tmp))


def _body(name: str, body_id: int = 1) -> BodyInfo:
    return BodyInfo(
        name=name, body_id=body_id, level=1,
        planet_class="Rocky body", star_type="", atmosphere="",
        terraform=False, landable=True,
        bio_signals=2, geo_signals=0, bio_genuses=["Bacterium"],
        dist_ls=200.0, value=80_000,
        first_discovered=True, first_mapped=False,
        mapped=False, fss_scanned=True, radius=600_000.0,
    )


def test_save_bodies_batch_and_load():
    db = _db()
    bodies = [_body("Sys A 1", 1), _body("Sys A 2", 2)]
    db.save_bodies_batch("Sys A", bodies)
    loaded = db.load_bodies("Sys A")
    assert len(loaded) == 2
    names = {b.name for b in loaded}
    assert names == {"Sys A 1", "Sys A 2"}


def test_save_bodies_batch_empty():
    db = _db()
    db.save_bodies_batch("Sys B", [])  # must not raise
    assert db.load_bodies("Sys B") == []


def test_save_body_single_delegates_to_batch():
    db = _db()
    db.save_body("Sys C", _body("Sys C 1"))
    assert len(db.load_bodies("Sys C")) == 1


def test_bio_scans_round_trip():
    db = _db()
    sc = BioScan(
        species="Bacterium Aurasus", species_localised="Bacterium Aurasus",
        genus_localised="Bacterium", body="Sys D 1",
        samples=2, min_dist=100.0, last_lat=10.5, last_lon=-20.3,
        body_radius=600_000.0, current_dist=None, value=1_000_600,
        alerted=False, complete=False, first_discovered=True,
        sample_lats=[10.5, 11.0], sample_lons=[-20.3, -19.8],
    )
    db.save_bio_scans("Sys D", [sc])
    loaded = db.load_bio_scans("Sys D")
    assert len(loaded) == 1
    assert loaded[0].species == "Bacterium Aurasus"
    assert loaded[0].sample_lats == [10.5, 11.0]
    assert loaded[0].sample_lons == [-20.3, -19.8]


def test_stats_increment_and_get():
    db = _db()
    db.increment_stat("jump_count", 1)
    db.increment_stat("jump_count", 2)
    stats = db.get_stats()
    assert "jump_count" in stats
    assert stats["jump_count"]["total"] == pytest.approx(3.0)
    assert stats["jump_count"]["today"] == pytest.approx(3.0)


def test_config_round_trip():
    db = _db()
    db.set_config("test_key", "hello")
    assert db.get_config("test_key") == "hello"
    assert db.get_config("missing_key", "default") == "default"


def test_prune_events_removes_old_rows():
    """prune_events(days=N) must keep recent rows and delete older ones."""
    from datetime import datetime, timedelta
    from ed_monitor.state import EventCategory, LogEvent
    db = _db()
    # Insert one fresh + one ancient event by bypassing insert()'s auto-timestamp.
    db.insert(LogEvent.new(EventCategory.Nav, "fresh jump"), "Sol")
    with db._lock:
        db._conn.execute(
            "INSERT INTO events (timestamp, category, message, system, event_date, commander)"
            " VALUES (?,?,?,?,?,?)",
            ("12:00:00", "NAV", "old jump", "Sol",
             (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d %H:%M:%S"),
             ""),
        )
        db._conn.commit()
    deleted = db.prune_events(days=180)
    assert deleted == 1
    remaining = [ev.message for ev in db.get_recent_events(10)]
    assert "fresh jump" in remaining
    assert "old jump" not in remaining


def test_edsm_systems_import_and_query():
    db = _db()
    # (id64, name, x, y, z, allegiance, government, economy, population, security, power, power_state)
    rows = [
        (100, "Sol",    0.0,  0.0, 0.0,  "Federation", "Democracy", "High Tech", 22_000_000, "High", "Felicia Winters", "Exploited"),
        (200, "Alioth", -33.6, 72.5, -20.7, "Alliance",  "Democracy", "High Tech",  9_000_000, "High", "Edmund Mahon",    "Control"),
        (300, "Deep Space", 500.0, 0.0, 0.0, "", "", "", 0, "", "", ""),
    ]
    db.import_edsm_systems_batch(rows)

    # Power query
    power, state = db.get_system_power("Sol")
    assert power == "Felicia Winters"
    assert state == "Exploited"
    assert db.get_system_power("Unknown") == ("", "")

    # Nearest populated (from Deep Space)
    nearest = db.get_nearest_populated(500.0, 0.0, 0.0, exclude="Deep Space")
    assert nearest is not None
    assert nearest[0] in ("Sol", "Alioth")      # one of the inhabited ones
    assert nearest[1] > 0                        # positive distance

    # Nearest excludes current system
    nearest_from_sol = db.get_nearest_populated(0.0, 0.0, 0.0, exclude="Sol")
    assert nearest_from_sol is not None
    assert nearest_from_sol[0] != "Sol"


def test_edsm_stations_import_and_query():
    db = _db()
    # (id, name, system_id64, system_name, type, dist_ls, allegiance, government, economy,
    #  has_market, has_shipyard, has_outfitting, other_services)
    rows = [
        (1, "Galileo",      17072, "Sol", "Orbis Starport",  490.0, "Federation", "Democracy", "High Tech", 1, 1, 1, "Refuel|Repair|Contacts"),
        (2, "Titan City",   17072, "Sol", "Orbis Starport",  4529.0, "Federation", "Democracy", "Industrial", 1, 0, 1, "Refuel|Missions"),
    ]
    db.import_edsm_stations_batch(rows)

    stations = db.get_system_stations("Sol")
    assert len(stations) == 2
    assert stations[0]["name"] == "Galileo"      # closest first
    assert stations[0]["market"] is True
    assert stations[0]["shipyard"] is True
    assert "Repair" in stations[0]["services"]
    assert db.get_system_stations("Empty System") == []


def test_edsm_powerplay_upsert():
    db = _db()
    # First import a populated system
    db.import_edsm_systems_batch([
        (100, "Sol", 0.0, 0.0, 0.0, "Federation", "Democracy", "High Tech", 22_000_000, "High", "", "")
    ])
    # Power play upsert should set power without touching population
    db.upsert_edsm_powerplay_batch([
        (100, "Sol", 0.0, 0.0, 0.0, "", "", "", 0, "", "Felicia Winters", "Exploited")
    ])
    power, state = db.get_system_power("Sol")
    assert power == "Felicia Winters"
    assert state == "Exploited"
    # Population should still come from the original import (not overwritten by powerplay)
    nearest = db.get_nearest_populated(-1.0, 0.0, 0.0, exclude="Other")
    assert nearest is not None
    assert nearest[5] == 22_000_000  # population preserved
