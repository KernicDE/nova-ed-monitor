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


def spawn_worker(
    voice:    str,
    rate:     str,
    volume:   list[int],
    vol_lock: threading.Lock,
) -> queue.Queue:
    _cleanup_stale_tmp()
    q: queue.Queue[TtsMsg] = queue.Queue()
    t = threading.Thread(
        target=_worker,
        args=(q, voice, rate, volume, vol_lock),
        daemon=True,
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
) -> None:
    pending: list[TtsMsg] = []

    while True:
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
            continue

        msg = pending.pop(0)
        with vol_lock:
            vol = volume[0]
        
        # Priority on msg.volume override
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
    """Play MP3. Platform-aware fallback chain."""
    import sys
    import time

    # ── Windows ────────────────────────────────────────────────────────────────
    # pygame from pip bundles SDL2+SDL_mixer on Windows — always works.
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
        # Windows fallback: PowerShell Windows.Media.MediaPlayer
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
    # mpg123 factor: 32768 = 100 %, so volume * 327 ≈ correct scale
    factor = str(int(volume * 327))

    # 1. mpg123 via PulseAudio — reliable on PipeWire + pipewire-pulse (Linux)
    try:
        subprocess.run(
            ["mpg123", "-o", "pulse", "--quiet", "-f", factor, path],
            timeout=60,
        )
        return
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, subprocess.CalledProcessError):
        pass

    # 2. mpg123 via default output (ALSA or whatever is configured)
    try:
        subprocess.run(
            ["mpg123", "--quiet", "-f", factor, path],
            timeout=60,
        )
        return
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 3. ffplay (FFmpeg) — widely available, uses SDL2 audio
    try:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
             "-volume", str(volume), path],
            timeout=60,
        )
        return
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 4. afplay (macOS)
    try:
        subprocess.run(["afplay", path], timeout=60)
        return
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 5. System python3 pygame — avoids the venv's potentially broken pygame
    try:
        script = (
            "import pygame, sys, time\n"
            "pygame.mixer.init()\n"
            "pygame.mixer.music.load(sys.argv[1])\n"
            f"pygame.mixer.music.set_volume({volume / 100.0:.3f})\n"
            "pygame.mixer.music.play()\n"
            "while pygame.mixer.music.get_busy(): time.sleep(0.05)\n"
        )
        subprocess.run(["python3", "-c", script, path], timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
