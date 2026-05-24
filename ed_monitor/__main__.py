from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
from datetime import datetime

# Workaround: Kitty terminal's extended keyboard protocol (CSI u) causes
# garbled characters and broken key handling in Textual 8.0.2.
# Textual's Linux driver unconditionally sends \x1b[>1u to enable the protocol.
# In addition, the user's shell (fish) may have left the protocol enabled.
# We therefore disable it explicitly before startup AND patch the driver so
# Textual cannot re-enable it.
if os.environ.get("TERM") == "xterm-kitty" or "KITTY_WINDOW_ID" in os.environ:
    # Push current flags onto stack and set kitty keyboard flags to 0.
    # This disables the protocol for the lifetime of NOVA. Textual's
    # stop_application_mode() already sends \x1b[<u (pop) on exit, so the
    # previous state (e.g. fish's enabled protocol) is restored cleanly.
    sys.stdout.write("\x1b[>0u")
    sys.stdout.write("\x1b[?1003l")  # disable mouse tracking (belt-and-suspenders)
    sys.stdout.flush()
    os.environ["TERM"] = "xterm-256color"
    os.environ.pop("TERMINFO", None)
    os.environ.pop("TERM_PROGRAM", None)

_wlog = logging.getLogger("nova.watchdog")


def _patch_textual_linux_driver() -> None:
    """Prevent Textual from enabling the Kitty keyboard protocol.

    Textual's LinuxDriver unconditionally sends \x1b[>1u in
    start_application_mode(). This causes Kitty to emit CSI u escape
    sequences that Textual 8.0.2 fails to parse correctly, resulting in
    garbled screen output and non-functional keys.
    We monkey-patch the driver to filter out that single sequence and
    emit an extra disable afterwards in case something else turned it on.
    """
    try:
        from textual.drivers.linux_driver import LinuxDriver
    except Exception:
        return

    _orig_start = LinuxDriver.start_application_mode

    def _patched_start(self):
        _orig_write = self.write
        def _filtered_write(data: str) -> None:
            if data == "\x1b[>1u":
                return
            return _orig_write(data)
        self.write = _filtered_write  # type: ignore[method-assign]
        try:
            _orig_start(self)
        finally:
            self.write = _orig_write  # type: ignore[method-assign]
        # The protocol is already disabled by the \x1b[>0u sent before
        # startup; we only need to prevent Textual from re-enabling it.

    LinuxDriver.start_application_mode = _patched_start  # type: ignore[method-assign]


_patch_textual_linux_driver()


def _spawn_guarded(target, args: tuple, name: str) -> threading.Thread:
    """Start a daemon thread that restarts itself on crash (5 s backoff) or normal return (immediate)."""
    def wrapper():
        while True:
            try:
                target(*args)
                # Normal return (e.g. watchdog event consumed) — restart quickly
                time.sleep(0.1)
            except Exception:
                _wlog.error("Thread '%s' crashed:\n%s", name, traceback.format_exc())
                time.sleep(5)  # Back off on crash to avoid tight crash loops
    t = threading.Thread(target=wrapper, name=name, daemon=True)
    t.start()
    return t

from . import bindings, config, config_watcher, db, debug_log, edsm, edsm_dumps, events, journal, neutron, overlay, screenshots, spansh, status, tts, twitch, voicelines, youtube
from .state import MAX_EVENTS, AppState, EventCategory, LogEvent
from .tts import TtsMsg
from .ui.app import NOVAApp

def _db_path() -> Path:
    p = config.data_dir() / "events.db"
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
                if isinstance(ev, dict) and ev.get("event") == "LoadGame":
                    cmdr = ev.get("Commander", "") or ""
            except _json.JSONDecodeError:
                continue  # malformed journal line — skip
        return cmdr
    except OSError:
        return ""


