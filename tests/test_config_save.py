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

    def test_save_emits_prune_events_days_only_when_set(self, tmp_path):
        cfg_off = _dummy_cfg()
        path = tmp_path / "off.toml"
        save(cfg_off, path)
        assert "prune_events_days" not in path.read_text()

        cfg_on = _dummy_cfg(prune_events_days=180)
        path = tmp_path / "on.toml"
        save(cfg_on, path)
        assert "prune_events_days = 180" in path.read_text()


    def test_save_emits_fuel_warning_percent_only_when_not_default(self, tmp_path):
        cfg_default = _dummy_cfg()
        path = tmp_path / "default.toml"
        save(cfg_default, path)
        assert "fuel_warning_percent" not in path.read_text()

        cfg_custom = _dummy_cfg(fuel_warning_percent=10)
        path = tmp_path / "custom.toml"
        save(cfg_custom, path)
        assert "fuel_warning_percent = 10" in path.read_text()

    def test_load_roundtrips_fuel_warning_percent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("fuel_warning_percent = 15\n")
        cfg = load()
        assert cfg.fuel_warning_percent == 15

    def test_load_clamps_fuel_warning_percent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("fuel_warning_percent = 150\n")
        cfg = load()
        assert cfg.fuel_warning_percent == 100

        path.write_text("fuel_warning_percent = -5\n")
        cfg = load()
        assert cfg.fuel_warning_percent == 0

    def test_save_roundtrips_situational_panels(self, tmp_path):
        cfg = _dummy_cfg(situational_panels=["bio", "overview", "missions"])
        path = tmp_path / "config.toml"
        save(cfg, path)
        text = path.read_text()
        assert "situational_panels = BIO OVR MIS" in text

    def test_load_roundtrips_situational_panels(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("situational_panels = OVR BIO MAP\n")
        cfg = load()
        assert cfg.situational_panels == ["overview", "bio", "galaxy"]

    def test_load_ignores_invalid_panel_abbrev(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("situational_panels = OVR BIO XYZ MAP\n")
        cfg = load()
        assert cfg.situational_panels == ["overview", "bio", "galaxy"]

    def test_load_migrates_legacy_abbrevs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("situational_panels = WLT DKG BIO\n")
        cfg = load()
        # WLT -> assets, DKG -> overview (deduplicated), BIO -> bio
        assert cfg.situational_panels == ["assets", "overview", "bio"]

    def test_save_omits_situational_panels_when_empty(self, tmp_path):
        cfg = _dummy_cfg(situational_panels=[])
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "situational_panels" not in path.read_text()


class TestAiVoiceConfig:
    def test_save_omits_ai_voice_keys_at_defaults(self, tmp_path):
        cfg = _dummy_cfg()
        path = tmp_path / "config.toml"
        save(cfg, path)
        text = path.read_text()
        assert "voice_engine" not in text
        assert "ambient_commentary_enabled" not in text
        assert "personality_name" not in text

    def test_save_roundtrips_voice_engine(self, tmp_path):
        cfg = _dummy_cfg(voice_engine="claude")
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "voice_engine = claude" in path.read_text()

    def test_save_roundtrips_ambient_enabled(self, tmp_path):
        cfg = _dummy_cfg(ambient_commentary_enabled=True)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "ambient_commentary_enabled = true" in path.read_text()

    def test_load_roundtrips_voice_engine(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("voice_engine = kimi\n")
        cfg = load()
        assert cfg.voice_engine == "kimi"

    def test_load_rejects_invalid_voice_engine(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("voice_engine = not-a-real-engine\n")
        cfg = load()
        assert cfg.voice_engine == "static"

    def test_load_roundtrips_ambient_settings(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text(
            "ambient_commentary_enabled = true\n"
            "ambient_interval_min_s = 90\n"
            "ambient_interval_max_s = 200\n"
        )
        cfg = load()
        assert cfg.ambient_commentary_enabled is True
        assert cfg.ambient_interval_min_s == 90
        assert cfg.ambient_interval_max_s == 200

    def test_load_swaps_inverted_ambient_interval(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text(
            "ambient_interval_min_s = 300\n"
            "ambient_interval_max_s = 100\n"
        )
        cfg = load()
        assert cfg.ambient_interval_min_s == 100
        assert cfg.ambient_interval_max_s == 300

    def test_load_roundtrips_personality_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ed_monitor.config.config_dir", lambda: tmp_path)
        path = tmp_path / "config.toml"
        path.write_text("personality_name = grumpy\n")
        cfg = load()
        assert cfg.personality_name == "grumpy"

    def test_default_voice_engine_is_static(self):
        cfg = _dummy_cfg()
        assert cfg.voice_engine == "static"
        assert cfg.ambient_commentary_enabled is False
