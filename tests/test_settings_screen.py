"""Tests for SettingsScreen helpers — voice catalog and row logic."""
from __future__ import annotations

import pytest
from ed_monitor.ui.settings_screen import _parse_voice_catalog


class TestParseCatalog:
    def test_basic_parsing(self):
        voices = [
            {"ShortName": "en-GB-SoniaNeural"},
            {"ShortName": "en-US-GuyNeural"},
            {"ShortName": "de-DE-KatjaNeural"},
        ]
        catalog = _parse_voice_catalog(voices)
        assert "en" in catalog
        assert "GB" in catalog["en"]
        assert "SoniaNeural" in catalog["en"]["GB"]
        assert "US" in catalog["en"]
        assert "GuyNeural" in catalog["en"]["US"]
        assert "de" in catalog
        assert "DE" in catalog["de"]
        assert "KatjaNeural" in catalog["de"]["DE"]

    def test_voices_sorted(self):
        voices = [
            {"ShortName": "en-GB-ZoeNeural"},
            {"ShortName": "en-GB-AbbieNeural"},
            {"ShortName": "en-GB-SoniaNeural"},
        ]
        catalog = _parse_voice_catalog(voices)
        assert catalog["en"]["GB"] == ["AbbieNeural", "SoniaNeural", "ZoeNeural"]

    def test_empty_input(self):
        assert _parse_voice_catalog([]) == {}

    def test_malformed_short_name_skipped(self):
        voices = [{"ShortName": "en-GB"}]  # only 2 parts, not 3
        catalog = _parse_voice_catalog(voices)
        assert catalog == {}
