"""Tests for events.py's _say() routing between the static voiceline system
and the AI voice path (ai_voice.py), gated by set_voice_engine()."""
from __future__ import annotations

import queue

import pytest

import ed_monitor.ai_voice as ai_voice
import ed_monitor.events as events


@pytest.fixture(autouse=True)
def reset_voice_engine():
    events.set_voice_engine("static")
    yield
    events.set_voice_engine("static")


def test_static_engine_speaks_directly_without_ai_voice(monkeypatch):
    submitted = []
    monkeypatch.setattr(ai_voice, "submit", lambda req: submitted.append(req))

    tts_q: "queue.Queue" = queue.Queue()
    events.set_voice_engine("static")
    events._say(tts_q, "NoSuchKeyForTest", False, fallback="Static fallback line.")

    msg = tts_q.get_nowait()
    assert "Static fallback line." in msg.text
    assert submitted == []


def test_ai_engine_routes_through_ai_voice_submit(monkeypatch):
    submitted = []
    monkeypatch.setattr(ai_voice, "submit", lambda req: submitted.append(req))

    tts_q: "queue.Queue" = queue.Queue()
    events.set_voice_engine("claude")
    events._say(tts_q, "NoSuchKeyForTest", False, fallback="AI fallback line.")

    assert tts_q.empty()
    assert len(submitted) == 1
    req = submitted[0]
    assert req.fallback_text == "AI fallback line."
    assert req.groupable is False


def test_groupable_key_sets_groupable_flag(monkeypatch):
    submitted = []
    monkeypatch.setattr(ai_voice, "submit", lambda req: submitted.append(req))

    tts_q: "queue.Queue" = queue.Queue()
    events.set_voice_engine("kimi")
    events._say(tts_q, "Scan_Notable", False, fallback="Notable body found.")

    assert submitted[-1].groupable is True


def test_muted_key_produces_no_request_in_either_engine(monkeypatch):
    import ed_monitor.voicelines as vl

    submitted = []
    monkeypatch.setattr(ai_voice, "submit", lambda req: submitted.append(req))
    monkeypatch.setattr(vl, "is_muted", lambda key, lang="en": True)

    tts_q: "queue.Queue" = queue.Queue()
    events.set_voice_engine("claude")
    events._say(tts_q, "AnyKey", False, fallback="Should not be spoken.")

    assert tts_q.empty()
    assert submitted == []
