"""Tests for voicelines unit localization and Slavic plural support."""
from __future__ import annotations

import pytest

from ed_monitor import voicelines as vl


class TestUnitFor:
    """unit_for(lang, key, count=None) returns localized unit strings."""

    def test_english_light_years(self):
        assert vl.unit_for("en", "light_years") == "light years"

    def test_german_light_years(self):
        assert vl.unit_for("de", "light_years") == "Lichtjahre"

    def test_french_credits(self):
        assert vl.unit_for("fr", "credits") == "crédits"

    def test_russian_light_years_plural_one(self):
        assert vl.unit_for("ru", "light_years", count=1) == "световой год"

    def test_russian_light_years_plural_few(self):
        assert vl.unit_for("ru", "light_years", count=2) == "световых года"
        assert vl.unit_for("ru", "light_years", count=4) == "световых года"

    def test_russian_light_years_plural_many(self):
        assert vl.unit_for("ru", "light_years", count=5) == "световых лет"
        assert vl.unit_for("ru", "light_years", count=11) == "световых лет"
        assert vl.unit_for("ru", "light_years", count=21) == "световой год"

    def test_russian_light_years_plural_teens(self):
        # 11-14 are "many" in Russian
        assert vl.unit_for("ru", "light_years", count=11) == "световых лет"
        assert vl.unit_for("ru", "light_years", count=12) == "световых лет"
        assert vl.unit_for("ru", "light_years", count=14) == "световых лет"

    def test_fallback_to_english(self):
        assert vl.unit_for("de", "nonexistent_key") == "nonexistent_key"

    def test_fallback_when_lang_missing_entirely(self):
        # "xx" has no TOML file — should fall back to English key
        assert vl.unit_for("xx", "light_years") == "light years"

    def test_scoopable_german(self):
        assert vl.unit_for("de", "scoopable") == "tankbar"

    def test_pop_german(self):
        assert vl.unit_for("de", "Pop") == "Bevölkerung"


class TestSlavicPlural:
    """_slavic_plural(n) returns one/few/many for Russian grammar."""

    def test_one(self):
        assert vl._slavic_plural(1) == "one"
        assert vl._slavic_plural(21) == "one"
        assert vl._slavic_plural(31) == "one"
        assert vl._slavic_plural(101) == "one"

    def test_few(self):
        assert vl._slavic_plural(2) == "few"
        assert vl._slavic_plural(3) == "few"
        assert vl._slavic_plural(4) == "few"
        assert vl._slavic_plural(22) == "few"
        assert vl._slavic_plural(24) == "few"
        assert vl._slavic_plural(104) == "few"

    def test_many(self):
        assert vl._slavic_plural(0) == "many"
        assert vl._slavic_plural(5) == "many"
        assert vl._slavic_plural(10) == "many"
        assert vl._slavic_plural(11) == "many"
        assert vl._slavic_plural(15) == "many"
        assert vl._slavic_plural(20) == "many"
        assert vl._slavic_plural(25) == "many"
        assert vl._slavic_plural(100) == "many"

    def test_teens_are_many(self):
        for n in range(11, 15):
            assert vl._slavic_plural(n) == "many"

    def test_negative_numbers(self):
        assert vl._slavic_plural(-1) == "one"
        assert vl._slavic_plural(-5) == "many"
