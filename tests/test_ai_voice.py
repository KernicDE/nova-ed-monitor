"""Tests for ai_voice.py — subprocess fallback, output sanitization, burst grouping."""
from __future__ import annotations

import queue
import subprocess
import threading
import time

import pytest

import ed_monitor.ai_voice as ai_voice
import ed_monitor.events as events


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    # Isolate personality lookups from the real ~/.config/nova
    import ed_monitor.personality as personality
    monkeypatch.setattr(personality, "_CONFIG_DIR", tmp_path)
    personality._CACHE.clear()

    ai_voice._ENGINE = "static"
    ai_voice._TIMEOUT_S = 12.0
    ai_voice._BURST_WINDOW_S = 2.5
    ai_voice._PERSONALITY_NAME = "default"
    with ai_voice._burst_lock:
        ai_voice._burst_buffers.clear()
        ai_voice._burst_timers.clear()
    # Drain any stray items from a previous test
    while True:
        try:
            ai_voice._ai_q.get_nowait()
        except queue.Empty:
            break
    events.set_tts_lang("en")
    yield
    events.set_tts_lang("en")


class _FakeCfg:
    voice_engine = "static"
    ai_voice_timeout_s = 12.0
    ai_voice_burst_window_s = 2.5
    personality_name = "default"


class TestConfigure:
    def test_configure_applies_all_fields(self):
        cfg = _FakeCfg()
        cfg.voice_engine = "claude"
        cfg.ai_voice_timeout_s = 5.0
        cfg.ai_voice_burst_window_s = 1.0
        cfg.personality_name = "custom"
        ai_voice.configure(cfg)
        assert ai_voice.get_engine() == "claude"
        assert ai_voice._TIMEOUT_S == 5.0
        assert ai_voice._BURST_WINDOW_S == 1.0
        assert ai_voice._PERSONALITY_NAME == "custom"


class TestGenerateFallback:
    def test_missing_binary_returns_none(self):
        result = ai_voice._generate("definitely-not-a-real-cli-xyz", "hello", 2.0)
        assert result is None

    def test_timeout_returns_none(self, monkeypatch):
        def _raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)
        monkeypatch.setattr(subprocess, "run", _raise_timeout)
        assert ai_voice._generate("claude", "hello", 1.0) is None

    def test_nonzero_exit_returns_none(self, monkeypatch):
        class _Result:
            returncode = 1
            stdout = ""
            stderr = "boom"
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        assert ai_voice._generate("claude", "hello", 2.0) is None

    def test_empty_output_returns_none(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "   \n  "
            stderr = ""
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        assert ai_voice._generate("claude", "hello", 2.0) is None

    def test_successful_output_sanitized(self, monkeypatch):
        class _Result:
            returncode = 0
            stdout = "  **Hull at 80 percent.**\nStay sharp.  "
            stderr = ""
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())
        result = ai_voice._generate("claude", "hello", 2.0)
        assert result == "Hull at 80 percent. Stay sharp."


class TestBuildPromptLanguage:
    """Regression test for the language-mixing bug: the AI CLI must be told
    explicitly which language to respond in, otherwise it drifts between
    English (matching the English prompt/context) and the configured
    tts_lang depending on the model's mood."""

    def test_prompt_instructs_configured_language(self):
        events.set_tts_lang("de")
        req = ai_voice.AiVoiceRequest(prompt_intent="FSDJump", fallback_text="Jump complete.")
        prompt = ai_voice._build_prompt(req)
        assert "German (de)" in prompt

    def test_prompt_defaults_to_english(self):
        events.set_tts_lang("en")
        req = ai_voice.AiVoiceRequest(prompt_intent="FSDJump", fallback_text="Jump complete.")
        prompt = ai_voice._build_prompt(req)
        assert "English (en)" in prompt

    def test_prompt_uses_language_name_for_each_supported_code(self):
        for code, name in ai_voice._LANGUAGE_NAMES.items():
            events.set_tts_lang(code)
            prompt = ai_voice._build_prompt(ai_voice.AiVoiceRequest(prompt_intent="x"))
            assert f"{name} ({code})" in prompt


class TestSanitizeOutput:
    def test_strips_markdown_and_collapses_newlines(self):
        assert ai_voice._sanitize_output("  **Hello** there\n\nWorld  ") == "Hello there  World"

    def test_truncates_long_output(self):
        text = "word " * 200
        result = ai_voice._sanitize_output(text)
        assert len(result) <= ai_voice._MAX_OUTPUT_CHARS + 1
        assert result.endswith("…")


