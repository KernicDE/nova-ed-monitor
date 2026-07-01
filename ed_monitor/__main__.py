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


def _patch_kitty_keyboard_protocol() -> None:
    # Fish 4.x pushes KKP flags=31 (DISAMBIGUATE | REPORT_EVENT_TYPES |
    # REPORT_ALTERNATE_KEYS | REPORT_ALL_KEYS | REPORT_ASSOCIATED_TEXT).
    # Textual then pushes flags=25 (DISAMBIGUATE | REPORT_ALL_KEYS |
    # REPORT_ASSOCIATED_TEXT) on top, making flags=25 active while NOVA runs.
    #
    # Two-layer fix:
    #
    # 1. Normalise incoming sequences in _sequence_to_key_events: strip `:\d+`
    #    sub-params left by REPORT_EVENT_TYPES (e.g. `\x1b[1;129:1C` →
    #    `\x1b[1;129C`).  This handles any residual flags=31 sequences during
    #    the brief window before Textual's own push takes effect.
    #
    # 2. Downgrade Textual's own KKP push to flags=1 (DISAMBIGUATE only) by
    #    zeroing KITTY_REPORT_ALL_KEYS and KITTY_REPORT_ASSOCIATED_TEXT in
    #    linux_driver before start_application_mode() computes KITTY_PROTOCOL_FLAG.
    #    With flags=1: cursor keys arrive as `\x1b[C` / `\x1b[1;NC` (classic
    #    xterm format), no Num Lock modifier complications, no 3-field character
    #    sequences — the simplest format that Textual handles perfectly.
    #
    # The stack-clear in main() (just before NOVAApp.run()) also pops any
    # leftover fish push via __stderr__ so the terminal starts clean.
    try:
        import re as _re
        import textual._xterm_parser as _xterm_parser
        from textual._ansi_sequences import ANSI_SEQUENCES_KEYS, IGNORE_SEQUENCE

        _strip_subparam = _re.compile(r":\d+")

        def _normalize(seq: str) -> str:
            return _strip_subparam.sub("", seq)   # drop :N event-type sub-params

        _orig_stke = _xterm_parser.XTermParser._sequence_to_key_events

        def _patched_stke(self, sequence: str, alt: bool = False,
                          _orig=_orig_stke, _norm=_normalize):
            return _orig(self, _norm(sequence), alt)

        _xterm_parser.XTermParser._sequence_to_key_events = _patched_stke

        for _seq in ("\x1b[p", "\x1b[>0p", "\x1b[>p"):
            ANSI_SEQUENCES_KEYS.setdefault(_seq, IGNORE_SEQUENCE)

    except Exception:
        pass

    # Downgrade Textual's KKP push from flags=25 to flags=1 (DISAMBIGUATE only).
    # REPORT_ALL_KEYS (bit 3) adds Num Lock into cursor-key modifier bytes;
    # REPORT_ASSOCIATED_TEXT (bit 4) produces 3-field character sequences.
    # Both interact poorly with fish's flags=31 stack and produce sequences that
    # cause \x1b[I (FOCUSIN) misparses in certain Kitty+fish combinations.
    # With flags=1, all keys arrive in the classic xterm format Textual knows.
    try:
        import textual.drivers.linux_driver as _ld
        _ld.KITTY_REPORT_ALL_KEYS = 0
        _ld.KITTY_REPORT_ASSOCIATED_TEXT = 0
    except Exception:
        pass


_patch_kitty_keyboard_protocol()

_wlog = logging.getLogger("nova.watchdog")


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

from . import ai_voice, ambient, bindings, config, config_watcher, db, debug_log, edsm, edsm_dumps, events, journal, neutron, overlay, personality, screenshots, spansh, status, tts, twitch, voicelines, youtube
from .state import MAX_EVENTS, AppState, EventCategory, LogEvent
from .tts import TtsMsg
from .ui import palette as _palette
_palette.ensure_theme_files()
_palette.apply_theme(config.load().theme)
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
    events.set_voice_engine(cfg.voice_engine)
    voicelines.ensure_user_files()   # copy built-ins to config dir if missing
    voicelines._load(cfg.tts_lang)   # pre-warm cache
    ai_voice.configure(cfg)
    personality.ensure_user_files()  # copy built-in personality to config dir if missing

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

    # cfg_holder: shared mutable cell so background threads (ambient) always
    # see the latest Config after a hot-reload/Settings-save, without a restart.
    cfg_holder = [cfg]

    # AI voice generation thread (no-op passthrough if voice_engine == static)
    _spawn_guarded(ai_voice.worker, (cfg, tts_q, stop_evt), "nova-ai-voice")

    # Ambient commentary thread (no-op if ambient_commentary_enabled is False
    # or voice_engine == static — checked inside the loop)
    _spawn_guarded(ambient.monitor,
                   (state, lock, tts_q, lambda: cfg_holder[0], stop_evt),
                   "nova-ambient")

    restart_evt = threading.Event()

    def _on_config_changed():
        try:
            new_cfg = config.load()
            old_lang = events.get_tts_lang()
            if new_cfg.tts_lang != old_lang:
                tts.clear_cache()
                voicelines.reload_all()
                restart_evt.set()
            # Theme changes require a restart (CSS is evaluated at class load time)
            if getattr(cfg, "theme", "default") != new_cfg.theme:
                restart_evt.set()
            events.set_tts_lang(new_cfg.tts_lang)
            events.set_voices(new_cfg.tts_voices)
            events.set_voice_engine(new_cfg.voice_engine)
            ai_voice.configure(new_cfg)
            cfg_holder[0] = new_cfg
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

    def _on_personality_changed():
        try:
            personality.reload_all()
        except Exception as exc:
            logging.getLogger("nova").warning("Personality hot-reload failed: %s", exc)

    config_watcher.spawn(
        config.config_dir(),
        _on_config_changed,
        _on_voicelines_changed,
        _on_personality_changed,
    )

    # Pop any KKP stack entries fish may have left active (fish pushes flags=31
    # when reading interactive input and may not pop before exec).  Sent to
    # __stderr__ — the same fd Textual uses — so Kitty processes the pops
    # before start_application_mode() pushes its own flags.
    sys.__stderr__.write("\x1b[<u" * 8)
    sys.__stderr__.flush()

    NOVAApp(state, lock, volume, vol_lock, tts_q, stop_evt, neutron_q, cfg, restart_evt, cfg_holder).run(mouse=False)

    if restart_evt.is_set():
        logging.getLogger("nova").info("Restarting NOVA after settings change")
        if sys.argv[0].endswith("__main__.py"):
            os.execv(sys.executable, [sys.executable, "-m", "ed_monitor"])
        else:
            # Entry-point launch: exec the script directly so the OS shebang runs it.
            # os.execv(sys.executable, sys.argv) would pass argv[0] as the process
            # name with no script argument, landing Python in interactive mode.
            os.execv(sys.argv[0], sys.argv)


if __name__ == "__main__":
    main()
