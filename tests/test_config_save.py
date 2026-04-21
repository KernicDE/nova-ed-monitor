"""Tests for config.save() — writes Config back to a TOML-like file."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from ed_monitor.config import Config, save, load


def _dummy_cfg(**overrides) -> Config:
    base = Config(
        journal_dir=Path("/tmp/journals"),
        tts_lang="en",
        tts_rate="+10%",
        default_volume=50,
        notable_value_threshold=500_000,
        carrier_lookup=False,
    )
    for k, v in overrides.items():
        object.__setattr__(base, k, v)
    return base


class TestConfigSave:
    def test_save_creates_file(self, tmp_path):
        cfg = _dummy_cfg()
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert path.exists()

    def test_save_roundtrips_tts_lang(self, tmp_path):
        cfg = _dummy_cfg(tts_lang="de")
        path = tmp_path / "config.toml"
        save(cfg, path)
        text = path.read_text()
        assert "tts_lang = de" in text

    def test_save_roundtrips_volume(self, tmp_path):
        cfg = _dummy_cfg(default_volume=75)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "default_volume = 75" in path.read_text()

    def test_save_roundtrips_tts_rate(self, tmp_path):
        cfg = _dummy_cfg(tts_rate="-5%")
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "tts_rate = -5%" in path.read_text()

    def test_save_roundtrips_carrier_lookup_true(self, tmp_path):
        cfg = _dummy_cfg(carrier_lookup=True)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "carrier_lookup = true" in path.read_text()

    def test_save_roundtrips_tts_voice(self, tmp_path):
        cfg = _dummy_cfg()
        cfg.tts_voices["en"] = "en-US-GuyNeural"
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "tts_voice_en = en-US-GuyNeural" in path.read_text()

    def test_save_roundtrips_notable_value(self, tmp_path):
        cfg = _dummy_cfg(notable_value_threshold=1_000_000)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "notable_value_threshold = 1000000" in path.read_text()