class TestSubmitAndWorker:
    def _run_worker(self, tts_q, stop_evt, engine="claude", burst_window=None):
        cfg = _FakeCfg()
        cfg.voice_engine = engine
        if burst_window is not None:
            cfg.ai_voice_burst_window_s = burst_window
        # Apply synchronously before the worker thread starts so submit()
        # (called from the test/main thread right after this) already sees
        # the intended engine/burst-window instead of racing worker's own
        # configure(cfg) call at thread start.
        ai_voice.configure(cfg)
        t = threading.Thread(target=ai_voice.worker, args=(cfg, tts_q, stop_evt), daemon=True)
        t.start()
        return t

    def test_non_groupable_request_uses_ai_result(self, monkeypatch):
        monkeypatch.setattr(ai_voice, "_generate", lambda engine, prompt, timeout: "AI reply")

        tts_q = queue.Queue()
        stop_evt = threading.Event()
        t = self._run_worker(tts_q, stop_evt, engine="claude")
        try:
            ai_voice.submit(ai_voice.AiVoiceRequest(prompt_intent="test", fallback_text="fallback"))
            msg = tts_q.get(timeout=2)
            assert msg.text == "AI reply"
        finally:
            stop_evt.set()
            t.join(timeout=2)

    def test_ai_failure_falls_back_to_static_text(self, monkeypatch):
        monkeypatch.setattr(ai_voice, "_generate", lambda engine, prompt, timeout: None)

        tts_q = queue.Queue()
        stop_evt = threading.Event()
        t = self._run_worker(tts_q, stop_evt, engine="claude")
        try:
            ai_voice.submit(ai_voice.AiVoiceRequest(prompt_intent="test", fallback_text="FALLBACK TEXT"))
            msg = tts_q.get(timeout=2)
            assert msg.text == "FALLBACK TEXT"
        finally:
            stop_evt.set()
            t.join(timeout=2)

    def test_static_engine_request_uses_fallback_directly(self, monkeypatch):
        """If a stray request arrives while engine == static, speak the fallback
        without ever calling _generate (defensive path, e.g. race during a
        live engine switch)."""
        calls = []
        monkeypatch.setattr(ai_voice, "_generate", lambda *a, **k: calls.append(1))

        tts_q = queue.Queue()
        stop_evt = threading.Event()
        t = self._run_worker(tts_q, stop_evt, engine="static")
        try:
            ai_voice.submit(ai_voice.AiVoiceRequest(prompt_intent="test", fallback_text="STATIC FALLBACK"))
            msg = tts_q.get(timeout=2)
            assert msg.text == "STATIC FALLBACK"
            assert calls == []
        finally:
            stop_evt.set()
            t.join(timeout=2)

    def test_burst_grouping_collapses_to_one_ai_call(self, monkeypatch):
        calls = []

        def fake_generate(engine, prompt, timeout):
            calls.append(prompt)
            return "GROUPED REPLY"
        monkeypatch.setattr(ai_voice, "_generate", fake_generate)

        tts_q = queue.Queue()
        stop_evt = threading.Event()
        t = self._run_worker(tts_q, stop_evt, engine="claude", burst_window=0.3)
        try:
            for i in range(4):
                ai_voice.submit(ai_voice.AiVoiceRequest(
                    prompt_intent=f"body {i}", fallback_text=f"fallback {i}",
                    groupable=True, group_key="sysA",
                ))
            msg = tts_q.get(timeout=2)
            assert msg.text == "GROUPED REPLY"
            assert tts_q.empty()
            assert len(calls) == 1
        finally:
            stop_evt.set()
            t.join(timeout=2)

    def test_burst_groups_are_isolated_by_key(self, monkeypatch):
        monkeypatch.setattr(ai_voice, "_generate", lambda engine, prompt, timeout: "REPLY")

        tts_q = queue.Queue()
        stop_evt = threading.Event()
        t = self._run_worker(tts_q, stop_evt, engine="claude", burst_window=0.3)
        try:
            ai_voice.submit(ai_voice.AiVoiceRequest(prompt_intent="a", groupable=True, group_key="sysA"))
            ai_voice.submit(ai_voice.AiVoiceRequest(prompt_intent="b", groupable=True, group_key="sysB"))
            msg1 = tts_q.get(timeout=2)
            msg2 = tts_q.get(timeout=2)
            assert {msg1.text, msg2.text} == {"REPLY"}
        finally:
            stop_evt.set()
            t.join(timeout=2)
