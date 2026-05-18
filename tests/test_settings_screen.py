"""Tests for SettingsScreen helpers — voice catalog and row logic."""
from __future__ import annotations

import pytest
from ed_monitor.ui.settings_screen import _parse_voice_catalog, ToggleRow, TextRow, SelectRow


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


class TestToggleRow:
    def test_cycle_right(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", False)
        row.cycle(+1)
        assert row.value is True

    def test_cycle_wraps(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", True)
        row.cycle(+1)
        assert row.value is False

    def test_display(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", True)
        assert row.display_value() == "Yes"


class TestSelectRow:
    def test_cycle_right(self):
        row = SelectRow("tts_lang", "TTS Language", "en", ["en", "de", "fr"])
        row.cycle(+1)
        assert row.value == "de"

    def test_cycle_wraps_at_end(self):
        row = SelectRow("tts_lang", "TTS Language", "fr", ["en", "de", "fr"])
        row.cycle(+1)
        assert row.value == "en"

    def test_cycle_left(self):
        row = SelectRow("tts_lang", "TTS Language", "de", ["en", "de", "fr"])
        row.cycle(-1)
        assert row.value == "en"


class TestTextRow:
    def test_initial_value(self):
        row = TextRow("tts_rate", "TTS Rate", "+10%")
        assert row.value == "+10%"

    def test_set_value(self):
        row = TextRow("tts_rate", "TTS Rate", "+10%")
        row.value = "-5%"
        assert row.value == "-5%"


class TestPanelRowCompilation:
    """Simulate the panel-order compilation logic from SettingsScreen._do_save()."""

    def _compile(self, rows: list[TextRow]) -> list[str]:
        _mode_from_key = {f"panel_{mode}": mode for mode, _ in [
            ("overview", "Overview"), ("bio", "Bio"), ("galaxy", "Maps"),
            ("missions", "Missions"), ("engineers", "Engineers"), ("bgs", "BGS"),
            ("colonisation", "Colonisation"), ("route", "Route"), ("neutron", "Neutron"),
            ("assets", "Assets"), ("stats", "Stats"),
        ]}
        panel_orders: list[tuple[int, str]] = []
        for row in rows:
            if row.value.strip():
                try:
                    panel_orders.append((int(row.value.strip()), _mode_from_key[row.key]))
                except (ValueError, KeyError):
                    pass
        panel_orders.sort(key=lambda x: x[0])
        return [mode for _, mode in panel_orders]

    def test_default_order(self):
        rows = [
            TextRow("panel_overview", "Overview", "1"),
            TextRow("panel_bio", "Bio", "2"),
            TextRow("panel_galaxy", "Maps", "3"),
        ]
        assert self._compile(rows) == ["overview", "bio", "galaxy"]

    def test_hidden_panel(self):
        """Empty value means panel is hidden."""
        rows = [
            TextRow("panel_overview", "Overview", "1"),
            TextRow("panel_bio", "Bio", ""),
            TextRow("panel_galaxy", "Maps", "2"),
        ]
        assert self._compile(rows) == ["overview", "galaxy"]

    def test_gaps_in_numbering(self):
        """Gaps like 1, 3, 4 are allowed — sorting still works."""
        rows = [
            TextRow("panel_overview", "Overview", "1"),
            TextRow("panel_bio", "Bio", "3"),
            TextRow("panel_galaxy", "Maps", "4"),
        ]
        assert self._compile(rows) == ["overview", "bio", "galaxy"]

    def test_reorder(self):
        rows = [
            TextRow("panel_overview", "Overview", "3"),
            TextRow("panel_bio", "Bio", "1"),
            TextRow("panel_galaxy", "Maps", "2"),
        ]
        assert self._compile(rows) == ["bio", "galaxy", "overview"]

    def test_all_hidden(self):
        rows = [
            TextRow("panel_overview", "Overview", ""),
            TextRow("panel_bio", "Bio", ""),
        ]
        assert self._compile(rows) == []


    def test_multilingual_voice_filtered(self):
        voices = [
            {"ShortName": "de-DE-KatjaNeural"},
            {"ShortName": "de-DE-SeraphinaMultilingualNeural"},
            {"ShortName": "en-GB-SoniaNeural"},
        ]
        catalog = _parse_voice_catalog(voices)
        assert "de" in catalog
        assert "DE" in catalog["de"]
        assert "KatjaNeural" in catalog["de"]["DE"]
        assert "SeraphinaMultilingualNeural" not in catalog["de"]["DE"]
        assert "en" in catalog
        assert "SoniaNeural" in catalog["en"]["GB"]
