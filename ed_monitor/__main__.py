from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from pathlib import Path
from datetime import datetime

_wlog = logging.getLogger("nova.watchdog")


def _spawn_guarded(target, args: tuple, name: str) -> threading.Thread:
    """Start a daemon thread that restarts itself after a 5-second delay on crash."""
    def wrapper():
        while True:
            try:
                target(*args)
            except Exception:
                _wlog.error("Thread '%s' crashed:\n%s", name, traceback.format_exc())
                time.sleep(5)
    t = threading.Thread(target=wrapper, name=name, daemon=True)
    t.start()
    return t

from . import bindings, config, db, debug_log, edsm, edsm_dumps, events, journal, neutron, overlay, screenshots, spansh, status, tts, twitch, voicelines, youtube
from .state import MAX_EVENTS, AppState, EventCategory, LogEvent
from .tts import TtsMsg
from .ui.app import NOVAApp

def _db_path() -> Path:
    p = Path.home() / ".local" / "share" / "nova" / "events.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _detect_initial_commander(journal_dir: Path) -> str:
    """Scan the most recent journal file for the last logged-in commander name."""
    import json as _json
    try:
        candidates = sorted(
            [p for p in journal_dir.iterdir()
             if p.name.startswith("Journal.") and p.name.endswith(".log")],
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            return ""
        with open(candidates[-1], "rb") as f:
            raw = f.read()
        cmdr = ""
        for line in raw.decode("utf-8", errors="replace").splitlines():
            try:
                ev = _json.loads(line.strip())
                if ev.get("event") == "LoadGame":
                    cmdr = ev.get("Commander", "") or ""
            except Exception:
                pass
        return cmdr
    except Exception:
        return ""


def main() -> None:
    cfg = config.load()
    debug_log.setup(cfg.debug_log, config.config_dir())

    # Apply voice and language config to events / voicelines modules
    events.set_voices(cfg.tts_voices)
    events.set_tts_lang(cfg.tts_lang)
    events.set_chat_lang(cfg.chat_lang)
    voicelines.ensure_user_files()   # copy built-ins to config dir if missing
    voicelines._load(cfg.tts_lang)   # pre-warm cache

    initial_commander = _detect_initial_commander(cfg.journal_dir)

    database = db.Database(_db_path())
    state    = AppState()
    lock     = threading.RLock()

    with lock:
        state.events.extendleft(database.get_recent_events(MAX_EVENTS, initial_commander))

    volume    = [cfg.default_volume]
    vol_lock  = threading.Lock()
    stop_evt  = threading.Event()

    # Use configured English voice + rate for the primary TTS worker
    primary_voice = cfg.tts_voices.get("en", "en-GB-SoniaNeural")
    tts_q = tts.spawn_worker(primary_voice, cfg.tts_rate, volume, vol_lock, stop_evt)

    edsm_q    = edsm.spawn(state, lock)
    edsm_dumps.spawn(state, lock, database)
    spansh_q  = spansh.spawn(state, lock) if cfg.carrier_lookup else None
    neutron_q = neutron.spawn(state, lock)

    with lock:
        state.volume                    = cfg.default_volume
        state.notable_value_threshold   = cfg.notable_value_threshold
        state.situational_panels        = list(cfg.situational_panels)
        state.session_start             = datetime.now().strftime("%H:%M")
        state.edsm_status.enabled = True
        state.client_online = False  # Start offline until we see LoadGame/Location event
        # Reset session statistics
        state.session_jumps = 0
        state.session_first_disc = 0
        state.session_mapped = 0
        state.session_value = 0
        state.jump_dist_total = 0.0
        state.push_event(LogEvent.new(EventCategory.System, "NOVA active."))

    try:
        # Only play startup message if not already played (prevents duplicates)
        if not getattr(state, '_startup_message_played', False):
            state._startup_message_played = True
            startup_text = voicelines.pick("Nova_Startup", lang=cfg.tts_lang) or "NOVA active."
            voice = None  # use worker default
            if cfg.tts_lang != "en":
                from . import events as _ev_mod
                voice = _ev_mod._LANG_VOICES.get(cfg.tts_lang)
            tts_q.put_nowait(TtsMsg(
                text=startup_text, 
                priority=False, 
                volume=20, 
                voice=voice,
                deduplication_key="Nova_Startup"
            ))
    except Exception:
        pass

    # Journal monitor thread (guarded: restarts on crash after 5s)
    _spawn_guarded(journal.monitor,
                   (state, lock, tts_q, database, cfg.journal_dir, edsm_q, spansh_q),
                   "nova-journal")

    # Status.json monitor thread (guarded: restarts on crash after 5s)
    _spawn_guarded(status.monitor,
                   (state, lock, cfg.journal_dir, tts_q),
                   "nova-status")

    # Twitch chat thread (no-op if twitch_channel not set in config)
    _spawn_guarded(twitch.monitor, (state, lock, tts_q, cfg), "nova-twitch")

    # YouTube live chat thread (no-op if youtube_channel not set in config)
    _spawn_guarded(youtube.monitor, (state, lock, tts_q, cfg), "nova-youtube")

    # Stream overlay thread
    _spawn_guarded(overlay.monitor, (state, lock, cfg), "nova-overlay")

    # Keybindings monitor thread
    _spawn_guarded(bindings.monitor,
                   (state, lock, cfg.journal_dir, config.config_dir()),
                   "nova-bindings")

    # Screenshot processing thread
    _spawn_guarded(screenshots.monitor, (state, lock, cfg), "nova-screenshots")

    NOVAApp(state, lock, volume, vol_lock, tts_q, stop_evt, neutron_q).run()


if __name__ == "__main__":
    main()
