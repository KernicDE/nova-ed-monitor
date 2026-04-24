"""Shared HTTP constants must stay in sync across modules (R-13)."""
from __future__ import annotations

from ed_monitor import _http


def test_user_agent_names_the_project():
    ua = _http.USER_AGENT
    assert ua.startswith("nova-ed-monitor/")
    # Comment block with GitHub URL so operators can trace traffic.
    assert "github.com/KernicDE/nova-ed-monitor" in ua


def test_timeout_hierarchy():
    # Short < Medium < Long < Dump — modules should pick the smallest that fits.
    assert _http.TIMEOUT_SHORT < _http.TIMEOUT_MEDIUM < _http.TIMEOUT_LONG < _http.TIMEOUT_DUMP


def test_all_http_modules_use_shared_ua():
    """Regression guard — a new outbound module must pull USER_AGENT from _http."""
    import ed_monitor.edsm as edsm
    import ed_monitor.edsm_dumps as edsm_dumps
    import ed_monitor.spansh as spansh
    import ed_monitor.neutron as neutron
    import ed_monitor.journal as journal

    # Every module should reference the shared constant.
    for mod in (edsm, edsm_dumps, spansh, neutron, journal):
        source = open(mod.__file__, encoding="utf-8").read()
        assert "USER_AGENT" in source, f"{mod.__name__} does not import USER_AGENT"
