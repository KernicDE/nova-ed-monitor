"""Tests for portable path resolution."""
from __future__ import annotations

from pathlib import Path
from ed_monitor import config
import ed_monitor.voicelines as vl


# ── config_dir ────────────────────────────────────────────────────────────────

def test_config_dir_default_resolves_to_package_parent(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    expected = (Path(__file__).parent.parent / "config").resolve()
    assert config.config_dir().resolve() == expected


def test_config_dir_portable_root_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.config_dir() == tmp_path / "config"


# ── data_dir ─────────────────────────────────────────────────────────────────

def test_data_dir_default_resolves_to_package_parent(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    expected = (Path(__file__).parent.parent / "data").resolve()
    assert config.data_dir().resolve() == expected


def test_data_dir_portable_root_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.data_dir() == tmp_path / "data"


# ── logs_dir ─────────────────────────────────────────────────────────────────

def test_logs_dir_default_resolves_to_package_parent(monkeypatch):
    monkeypatch.delenv("NOVA_PORTABLE_ROOT", raising=False)
    expected = (Path(__file__).parent.parent / "logs").resolve()
    assert config.logs_dir().resolve() == expected


def test_logs_dir_portable_root_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.logs_dir() == tmp_path / "logs"


# ── paths are siblings under the same root ────────────────────────────────────

def test_all_dirs_share_same_root(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    assert config.config_dir().parent == tmp_path
    assert config.data_dir().parent == tmp_path
    assert config.logs_dir().parent == tmp_path


# ── voicelines uses config_dir ────────────────────────────────────────────────

def test_voicelines_config_dir_respects_portable_root(tmp_path, monkeypatch):
    """voicelines._config_dir() must honour NOVA_PORTABLE_ROOT."""
    monkeypatch.setenv("NOVA_PORTABLE_ROOT", str(tmp_path))
    orig = vl._CONFIG_DIR
    vl._CONFIG_DIR = None
    try:
        assert vl._config_dir() == tmp_path / "config"
    finally:
        vl._CONFIG_DIR = orig
