"""Tests for spansh.py response parsing (R-12)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import io
import json

import pytest

from ed_monitor.spansh import _fetch_carriers_query


class _FakeResp(io.BytesIO):
    """Minimal urlopen-compatible response wrapper."""
    def __init__(self, payload: dict | list | str):
        raw = json.dumps(payload).encode("utf-8") if not isinstance(payload, str) else payload.encode()
        super().__init__(raw)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fake_urlopen(payload):
    return lambda req, timeout=None: _FakeResp(payload)


def test_missing_results_field_returns_empty():
    with patch("urllib.request.urlopen", _fake_urlopen({"message": "oops"})):
        assert _fetch_carriers_query(system_name="Sol") == []


def test_results_not_a_list_returns_empty():
    with patch("urllib.request.urlopen", _fake_urlopen({"results": "oops"})):
        assert _fetch_carriers_query(system_name="Sol") == []


def test_non_dict_entries_skipped():
    payload = {"results": ["oops", {"name": "Good", "system_name": "Sol"}]}
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        result = _fetch_carriers_query(system_name="Sol")
        assert [c["name"] for c in result] == ["Good"]


def test_unnamed_carrier_skipped():
    payload = {"results": [{"system_name": "Sol"}, {"name": "Good", "system_name": "Sol"}]}
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        result = _fetch_carriers_query(system_name="Sol")
        assert [c["name"] for c in result] == ["Good"]


def test_wrong_type_name_skipped():
    payload = {"results": [{"name": 42}, {"name": "Good"}]}
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        result = _fetch_carriers_query(system_name="Sol")
        assert [c["name"] for c in result] == ["Good"]


def test_non_numeric_coords_default_to_zero():
    payload = {"results": [{
        "name": "X", "system_name": "Sol",
        "system_x": "huh", "system_y": None, "system_z": 5.0,
        "distance_to_arrival": "what",
    }]}
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        result = _fetch_carriers_query(system_name="Sol")
        assert result[0]["sys_x"] == 0.0
        assert result[0]["sys_y"] == 0.0
        assert result[0]["sys_z"] == 5.0
        assert result[0]["dist_ls"] == 0.0


def test_full_valid_row_round_trips():
    payload = {"results": [{
        "name": "T.N. Jewel", "system_name": "Beagle Point",
        "system_x": 10.0, "system_y": -20.0, "system_z": 65000.0,
        "distance_to_arrival": 500.0,
        "updated_at": "2026-01-01T00:00:00",
        "has_market": True, "has_shipyard": False, "has_outfitting": True,
    }]}
    with patch("urllib.request.urlopen", _fake_urlopen(payload)):
        c = _fetch_carriers_query(system_name="Beagle Point")[0]
    assert c["name"] == "T.N. Jewel"
    assert c["system_name"] == "Beagle Point"
    assert c["sys_x"] == 10.0 and c["sys_z"] == 65000.0
    assert c["market"] is True and c["shipyard"] is False
    assert c["dist_ls"] == 500.0
