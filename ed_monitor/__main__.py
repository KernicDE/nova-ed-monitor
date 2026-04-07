from __future__ import annotations

import queue
import threading
from pathlib import Path
from datetime import datetime

from . import bindings, config, db, debug_log, edsm, edsm_dumps, events, journal, neutron, overlay, screenshots, spansh, status, tts, twitch, voicelines, youtube
from .state import MAX_EVENTS, AppState, EventCategory, LogEvent
from .tts import TtsMsg
from .ui.app import NOVAApp

def _db_path() -> Path:
    p = Path.home() / ".local" / "share" / "nova" / "events.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main() -> None:
    cfg = config.load()
    debug_log.setup(cfg.debug_log, config.config_dir())

    # Apply voice and language config to events / voicelines modules
    events.set_voices(cfg.tts_voices)
    events.set_tts_lang(cfg.tts_lang)
    voicelines.ensure_user_files()   # copy built-ins to config dir if missing
    voicelines._load(cfg.tts_lang)   # pre-warm cache

    database = db.Database(_db_path())
    state    = AppState()
    lock     = threading.RLock()

    with lock:
        state.events.extendleft(database.get_recent_events(MAX_EVENTS))

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

    # Journal monitor thread
    threading.Thread(
        target=journal.monitor,
        args=(state, lock, tts_q, database, cfg.journal_dir, edsm_q, spansh_q),
        daemon=True,
    ).start()

    # Status.json monitor thread
    threading.Thread(
        target=status.monitor,
        args=(state, lock, cfg.journal_dir, tts_q),
        daemon=True,
    ).start()

    # Twitch chat thread (no-op if twitch_channel not set in config)
    threading.Thread(
        target=twitch.monitor,
        args=(state, lock, tts_q, cfg),
        daemon=True,
    ).start()

    # YouTube live chat thread (no-op if youtube_channel not set in config)
    threading.Thread(
        target=youtube.monitor,
        args=(state, lock, tts_q, cfg),
        daemon=True,
    ).start()

    # Stream overlay thread
    threading.Thread(
        target=overlay.monitor,
        args=(state, lock, cfg),
        daemon=True,
    ).start()

    # Keybindings monitor thread
    threading.Thread(
        target=bindings.monitor,
        args=(state, lock, cfg.journal_dir, config.config_dir()),
        daemon=True,
    ).start()

    # Screenshot processing thread
    threading.Thread(
        target=screenshots.monitor,
        args=(state, lock, cfg),
        daemon=True,
    ).start()

    NOVAApp(state, lock, volume, vol_lock, tts_q, stop_evt, neutron_q).run()


if __name__ == "__main__":
    main()
