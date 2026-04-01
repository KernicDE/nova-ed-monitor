from __future__ import annotations

import glob
import hashlib
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_TMPDIR = tempfile.gettempdir()


@dataclass
class TtsMsg:
    text:      str
    priority:  bool = False
    voice:     Optional[str] = None
    volume:    Optional[int] = None
    cacheable: bool = True


# Cached playback backend: set after first successful play, reset on failure.
# Values: "mpg123_pulse" | "mpg123" | "ffplay" | "afplay" | "pygame_sys" | None
_audio_backend: Optional[str] = None
_audio_backend_lock = threading.Lock()

_CACHE_MAX_BYTES = 500 * 1024 * 1024  # 500 MB


def _cache_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) / "nova" if xdg else Path.home() / ".config" / "nova"
    p = base / "cache" / "tts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(text: str, voice: str, rate: str) -> str:
    return hashlib.sha256(f"{voice}|{rate}|{text}".encode()).hexdigest()[:24]


def _evict_cache(cache_dir: Path) -> None:
    """Delete least-recently-used mp3s until total size is under _CACHE_MAX_BYTES."""
    files = []
    for p in cache_dir.glob("*.mp3"):
        try:
            st = p.stat()
            files.append((p, st.st_size, st.st_mtime))
        except OSError:
            pass
    total = sum(sz for _, sz, _ in files)
    if total <= _CACHE_MAX_BYTES:
        return
    files.sort(key=lambda x: x[2])  # oldest mtime first
    for path, sz, _ in files:
        if total <= _CACHE_MAX_BYTES:
            break
        try:
            path.unlink()
            total -= sz
        except OSError:
            pass


def _reset_cache_if_voice_changed(voice: str, rate: str) -> None:
    """Clear all cached mp3s when voice or rate has changed since last run."""
    cd = _cache_dir()
    sig_file = cd.parent / "voice.sig"
    sig = f"{voice}|{rate}"
    try:
        old_sig = sig_file.read_text(encoding="utf-8")
    except OSError:
        old_sig = ""
    if old_sig == sig:
        return
    for p in cd.glob("*.mp3"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        sig_file.write_text(sig, encoding="utf-8")
    except OSError:
        pass


def spawn_worker(
    voice:     str,
    rate:      str,
    volume:    list[int],
    vol_lock:  threading.Lock,
    stop_evt:  Optional[threading.Event] = None,
) -> queue.Queue:
    _cleanup_stale_tmp()
    _reset_cache_if_voice_changed(voice, rate)
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
    """Delete any leftover nova-tts-*.mp3 files from previous runs."""
    pattern = os.path.join(_TMPDIR, "nova-tts-*.mp3")
    for path in glob.glob(pattern):
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

        _play(msg.text, msg.voice or voice, rate, vol, msg.cacheable)


def _play(text: str, voice: str, rate: str, volume: int, cacheable: bool = True) -> None:
    cd = _cache_dir()
    key = _cache_key(text, voice, rate)
    cached_path = cd / f"{key}.mp3"

    if cacheable and cached_path.exists():
        # Touch to update LRU timestamp, then play directly
        try:
            cached_path.touch()
        except OSError:
            pass
        _play_audio(str(cached_path), volume)
        return

    tmp = os.path.join(_TMPDIR, f"nova-tts-{os.getpid()}.mp3")
    try:
        result = subprocess.run(
            ["edge-tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", tmp],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(tmp):
            if cacheable:
                try:
                    shutil.copy2(tmp, str(cached_path))
                    _evict_cache(cd)
                except OSError:
                    pass
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
