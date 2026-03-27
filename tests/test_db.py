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
