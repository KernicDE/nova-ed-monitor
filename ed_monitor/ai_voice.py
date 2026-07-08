"""
NOVA AI Voice — AI-generated voice lines via external CLI (kimi -p / claude -p).

Additive, opt-in path. When ``voice_engine == "static"`` (the default) this
module is never invoked — events.py keeps using the existing template-based
voicelines system unchanged.

When enabled, events.py submits an AiVoiceRequest instead of speaking the
static text directly. A dedicated daemon thread (`worker`, registered via
`_spawn_guarded` in __main__.py) drains the request queue, builds a prompt
from the configured personality + situation context, and shells out to the
chosen CLI with a timeout. On any failure (missing binary, timeout, non-zero
exit, empty output) the request's `fallback_text` — the same text the static
voiceline system would have spoken — is used instead, so NOVA never falls
silent because of a flaky AI backend.

Rapid-fire "groupable" events (e.g. FSS scanning many bodies in a row) are
debounced: `submit()` buffers them per group_key and (re)starts a short timer;
once the burst settles, all buffered intents are merged into a single request
so only one AI call is made per burst instead of one per event.
"""
from __future__ import annotations

import logging
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger("nova.ai_voice")

# ── Module state (mirrors events.py's _TTS_LANG-style live-configurable globals) ──
_ENGINE:           str   = "static"   # static | kimi | claude
_TIMEOUT_S:        float = 12.0
_BURST_WINDOW_S:   float = 2.5
_PERSONALITY_NAME: str   = "default"

_MAX_OUTPUT_CHARS = 400


def configure(cfg) -> None:
    """Apply voice_engine/timeout/burst-window/personality settings from Config.

    Called at startup and whenever settings are hot-reloaded (config.toml
    edit or Settings overlay save) — mirrors events.set_tts_lang()/set_voices().
    """
    global _ENGINE, _TIMEOUT_S, _BURST_WINDOW_S, _PERSONALITY_NAME
    _ENGINE           = getattr(cfg, "voice_engine", "static")
    _TIMEOUT_S        = getattr(cfg, "ai_voice_timeout_s", 12.0)
    _BURST_WINDOW_S   = getattr(cfg, "ai_voice_burst_window_s", 2.5)
    _PERSONALITY_NAME = getattr(cfg, "personality_name", "default")


def get_engine() -> str:
    return _ENGINE


@dataclass
class AiVoiceRequest:
    prompt_intent: str
    context:       dict = field(default_factory=dict)
    fallback_text: str  = ""
    priority:      bool = False
    cacheable:     bool = False   # AI output is non-deterministic — don't mp3-cache by default
    groupable:     bool = False
    group_key:     str  = ""      # only used when groupable=True


_ai_q: "queue.Queue[AiVoiceRequest]" = queue.Queue()

# ── Burst grouping (debounce) ────────────────────────────────────────────────
_burst_lock = threading.Lock()
_burst_buffers: dict[str, dict] = {}   # group_key -> {"items": [...], "priority": bool, "cacheable": bool}
_burst_timers:  dict[str, threading.Timer] = {}


def submit(request: AiVoiceRequest) -> None:
    """Enqueue a voice request. Groupable requests are debounced per group_key."""
    if not request.groupable:
        try:
            _ai_q.put_nowait(request)
        except queue.Full:
            _log.debug("AI voice queue full — dropped request: %s", request.prompt_intent[:60])
        return

    key = request.group_key or request.prompt_intent
    with _burst_lock:
        buf = _burst_buffers.setdefault(key, {"items": [], "priority": False, "cacheable": False})
        buf["items"].append(request)
        buf["priority"] = buf["priority"] or request.priority

        old_timer = _burst_timers.get(key)
        if old_timer is not None:
            old_timer.cancel()
        timer = threading.Timer(_BURST_WINDOW_S, _flush_burst, args=(key,))
        timer.daemon = True
        _burst_timers[key] = timer
        timer.start()


