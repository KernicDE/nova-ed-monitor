"""Tests for TTS cache and helper functions."""
from __future__ import annotations

import pytest
from pathlib import Path
from ed_monitor import tts


class TestClearCache:
    def test_clear_cache_removes_mp3_and_sig(self, monkeypatch, tmp_path):
        cache_dir = tmp_path / "cache" / "tts"
        cache_dir.mkdir(parents=True)
        sig_file = tmp_path / "cache" / "voice.sig"

        # Create dummy cached files
        mp3 = cache_dir / "abc123.mp3"
        mp3.write_text("dummy mp3")
        sig_file.write_text("en-GB-SoniaNeural|+10%")

        # Monkeypatch _cache_dir to return our temp path
        monkeypatch.setattr(tts, "_cache_dir", lambda: cache_dir)

        tts.clear_cache()

        assert not mp3.exists()
        assert not sig_file.exists()

    def test_clear_cache_survives_missing_files(self, monkeypatch, tmp_path):
        cache_dir = tmp_path / "cache" / "tts"
        cache_dir.mkdir(parents=True)
        monkeypatch.setattr(tts, "_cache_dir", lambda: cache_dir)

        # Should not raise even when cache is already empty
        tts.clear_cache()
