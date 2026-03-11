from __future__ import annotations

import queue
import threading
from pathlib import Path
from datetime import datetime

from . import config, db, edsm, events, journal, overlay, status, tts, twitch
from .state import MAX_EVENTS, AppState, EventCategory, LogEvent
from .tts import TtsMsg
from .ui.app import NOVAApp

DEFAULT_VOLUME = 50


def _db_path() -> Path:
    p = Path.home() / ".local" / "share" / "nova" / "events.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main() -> None:
    cfg = config.load()

    # Apply voice config to events module
    events.set_voices(cfg.tts_voices)

    database = db.Database(_db_path())
    state    = AppState()
    lock     = threading.RLock()

    with lock:
        state.events.extendleft(database.get_recent_events(MAX_EVENTS))

    volume   = [DEFAULT_VOLUME]
    vol_lock = threading.Lock()

    # Use configured English voice + rate for the primary TTS worker
    primary_voice = cfg.tts_voices.get("en", "en-GB-SoniaNeural")
    tts_q = tts.spawn_worker(primary_voice, cfg.tts_rate, volume, vol_lock)

    edsm_q = edsm.spawn(state, lock)

    with lock:
        state.volume        = DEFAULT_VOLUME
        state.session_start = datetime.now().strftime("%H:%M")
        state.edsm_status.enabled = True
        state.push_event(LogEvent.new(EventCategory.System, "NOVA (Navigation, Operations, and Vessel Assistance) active."))

    try:
        tts_q.put_nowait(TtsMsg(text="NOVA active.", priority=False, volume=20))
    except Exception:
        pass

    # Journal monitor thread
    threading.Thread(
        target=journal.monitor,
        args=(state, lock, tts_q, database, cfg.journal_dir, edsm_q),
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

    # Stream overlay thread
    threading.Thread(
        target=overlay.monitor,
        args=(state, lock),
        daemon=True,
    ).start()

    NOVAApp(state, lock, volume, vol_lock, tts_q).run()


if __name__ == "__main__":
    main()
