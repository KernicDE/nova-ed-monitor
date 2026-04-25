"""Tests for _body_value and _body_value_color (issue #98).

Verifies that:
- FSS'd bodies never use EDSM values (always formula-based)
- FSS'd but unmapped bodies always assume efficiency bonus (×1.25)
- Correct DSS multiplier is chosen based on first_discovered / first_mapped flags
- _body_value_color returns the correct tier color
"""
from __future__ import annotations

import pytest
from ed_monitor.state import BodyInfo
from ed_monitor.ui import palette as P
from ed_monitor.ui.panels import _body_value, _body_value_color, _estimated_value


def _body(
    *,
    planet_class: str = "Rocky body",
    mass_em: float = 5.0,
    value: int = 0,
    fss_scanned: bool = False,
    mapped: bool = False,
    first_discovered: bool = False,
    first_mapped: bool = False,
    efficiency_bonus: bool = False,
    first_footfall: bool = False,
    terraform: bool = False,
) -> BodyInfo:
    return BodyInfo(
        name="Test A 1", body_id=1, level=1,
        planet_class=planet_class, star_type="", atmosphere="",
        terraform=terraform, landable=True,
        bio_signals=0, geo_signals=0, bio_genuses=[],
        dist_ls=100.0, value=value,
        first_discovered=first_discovered, first_mapped=first_mapped,
        mapped=mapped, fss_scanned=fss_scanned, radius=500_000.0,
        mass_em=mass_em,
        efficiency_bonus=efficiency_bonus,
        first_footfall=first_footfall,
    )


# ── Base value ────────────────────────────────────────────────────────────────

class TestBaseValueSelection:
    def test_fss_scanned_uses_formula_not_edsm(self):
        """FSS'd body must ignore b.value (EDSM) and use the formula."""
        edsm_value = 999_999_999  # artificially large EDSM value
        b = _body(fss_scanned=True, value=edsm_value, mass_em=5.0)
        formula_base = _estimated_value(b)
        result = _body_value(b)
        # result should be formula × DSS multiplier × efficiency, not anywhere near edsm_value
        assert result != edsm_value
        # result must be consistent with formula base × 3.3333 × 1.25 (no-bonus case)
        expected = int(formula_base * 3.3333333333 * 1.25)
        assert result == expected

    def test_non_fss_uses_edsm_value(self):
        """Non-FSS'd body with a stored EDSM value should use it."""
        b = _body(fss_scanned=False, value=50_000, mass_em=0.0)
        result = _body_value(b)
        # No-bonus: 50000 × 3.3333 = 166665
        assert result == int(50_000 * 3.3333333333)

    def test_non_fss_no_edsm_falls_back_to_table(self):
        """Non-FSS'd body with no EDSM value falls back to table estimate."""
        b = _body(fss_scanned=False, value=0, mass_em=0.0, planet_class="Rocky body")
        result = _body_value(b)
        assert result > 0  # table has a value for Rocky body


# ── FSS'd unmapped: maximum projected payout ─────────────────────────────────

class TestFSSdUnmappedProjected:
    def test_no_bonus_applies_efficiency(self):
        """FSS'd, no first_mapped/first_discovered → basic DSS × efficiency."""
        b = _body(fss_scanned=True, mass_em=5.0)
        base = _estimated_value(b)
        expected = int(base * 3.3333333333 * 1.25)
        assert _body_value(b) == expected

    def test_first_mapped_applies_efficiency(self):
        """FSS'd + first_mapped → 3.6996 × efficiency."""
        b = _body(fss_scanned=True, first_mapped=True, mass_em=5.0)
        base = _estimated_value(b)
        expected = int(base * 3.699622554 * 1.25)
        assert _body_value(b) == expected

    def test_first_discovered_and_mapped_applies_efficiency(self):
        """FSS'd + first_discovered + first_mapped → 3.3333 × 1.25 × 3.692 (ODExplorer stacking)."""
        b = _body(fss_scanned=True, first_discovered=True, first_mapped=True, mass_em=5.0)
        base = _estimated_value(b)
        expected = int(base * 3.3333333333 * 1.25 * 3.692)
        assert _body_value(b) == expected

    def test_first_discovered_no_first_mapped_no_bonus(self):
        """FSS'd + first_discovered only (already mapped by others) → basic DSS × efficiency."""
        b = _body(fss_scanned=True, first_discovered=True, first_mapped=False, mass_em=5.0)
        base = _estimated_value(b)
        expected = int(base * 3.3333333333 * 1.25)
        assert _body_value(b) == expected


# ── Mapped (actual payout) ────────────────────────────────────────────────────

class TestMappedActualPayout:
    def test_mapped_no_bonus(self):
        """Already mapped by others → 3.3333 (no efficiency unless flag set)."""
        b = _body(fss_scanned=True, mapped=True, mass_em=5.0)
        base = _estimated_value(b)
        assert _body_value(b) == int(base * 3.3333333333)

    def test_mapped_with_efficiency(self):
        """DSS'd with efficiency → 3.3333 × 1.25."""
        b = _body(fss_scanned=True, mapped=True, efficiency_bonus=True, mass_em=5.0)
        base = _estimated_value(b)
        assert _body_value(b) == int(base * 3.3333333333 * 1.25)

    def test_mapped_first_mapped(self):
        """First mapper → 3.6996."""
        b = _body(fss_scanned=True, mapped=True, first_mapped=True, mass_em=5.0)
        base = _estimated_value(b)
        assert _body_value(b) == int(base * 3.699622554)

    def test_mapped_first_disc_and_map_with_efficiency(self):
        """First disc + first map + efficiency."""
        b = _body(fss_scanned=True, mapped=True,
                  first_discovered=True, first_mapped=True,
                  efficiency_bonus=True, mass_em=5.0)
        base = _estimated_value(b)
        assert _body_value(b) == int(base * 8.0956 * 1.25)

    def test_mapped_first_footfall(self):
        """First footfall adds 30% on top of mapped value."""
        b = _body(fss_scanned=True, mapped=True, first_footfall=True, mass_em=5.0)
        base = _estimated_value(b)
        assert _body_value(b) == int(int(base * 3.3333333333) * 1.30)


# ── Color tiers ───────────────────────────────────────────────────────────────

class TestBodyValueColor:
    def test_non_fss_with_edsm_value(self):
        b = _body(fss_scanned=False, value=50_000)
        assert _body_value_color(b) == P.AMBER

    def test_non_fss_no_value(self):
        b = _body(fss_scanned=False, value=0)
        assert _body_value_color(b) == P.DIM

    def test_fss_no_bonus(self):
        b = _body(fss_scanned=True, first_discovered=False, first_mapped=False)
        assert _body_value_color(b) == "white"

    def test_fss_first_discovered_no_first_mapped(self):
        """first_discovered without first_mapped → no map bonus → white."""
        b = _body(fss_scanned=True, first_discovered=True, first_mapped=False)
        assert _body_value_color(b) == "white"

    def test_fss_first_mapped(self):
        b = _body(fss_scanned=True, first_discovered=False, first_mapped=True)
        assert _body_value_color(b) == P.AMBER

    def test_fss_first_discovered_and_mapped(self):
        b = _body(fss_scanned=True, first_discovered=True, first_mapped=True)
        assert _body_value_color(b) == P.GOLD
