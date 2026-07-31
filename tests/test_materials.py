"""Tests for material tracking (Materials / MaterialCollected / MaterialDiscarded)."""
from __future__ import annotations

import queue

from ed_monitor.events import handle
from ed_monitor.state import AppState
from ed_monitor.materials_catalog import lookup_fuzzy


def _collected(name: str, count: int, category: str = "Encoded") -> dict:
    return {"event": "MaterialCollected", "Category": category,
            "Name": name, "Count": count}


def test_material_collected_adds_and_bumps_version():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_collected("atypicalencryptionarchives", 12), state, q)
    assert state.materials_enc["Atypical Encryption Archives"] == 12
    assert state.materials_version == 1


def test_material_collected_clamps_to_cap():
    """The journal reports full amounts even when the game silently discards
    everything above the per-material cap — NOVA must clamp."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    info = lookup_fuzzy("atypicalencryptionarchives")
    assert info is not None
    handle(_collected("atypicalencryptionarchives", info.cap - 5), state, q)
    handle(_collected("atypicalencryptionarchives", 12), state, q)
    assert state.materials_enc["Atypical Encryption Archives"] == info.cap
    assert state.materials_version == 2


def test_real_journal_internal_names_resolve():
    """Internal names as written by the game client (verified against live
    journals) must resolve to catalogue entries — otherwise counts land in
    unclamped localised fallback rows."""
    assert lookup_fuzzy("encryptionarchives") is not None
    assert lookup_fuzzy("encryptionarchives").name == "Atypical Encryption Archives"
    assert lookup_fuzzy("adaptiveencryptors").name == "Adaptive Encryptors Capture"
    assert lookup_fuzzy("encryptedfiles").name == "Unusual Encrypted Files"
    assert lookup_fuzzy("encryptioncodes").name == "Tagged Encryption Codes"


def test_material_trade_moves_counts():
    """Trading at a material trader must update counts live: Paid is
    subtracted, Received is added (clamped to cap)."""
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_collected("adaptiveencryptors", 100), state, q)
    handle({"event": "MaterialTrade",
            "Paid":     {"Material": "adaptiveencryptors", "Category": "Encoded", "Quantity": 22},
            "Received": {"Material": "symmetrickeys", "Category": "Encoded", "Quantity": 198}},
           state, q)
    assert state.materials_enc["Adaptive Encryptors Capture"] == 78
    # Open Symmetric Keys is G3 (cap 200) — 198 fits
    assert state.materials_enc["Open Symmetric Keys"] == 198
    assert state.materials_version == 2


def test_material_trade_received_clamped_to_cap():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_collected("scandatabanks", 150), state, q)
    handle({"event": "MaterialTrade",
            "Paid":     {"Material": "bulkscandata", "Category": "Encoded", "Quantity": 30},
            "Received": {"Material": "scandatabanks", "Category": "Encoded", "Quantity": 100}},
           state, q)
    # Classified Scan Databanks is G3 (cap 200)
    assert state.materials_enc["Classified Scan Databanks"] == 200
    # Paid material was never owned — floors at 0
    assert state.materials_enc["Anomalous Bulk Scan Data"] == 0


def test_material_collected_unknown_material_not_clamped():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_collected("Unbekanntes Material", 9999), state, q)
    assert state.materials_enc["Unbekanntes Material"] == 9999


def test_material_discarded_floors_at_zero_and_bumps_version():
    state = AppState()
    q: queue.Queue = queue.Queue()
    handle(_collected("iron", 10, "Raw"), state, q)
    handle({"event": "MaterialDiscarded", "Category": "Raw",
            "Name": "iron", "Count": 15}, state, q)
    assert state.materials_raw["Iron"] == 0
    assert state.materials_version == 2


def test_materials_event_replaces_and_bumps_version():
    state = AppState()
    q: queue.Queue = queue.Queue()
    state.materials_enc["Atypical Encryption Archives"] = 50
    handle({"event": "Materials", "Raw": [], "Manufactured": [],
            "Encoded": [{"Name": "atypicalencryptionarchives", "Count": 93}]},
           state, q)
    assert state.materials_enc == {"Atypical Encryption Archives": 93}
    assert state.materials_version == 1
