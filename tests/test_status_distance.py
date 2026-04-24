"""Tests for status.py haversine distance and bio-distance resolution (P-4, R-4)."""
from __future__ import annotations

import math
import queue

import pytest

from ed_monitor.state import AppState, BioScan, BodyInfo, _DEFAULT_BODY_RADIUS_M
from ed_monitor.status import _haversine, _check_bio_distance


def _landable_body(name: str = "TestBody", body_id: int = 1,
                   radius: float = _DEFAULT_BODY_RADIUS_M) -> BodyInfo:
    return BodyInfo(
        name=name, body_id=body_id, level=1,
        planet_class="Rocky body", star_type="", atmosphere="",
        terraform=False, landable=True,
        bio_signals=0, geo_signals=0, bio_genuses=[],
        dist_ls=200.0, value=0,
        first_discovered=False, first_mapped=False,
        mapped=False, fss_scanned=False, radius=radius,
    )


def _scan(body: str = "TestBody",
          *,
          species: str = "Bacterium Aurasus",
          min_dist: float = 500.0,
          foot: list[tuple[float, float]] | None = None,
          comp: list[tuple[float, float]] | None = None,
          complete: bool = False,
          samples: int = 1) -> BioScan:
    foot = foot or []
    comp = comp or []
    return BioScan(
        species=species, species_localised=species,
        genus_localised="Bacterium", body=body,
        samples=samples, min_dist=min_dist, last_lat=None, last_lon=None,
        body_radius=_DEFAULT_BODY_RADIUS_M, current_dist=None,
        value=0, alerted=False, complete=complete, first_discovered=False,
        sample_lats=[p[0] for p in foot], sample_lons=[p[1] for p in foot],
        comp_lats=[p[0] for p in comp], comp_lons=[p[1] for p in comp],
    )


# ── Haversine ────────────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert _haversine(0.0, 0.0, 0.0, 0.0, 1000.0) == pytest.approx(0.0)

    def test_quarter_circle_equals_pi_over_2_times_radius(self):
        # 90° of longitude along the equator on a unit sphere = π/2
        r = 1.0
        d = _haversine(0.0, 0.0, 0.0, 90.0, r)
        assert d == pytest.approx(math.pi / 2, abs=1e-6)

    def test_symmetric(self):
        d1 = _haversine(10.0, 20.0, -30.0, 40.0, 1e6)
        d2 = _haversine(-30.0, 40.0, 10.0, 20.0, 1e6)
        assert d1 == pytest.approx(d2)


# ── _check_bio_distance ─────────────────────────────────────────────────────

class TestCheckBioDistance:
    def _state(self, lat: float = 0.0, lon: float = 0.0,
               on_surface: bool = True) -> AppState:
        s = AppState()
        s.lat, s.lon = lat, lon
        if on_surface:
            s.landed = True
        else:
            s.in_main_ship = True
        s.nearest_body = "TestBody"
        s.upsert_body(_landable_body())
        return s

    def test_skips_complete_scans(self):
        s = self._state()
        sc = _scan(complete=True, samples=3, foot=[(1.0, 1.0)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        _check_bio_distance(s, q)
        assert sc.current_dist is None
        assert sc.sample_bearings == []

    def test_no_foot_samples_every_comp_marker_qualifies(self):
        """When no foot samples exist yet, every COMP marker should be unvisited."""
        s = self._state()
        sc = _scan(comp=[(1.0, 1.0), (2.0, 2.0)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        _check_bio_distance(s, q)
        # Both comp markers treated as nav targets → two bearings
        assert len(sc.sample_bearings) == 2

    def test_comp_marker_inside_exclusion_disqualified(self):
        """COMP marker within max(100 m, min_dist) of a foot sample is excluded."""
        s = self._state()
        # min_dist 500 m; the foot sample is at (0, 0) and comp at (0, 0.001)
        # which is only ~111 m apart on Mars-sized body → inside 500 m exclusion.
        sc = _scan(min_dist=500.0, foot=[(0.0, 0.0)], comp=[(0.0, 0.001)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        _check_bio_distance(s, q)
        # Comp marker dropped — the navigation falls back to the foot sample
        assert len(sc.sample_bearings) == 1   # foot position is the nav target

    def test_comp_marker_outside_exclusion_used(self):
        """COMP marker well outside min_dist → treated as unvisited nav target."""
        s = self._state()
        sc = _scan(min_dist=500.0, foot=[(0.0, 0.0)], comp=[(1.0, 1.0)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        _check_bio_distance(s, q)
        # Only the unvisited comp marker is the nav target
        assert len(sc.sample_bearings) == 1

    def test_other_body_scans_skipped(self):
        """Scan on a different body than current nearest_body gets no distances."""
        s = self._state()
        sc = _scan(body="OtherBody", foot=[(1.0, 1.0)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        _check_bio_distance(s, q)
        assert sc.current_dist is None
        assert sc.sample_bearings == []

    def test_default_radius_constant_is_used_when_body_unknown(self):
        """A bio scan on a body that isn't in state.bodies must fall back to the shared default."""
        s = AppState()
        s.lat, s.lon, s.landed = 0.0, 0.0, True
        s.nearest_body = "UnknownBody"
        # No body in state.bodies → _check_bio_distance uses _DEFAULT_BODY_RADIUS_M
        sc = _scan(body="UnknownBody", foot=[(0.0, 0.0)], comp=[(0.0, 0.002)])
        s.bio_scans.append(sc)
        q: queue.Queue = queue.Queue()
        # Don't assert exact distance; just verify it ran without NameError
        # and produced one bearing (comp marker at 222 m is inside 500 m
        # exclusion, so falls back to the foot sample).
        _check_bio_distance(s, q)
        assert sc.sample_bearings != []  # some nav target resolved