def main() -> None:
    cfg = config.load()
    debug_log.setup(cfg.debug_log, config.logs_dir())

    # Apply voice and language config to events / voicelines modules
    events.set_voices(cfg.tts_voices)
    events.set_tts_lang(cfg.tts_lang)
    events.set_chat_lang(cfg.chat_lang)
    voicelines.ensure_user_files()   # copy built-ins to config dir if missing
    voicelines._load(cfg.tts_lang)   # pre-warm cache

    # Validate user voiceline file — warn on parse error without crashing
    _vl_error = voicelines.validate_user_file(cfg.tts_lang)

    initial_commander = _detect_initial_commander(cfg.journal_dir)

    database = db.Database(_db_path())
    state    = AppState()
    state.fuel_warning_percent = cfg.fuel_warning_percent
    state.home_system = cfg.home_system
    lock     = threading.RLock()

    # Optional event-log pruning. Off by default (prune_events_days = 0 in
    # the default config) so existing users preserve their full history.
    # Enable it in config.toml to auto-delete events older than N days at
    # each startup — useful on portable installs where disk budget matters.
    if cfg.prune_events_days > 0:
        try:
            deleted = database.prune_events(days=cfg.prune_events_days)
            if deleted:
                logging.getLogger("nova").info(
                    "Pruned %d events older than %d days",
                    deleted, cfg.prune_events_days,
                )
        except Exception as exc:
            logging.getLogger("nova").warning("prune_events failed: %s", exc)

    with lock:
        state.events.extendleft(database.get_recent_events(MAX_EVENTS, initial_commander))

    volume    = [cfg.default_volume]
    vol_lock  = threading.Lock()
    stop_evt  = threading.Event()

    # Use configured English voice + rate for the primary TTS worker
    primary_voice = cfg.tts_voices.get("en", "en-GB-SoniaNeural")
    tts_q = tts.spawn_worker(primary_voice, cfg.tts_rate, volume, vol_lock, stop_evt)

    edsm_q    = edsm.spawn(state, lock, tts_q)
    edsm_dumps.spawn(state, lock, database)
    spansh_q  = spansh.spawn(state, lock) if cfg.carrier_lookup else None
    neutron_q = neutron.spawn(state, lock)

    with lock:
        state.volume                    = cfg.default_volume
        state.notable_value_threshold   = cfg.notable_value_threshold
        state.situational_panels        = list(cfg.situational_panels)
        state.chat_tts_muted            = not cfg.tts_chat
        state.twitch_tts_muted          = not cfg.tts_twitch
        state.youtube_tts_muted         = not cfg.tts_youtube
        state.session_start             = datetime.now().strftime("%H:%M")
        state.session_start_ts          = time.time()
        state.edsm_status.enabled = True
        state.client_online = False  # Start offline until we see LoadGame/Location event
        # Reset session statistics
        state.session_jumps = 0
        state.session_first_disc = 0
        state.session_mapped = 0
        state.session_value = 0
        state.jump_dist_total = 0.0
        state.push_event(LogEvent.new(EventCategory.System, "NOVA active."))

    if _vl_error:
        with lock:
            state.push_event(LogEvent.new(EventCategory.System, f"⚠ {_vl_error}"))

    # Startup voiceline — lost if the TTS queue rejects it, but not worth
    # crashing the app for. Same for the voiceline-file error warning.
    try:
        if not getattr(state, '_startup_message_played', False):
            state._startup_message_played = True
            if not voicelines.is_muted("Nova_Startup", lang=cfg.tts_lang):
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
    except queue.Full:
        logging.getLogger("nova").debug("TTS queue full at startup — skipping Nova_Startup")

    if _vl_error:
        try:
            tts_q.put_nowait(TtsMsg(
                text="Warning: voiceline file has an error and will not be used.",
                priority=True,
                volume=cfg.default_volume,
                voice=None,
                deduplication_key="VoicelineFileError",
            ))
        except queue.Full:
            logging.getLogger("nova").debug("TTS queue full at startup — skipping VoicelineFileError")

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

    restart_evt = threading.Event()

    def _on_config_changed():
        try:
            new_cfg = config.load()
            old_lang = events.get_tts_lang()
            if new_cfg.tts_lang != old_lang:
                tts.clear_cache()
                voicelines.reload_all()
                restart_evt.set()
            events.set_tts_lang(new_cfg.tts_lang)
            events.set_voices(new_cfg.tts_voices)
            with vol_lock:
                volume[0] = new_cfg.default_volume
            with lock:
                state.volume                  = new_cfg.default_volume
                state.notable_value_threshold = new_cfg.notable_value_threshold
        except Exception as exc:
            logging.getLogger("nova").warning("Config hot-reload failed: %s", exc)

    def _on_voicelines_changed():
        try:
            voicelines.reload_all()
        except Exception as exc:
            logging.getLogger("nova").warning("Voiceline hot-reload failed: %s", exc)

    config_watcher.spawn(
        config.config_dir(),
        _on_config_changed,
        _on_voicelines_changed,
    )

    NOVAApp(state, lock, volume, vol_lock, tts_q, stop_evt, neutron_q, cfg, restart_evt).run(mouse=False)

    if restart_evt.is_set():
        logging.getLogger("nova").info("Restarting NOVA after language change")
        if sys.argv[0].endswith("__main__.py"):
            os.execv(sys.executable, [sys.executable, "-m", "ed_monitor"])
        else:
            os.execv(sys.executable, sys.argv)


if __name__ == "__main__":
    main()
