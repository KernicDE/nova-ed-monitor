"""Tests for status.py materials parsing and zero-fill behaviour."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from ed_monitor.state import AppState
from ed_monitor.status import _apply_materials
from ed_monitor.materials_catalog import (
    RAW_CATEGORIES, MANUFACTURED_CATEGORIES, ENCODED_CATEGORIES,
)


def _write_materials(tmp_path: Path, raw=None, manufactured=None, encoded=None) -> Path:
    data: dict = {}
    if raw is not None:
        data["Raw"] = raw
    if manufactured is not None:
        data["Manufactured"] = manufactured
    if encoded is not None:
        data["Encoded"] = encoded
    path = tmp_path / "Materials.json"
    path.write_text(json.dumps(data))
    return path


def test_materials_zero_filled_from_catalogue(tmp_path: Path):
    """Missing entries in Materials.json should be zero-filled from the catalogue."""
    state = AppState()
    # Only Carbon present
    path = _write_materials(
        tmp_path,
        raw=[{"Name": "carbon", "Name_Localised": "Carbon", "Count": 42}],
    )
    _apply_materials(path, state, threading.RLock())

    assert state.materials_raw["Carbon"] == 42
    # Other raw materials should be present with count 0
    assert state.materials_raw["Vanadium"] == 0
    assert state.materials_raw["Yttrium"] == 0
    # Manufactured/Encoded are also zero-filled from catalogue even when
    # absent from JSON so the tracker can show missing materials.
    assert state.materials_mfg["Chemical Storage Units"] == 0
    assert state.materials_enc["Exceptional Scrambled Emission Data"] == 0


def test_materials_full_catalogue_present(tmp_path: Path):
    """All catalogue materials should be present after parsing."""
    state = AppState()
    path = _write_materials(tmp_path, raw=[], manufactured=[], encoded=[])
    _apply_materials(path, state, threading.RLock())

    raw_total = sum(len(mats) for _, mats in RAW_CATEGORIES)
    mfg_total = sum(len(mats) for _, mats in MANUFACTURED_CATEGORIES)
    enc_total = sum(len(mats) for _, mats in ENCODED_CATEGORIES)

    assert len(state.materials_raw) == raw_total
    assert len(state.materials_mfg) == mfg_total
    assert len(state.materials_enc) == enc_total

    # All counts should be zero
    assert all(v == 0 for v in state.materials_raw.values())
    assert all(v == 0 for v in state.materials_mfg.values())
    assert all(v == 0 for v in state.materials_enc.values())


def test_materials_unknown_ingredients_still_parsed(tmp_path: Path):
    """Materials not in the catalogue should still be preserved if present."""
    state = AppState()
    path = _write_materials(
        tmp_path,
        raw=[
            {"Name": "carbon", "Name_Localised": "Carbon", "Count": 10},
            {"Name": "unknown_stuff", "Name_Localised": "Mystery Goo", "Count": 5},
        ],
    )
    _apply_materials(path, state, threading.RLock())

    assert state.materials_raw["Carbon"] == 10
    assert state.materials_raw["Mystery Goo"] == 5
