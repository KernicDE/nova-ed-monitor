"""Tests for personality.py — default/override merge, prompt fragment rendering."""
from __future__ import annotations

from pathlib import Path
import pytest

import ed_monitor.personality as personality


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Point personality at a temp dir so tests don't touch ~/.config/nova."""
    monkeypatch.setattr(personality, "_CONFIG_DIR", tmp_path)
    personality._CACHE.clear()
    yield
    personality._CACHE.clear()


def _write_user_file(tmp_path: Path, name: str, content: str) -> None:
    d = tmp_path / "personality"
    d.mkdir(exist_ok=True)
    (d / f"{name}.toml").write_text(content, encoding="utf-8")


class TestLoadBuiltinDefault:
    def test_builtin_default_loads(self):
        fragment = personality.get_prompt_fragment("default")
        assert "NOVA" in fragment

    def test_unknown_name_falls_back_to_builtin_default(self):
        fragment = personality.get_prompt_fragment("does-not-exist")
        assert "NOVA" in fragment


class TestUserOverride:
    def test_user_file_overrides_name(self, tmp_path):
        _write_user_file(tmp_path, "default", 'name = "Custom AI"\n')
        fragment = personality.get_prompt_fragment("default")
        assert "Custom AI" in fragment

    def test_user_file_partial_override_keeps_other_builtin_fields(self, tmp_path):
        _write_user_file(tmp_path, "default", 'tone = "Extremely sarcastic."\n')
        fragment = personality.get_prompt_fragment("default")
        assert "Extremely sarcastic." in fragment
        # traits/speech_style from the built-in default should still be present
        assert "Traits:" in fragment


class TestReload:
    def test_reload_picks_up_new_user_file(self, tmp_path):
        fragment_before = personality.get_prompt_fragment("default")
        assert "Custom AI" not in fragment_before
        _write_user_file(tmp_path, "default", 'name = "Custom AI"\n')
        personality.reload("default")
        fragment_after = personality.get_prompt_fragment("default")
        assert "Custom AI" in fragment_after

    def test_reload_all_clears_cache(self, tmp_path):
        personality.get_prompt_fragment("default")
        assert "default" in personality._CACHE
        personality.reload_all()
        assert personality._CACHE == {}


class TestValidateUserFile:
    def test_no_file_returns_none(self):
        assert personality.validate_user_file("default") is None

    def test_valid_file_returns_none(self, tmp_path):
        _write_user_file(tmp_path, "default", 'name = "OK"\n')
        assert personality.validate_user_file("default") is None

    def test_invalid_toml_returns_error_message(self, tmp_path):
        _write_user_file(tmp_path, "default", "this is not valid toml [[[")
        error = personality.validate_user_file("default")
        assert error is not None
        assert "syntax error" in error


class TestEnsureUserFiles:
    def test_creates_dir_readme_and_reference_copy(self, tmp_path):
        personality.ensure_user_files()
        d = tmp_path / "personality"
        assert d.is_dir()
        assert (d / "README.md").exists()
        assert (d / "default" / "default.default.toml").exists()