def _flush_burst(key: str) -> None:
    with _burst_lock:
        buf = _burst_buffers.pop(key, None)
        _burst_timers.pop(key, None)
    if not buf or not buf["items"]:
        return

    items: list[AiVoiceRequest] = buf["items"]
    merged_context: dict = {}
    for item in items:
        merged_context.update(item.context)

    intents = [item.prompt_intent for item in items]
    merged = AiVoiceRequest(
        prompt_intent="Summarize these noteworthy discoveries in one short remark: "
                      + "; ".join(intents),
        context=merged_context,
        fallback_text=" ".join(item.fallback_text for item in items if item.fallback_text),
        priority=buf["priority"],
        cacheable=False,
        groupable=False,
    )
    try:
        _ai_q.put_nowait(merged)
    except queue.Full:
        _log.debug("AI voice queue full — dropped grouped burst for key %r", key)


# ── Prompt construction ──────────────────────────────────────────────────────

_LANGUAGE_NAMES = {
    "en": "English", "de": "German", "fr": "French", "it": "Italian",
    "es": "Spanish", "pt": "Portuguese", "ru": "Russian",
}


def _build_prompt(request: AiVoiceRequest) -> str:
    from . import personality as _personality
    from . import events as _ev

    lang_code = _ev.get_tts_lang()
    lang_name = _LANGUAGE_NAMES.get(lang_code, "English")

    parts = [_personality.get_prompt_fragment(_PERSONALITY_NAME)]
    parts.append(f"\nSituation: {request.prompt_intent}")
    if request.context:
        details = ", ".join(f"{k}={v}" for k, v in request.context.items() if v not in (None, ""))
        if details:
            parts.append(f"Details: {details}")
    if request.fallback_text:
        parts.append(f"Reference line for context (do not repeat verbatim): {request.fallback_text}")
    parts.append(
        f"\nRespond ONLY in {lang_name} ({lang_code}) — every word, no exceptions, "
        "even if the situation details above are in English. "
        "Respond with a single short spoken line only — no formatting, no quotes, "
        "no explanations. Just the line NOVA would say out loud."
    )
    return "\n".join(p for p in parts if p)


_STRIP_MARKDOWN_RE = re.compile(r"[*_`#]")


def _sanitize_output(text: str) -> str:
    text = text.strip()
    text = _STRIP_MARKDOWN_RE.sub("", text)
    text = " ".join(text.splitlines())
    text = text.strip().strip('"').strip()
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def _generate(engine: str, prompt: str, timeout: float) -> Optional[str]:
    """Run the AI CLI and return generated text, or None on any failure."""
    try:
        result = subprocess.run(
            [engine, "-p", prompt],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        _log.warning("AI voice generation failed (%s): %s", engine, e)
        return None

    if result.returncode != 0:
        _log.warning("AI voice CLI '%s' exited rc=%d: %s", engine, result.returncode, (result.stderr or "")[:200])
        return None

    text = _sanitize_output(result.stdout or "")
    if not text:
        _log.warning("AI voice CLI '%s' returned empty output", engine)
        return None
    return text


def _push_to_tts(tts_q, text: str, priority: bool, cacheable: bool) -> None:
    """Speak *text* via the existing TTS pipeline (voice/phonetic-sub reuse)."""
    from . import events as _ev
    _ev._speak(tts_q, text, priority, cacheable=cacheable)


def worker(cfg, tts_q, stop_evt) -> None:
    """Daemon thread entry point (registered via _spawn_guarded as 'nova-ai-voice').

    Drains the AI voice request queue, generates text via the configured CLI,
    and falls back to the static fallback text on any failure.
    """
    configure(cfg)
    while not stop_evt.is_set():
        try:
            request = _ai_q.get(timeout=0.5)
        except queue.Empty:
            continue

        engine = _ENGINE
        if engine == "static":
            # Shouldn't normally happen (events.py only submits when engine
            # != static), but handle gracefully if a stale request arrives
            # right after the user switches back to static.
            if request.fallback_text:
                _push_to_tts(tts_q, request.fallback_text, request.priority, request.cacheable)
            continue

        prompt = _build_prompt(request)
        text = _generate(engine, prompt, _TIMEOUT_S)
        if text:
            _push_to_tts(tts_q, text, request.priority, request.cacheable)
        elif request.fallback_text:
            _push_to_tts(tts_q, request.fallback_text, request.priority, request.cacheable)
