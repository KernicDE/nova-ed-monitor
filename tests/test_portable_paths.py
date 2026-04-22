"""Tests for portable-mode path resolution (issue #102)."""
from __future__ import annotations

import shutil
import pytest
from pathlib import Path
from ed_monitor import config


# ── config_dir ────────────────────────────────────────────────────────────────

def test_config_dir_default(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config.config_dir() == Path.home() / ".config" / "nova"


def test_config_dir_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_dir() == tmp_path / "nova"


def test_config_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.config_dir() == tmp_path / "config"


def test_config_dir_portable_takes_priority_over_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config.config_dir() == tmp_path / "config"


# ── data_dir ─────────────────────────────────────────────────────────────────

def test_data_dir_default(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert config.data_dir() == Path.home() / ".local" / "share" / "nova"


def test_data_dir_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert config.data_dir() == tmp_path / "nova"


def test_data_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.data_dir() == tmp_path / "data"


# ── logs_dir ─────────────────────────────────────────────────────────────────

def test_logs_dir_default(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config.logs_dir() == config.config_dir()


def test_logs_dir_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.logs_dir() == tmp_path / "logs"


# ── migrate_from_system_paths ─────────────────────────────────────────────────

def test_migrate_config_on_first_portable_run(tmp_path, monkeypatch):
    """Copies old config dir into portable layout when portable config doesn't exist."""
    old_cfg = tmp_path / "old_config"
    old_cfg.mkdir()
    (old_cfg / "config.toml").write_text("tts_lang = de\n")

    portable_root = tmp_path / "NOVA"
    portable_root.mkdir()
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))

    config.migrate_from_system_paths(old_config_dir=old_cfg, old_data_dir=tmp_path / "nodata")

    assert (portable_root / "config" / "config.toml").read_text() == "tts_lang = de\n"


def test_migrate_db_on_first_portable_run(tmp_path, monkeypatch):
    """Copies old events.db into portable layout when portable db doesn't exist."""
    old_data = tmp_path / "old_data"
    old_data.mkdir()
    (old_data / "events.db").write_bytes(b"SQLite")

    portable_root = tmp_path / "NOVA"
    portable_root.mkdir()
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))

    config.migrate_from_system_paths(old_config_dir=tmp_path / "nocfg", old_data_dir=old_data)

    assert (portable_root / "data" / "events.db").read_bytes() == b"SQLite"


def test_migrate_does_not_overwrite_existing_config(tmp_path, monkeypatch):
    """Never overwrites an existing portable config directory."""
    old_cfg = tmp_path / "old_config"
    old_cfg.mkdir()
    (old_cfg / "config.toml").write_text("old\n")

    portable_root = tmp_path / "NOVA"
    (portable_root / "config").mkdir(parents=True)
    (portable_root / "config" / "config.toml").write_text("new\n")

    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))

    config.migrate_from_system_paths(old_config_dir=old_cfg, old_data_dir=tmp_path / "x")

    assert (portable_root / "config" / "config.toml").read_text() == "new\n"


def test_migrate_does_not_overwrite_existing_db(tmp_path, monkeypatch):
    """Never overwrites an existing portable events.db."""
    old_data = tmp_path / "old_data"
    old_data.mkdir()
    (old_data / "events.db").write_bytes(b"OLD")

    portable_root = tmp_path / "NOVA"
    (portable_root / "data").mkdir(parents=True)
    (portable_root / "data" / "events.db").write_bytes(b"NEW")

    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))

    config.migrate_from_system_paths(old_config_dir=tmp_path / "x", old_data_dir=old_data)

    assert (portable_root / "data" / "events.db").read_bytes() == b"NEW"


def test_migrate_noop_when_not_portable(tmp_path, monkeypatch):
    """migrate_from_system_paths does nothing when NOVA_PORTABLE_ROOT is not set."""
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    old_cfg = tmp_path / "old_config"
    old_cfg.mkdir()
    (old_cfg / "config.toml").write_text("whatever\n")
    # Should not raise; portable config should not be created
    config.migrate_from_system_paths(old_config_dir=old_cfg, old_data_dir=tmp_path)
    assert not (tmp_path / "config").exists()


def test_migrate_skips_missing_old_config(tmp_path, monkeypatch):
    """No error if old config dir doesn't exist."""
    portable_root = tmp_path / "NOVA"
    portable_root.mkdir()
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(portable_root))
    config.migrate_from_system_paths(
        old_config_dir=tmp_path / "nonexistent",
        old_data_dir=tmp_path / "nonexistent",
    )
    assert not (portable_root / "config").exists()


# ── voicelines uses config_dir ────────────────────────────────────────────────

def test_voicelines_config_dir_respects_portable_root(tmp_path, monkeypatch):
    """voicelines._config_dir() must honour NOVA_PORTABLE_ROOT."""
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    import importlib
    import ed_monitor.voicelines as vl
    # _CONFIG_DIR override must be None for this test
    orig = vl._CONFIG_DIR
    vl._CONFIG_DIR = None
    try:
        assert vl._config_dir() == tmp_path / "config"
    finally:
        vl._CONFIG_DIR = orig
