"""Tests for AppState body index correctness."""
from __future__ import annotations

import pytest
from ed_monitor.state import AppState, BodyInfo


def _body(name: str, body_id: int, planet_class: str = "Rocky body") -> BodyInfo:
    return BodyInfo(
        name=name, body_id=body_id, level=1,
        planet_class=planet_class, star_type="", atmosphere="",
        terraform=False, landable=True,
        bio_signals=0, geo_signals=0, bio_genuses=[],
        dist_ls=100.0, value=50_000,
        first_discovered=False, first_mapped=False,
        mapped=False, fss_scanned=False, radius=500_000.0,
    )


def test_upsert_inserts_and_indexes():
    s = AppState()
    b = _body("Sol A", 1)
    s.upsert_body(b)
    assert s._bodies_by_name == {"Sol A": 0}
    assert s._bodies_by_id == {1: 0}
    assert s.bodies[0].name == "Sol A"


def test_upsert_multiple_sorted_by_body_id():
    s = AppState()
    s.upsert_body(_body("Sol C", 3))
    s.upsert_body(_body("Sol A", 1))
    s.upsert_body(_body("Sol B", 2))
    assert [b.body_id for b in s.bodies] == [1, 2, 3]
    # Indices must reflect sorted positions
    for i, b in enumerate(s.bodies):
        assert s._bodies_by_name[b.name] == i
        assert s._bodies_by_id[b.body_id] == i


def test_upsert_update_preserves_bio_signals():
    s = AppState()
    b1 = _body("Sol A", 1)
    b1.bio_signals = 3
    s.upsert_body(b1)
    # Second upsert with bio_signals=0 should keep existing value
    b2 = _body("Sol A", 1)
    assert b2.bio_signals == 0
    s.upsert_body(b2)
    assert s.bodies[0].bio_signals == 3


def test_upsert_update_keeps_index_stable():
    s = AppState()
    s.upsert_body(_body("Sol A", 1))
    s.upsert_body(_body("Sol B", 2))
    idx_before = s._bodies_by_name["Sol A"]
    s.upsert_body(_body("Sol A", 1))  # update, not insert
    assert s._bodies_by_name["Sol A"] == idx_before


def test_clear_bodies():
    s = AppState()
    s.upsert_body(_body("Sol A", 1))
    s.upsert_body(_body("Sol B", 2))
    s.clear_bodies()
    assert s.bodies == []
    assert s._bodies_by_name == {}
    assert s._bodies_by_id == {}


def test_lookup_after_clear_and_reinsert():
    s = AppState()
    s.upsert_body(_body("Sol A", 1))
    s.clear_bodies()
    s.upsert_body(_body("Sol X", 10))
    assert s._bodies_by_name == {"Sol X": 0}
    assert s._bodies_by_id == {10: 0}


def test_rebuild_body_index():
    s = AppState()
    s.upsert_body(_body("Sol A", 1))
    s.upsert_body(_body("Sol B", 2))
    # Manually corrupt index then rebuild
    s._bodies_by_name.clear()
    s._bodies_by_id.clear()
    s._rebuild_body_index()
    assert s._bodies_by_name == {"Sol A": 0, "Sol B": 1}
    assert s._bodies_by_id == {1: 0, 2: 1}
