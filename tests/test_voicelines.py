"""Tests for voicelines.py — silence fix and validation."""
from __future__ import annotations

from pathlib import Path
import pytest

import ed_monitor.voicelines as vl


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Point voicelines at a temp dir so tests don't touch ~/.config/nova."""
    monkeypatch.setattr(vl, "_CONFIG_DIR", tmp_path)
    vl._CACHE.clear()
    yield
    vl._CACHE.clear()


def _write_user_file(tmp_path: Path, lang: str, content: str) -> None:
    d = tmp_path / "voicelines"
    d.mkdir(exist_ok=True)
    (d / f"{lang}.toml").write_text(content, encoding="utf-8")


class TestIsMuted:
    def test_not_muted_when_key_absent(self):
        assert vl.is_muted("SomeEvent", "en") is False

    def test_not_muted_when_replace_has_lines(self, tmp_path):
        _write_user_file(tmp_path, "en", '[FSDJump]\nreplace = ["Jumping."]\n')
        assert vl.is_muted("FSDJump", "en") is False

    def test_muted_when_replace_empty(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("FSDJump", "en") is True

    def test_muted_does_not_affect_other_keys(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("Docked", "en") is False

    def test_muted_for_lang_only(self, tmp_path):
        """Silencing in 'de' does not silence 'en'."""
        _write_user_file(tmp_path, "de", "[FSDJump]\nreplace = []\n")
        assert vl.is_muted("FSDJump", "de") is True
        assert vl.is_muted("FSDJump", "en") is False


class TestSilencePropagation:
    """Verify that replace=[] prevents any TTS output, even when a fallback exists."""

    def test_pick_returns_none_when_silenced(self, tmp_path):
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        result = vl.pick("FSDJump", lang="en")
        assert result is None

    def test_is_muted_true_blocks_fallback(self, tmp_path):
        """
        Simulate what _say() should do:
        if is_muted → skip, even if fallback is non-empty.
        """
        _write_user_file(tmp_path, "en", "[FSDJump]\nreplace = []\n")
        fallback = "Jumping to hyperspace."
        # Current (broken) behaviour: pick() or fallback → speaks fallback
        broken = vl.pick("FSDJump", lang="en") or fallback
        assert broken == fallback  # documents the bug

        # Correct behaviour: check is_muted first
        if vl.is_muted("FSDJump", "en"):
            text = None
        else:
            text = vl.pick("FSDJump", lang="en") or fallback
        assert text is None
