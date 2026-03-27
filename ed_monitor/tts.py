from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TtsMsg:
    text:     str
    priority: bool = False
    voice:    Optional[str] = None
    volume:   Optional[int] = None


# Cached playback backend: set after first successful play, reset on failure.
# Values: "mpg123_pulse" | "mpg123" | "ffplay" | "afplay" | "pygame_sys" | None
_audio_backend: Optional[str] = None
_audio_backend_lock = threading.Lock()


def spawn_worker(
    voice:     str,
    rate:      str,
    volume:    list[int],
    vol_lock:  threading.Lock,
    stop_evt:  Optional[threading.Event] = None,
) -> queue.Queue:
    _cleanup_stale_tmp()
    q: queue.Queue[TtsMsg] = queue.Queue()
    t = threading.Thread(
        target=_worker,
        args=(q, voice, rate, volume, vol_lock, stop_evt or threading.Event()),
        daemon=True,
        name="nova-tts",
    )
    t.start()
    return q


def _cleanup_stale_tmp() -> None:
    """Delete any leftover ed-tts-*.mp3 files from previous runs."""
    import glob
    for path in glob.glob("/tmp/nova-tts-*.mp3"):
        try:
            os.unlink(path)
        except OSError:
            pass


def _worker(
    q:        queue.Queue[TtsMsg],
    voice:    str,
    rate:     str,
    volume:   list[int],
    vol_lock: threading.Lock,
    stop_evt: threading.Event,
) -> None:
    pending: list[TtsMsg] = []

    while not stop_evt.is_set():
        # Drain all pending messages
        while True:
            try:
                msg = q.get_nowait()
                if msg.priority:
                    pending.insert(0, msg)
                else:
                    pending.append(msg)
            except queue.Empty:
                break

        if not pending:
            try:
                msg = q.get(timeout=0.5)
                if msg.priority:
                    pending.insert(0, msg)
                else:
                    pending.append(msg)
            except queue.Empty:
                continue
            if stop_evt.is_set():
                break
            continue

        msg = pending.pop(0)
        with vol_lock:
            vol = volume[0]

        # msg.volume overrides global volume (e.g. startup message at lower level)
        if msg.volume is not None:
            vol = msg.volume

        _play(msg.text, msg.voice or voice, rate, vol)


def _play(text: str, voice: str, rate: str, volume: int) -> None:
    tmp = f"/tmp/nova-tts-{os.getpid()}.mp3"
    try:
        result = subprocess.run(
            ["edge-tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", tmp],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(tmp):
            _play_audio(tmp, volume)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _play_audio(path: str, volume: int) -> None:
    """Play MP3. Platform-aware fallback chain with backend caching."""
    global _audio_backend
    import sys
    import time

    # ── Windows ────────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume / 100.0)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            return
        except Exception:
            pass
        try:
            ps = (
                f"$mp = [System.Windows.Media.MediaPlayer]::new(); "
                f"$mp.Open([uri]'{path}'); $mp.Play(); Start-Sleep -Seconds 60"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                timeout=90,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return

    # ── Linux / macOS ──────────────────────────────────────────────────────────
    factor = str(int(volume * 327))  # mpg123: 32768 = 100%

    def _try_mpg123_pulse() -> bool:
        try:
            r = subprocess.run(
                ["mpg123", "-o", "pulse", "--quiet", "-f", factor, path],
                timeout=60,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_mpg123() -> bool:
        try:
            r = subprocess.run(
                ["mpg123", "--quiet", "-f", factor, path],
                timeout=60,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_ffplay() -> bool:
        try:
            r = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                 "-volume", str(volume), path],
                timeout=60,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_afplay() -> bool:
        try:
            r = subprocess.run(["afplay", "-v", f"{volume / 100.0:.3f}", path], timeout=60)
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_pygame_sys() -> bool:
        try:
            script = (
                "import pygame, sys, time\n"
                "pygame.mixer.init()\n"
                "pygame.mixer.music.load(sys.argv[1])\n"
                f"pygame.mixer.music.set_volume({volume / 100.0:.3f})\n"
                "pygame.mixer.music.play()\n"
                "while pygame.mixer.music.get_busy(): time.sleep(0.05)\n"
            )
            r = subprocess.run(["python3", "-c", script, path], timeout=60)
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    _backends = [
        ("mpg123_pulse", _try_mpg123_pulse),
        ("mpg123",       _try_mpg123),
        ("ffplay",       _try_ffplay),
        ("afplay",       _try_afplay),
        ("pygame_sys",   _try_pygame_sys),
    ]

    # Try cached backend first
    with _audio_backend_lock:
        cached = _audio_backend

    if cached is not None:
        fn = next((f for n, f in _backends if n == cached), None)
        if fn is not None and fn():
            return
        # Cached backend failed — reset and fall through to full chain
        with _audio_backend_lock:
            _audio_backend = None

    # Full discovery chain
    for name, fn in _backends:
        if fn():
            with _audio_backend_lock:
                _audio_backend = name
            return
