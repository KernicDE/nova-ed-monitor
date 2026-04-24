"""Tests for the config-watcher quiet window (R-8)."""
from __future__ import annotations

import time

import pytest

import ed_monitor.config_watcher as cw


@pytest.fixture(autouse=True)
def reset_quiet_window():
    """notify_self_write writes to a module-global; clear it between tests
    so one test's window doesn't keep the next one in quiet mode."""
    with cw._quiet_lock:
        cw._quiet_until = 0.0
    yield
    with cw._quiet_lock:
        cw._quiet_until = 0.0


def test_quiet_window_default_is_inactive():
    assert cw._in_quiet_window() is False


def test_notify_self_write_opens_window():
    cw.notify_self_write(window_s=2.0)
    assert cw._in_quiet_window() is True


def test_quiet_window_expires():
    cw.notify_self_write(window_s=0.05)
    assert cw._in_quiet_window() is True
    time.sleep(0.1)
    assert cw._in_quiet_window() is False


def test_overlapping_windows_take_latest_expiry():
    cw.notify_self_write(window_s=0.05)   # short
    cw.notify_self_write(window_s=1.0)    # longer — should dominate
    time.sleep(0.1)
    assert cw._in_quiet_window() is True


def test_config_load_opens_quiet_window_after_rewrite(tmp_path, monkeypatch):
    """When config.load() rewrites the file (old format), the watcher should
    be told to stay quiet so the resulting mtime change doesn't loop back."""
    from ed_monitor import config
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    # Write an old-format file without "# overlay_dir" so load() rewrites it.
    (tmp_path / "config.toml").write_text("tts_lang = de\n", encoding="utf-8")
    config.load()
    assert cw._in_quiet_window() is True
