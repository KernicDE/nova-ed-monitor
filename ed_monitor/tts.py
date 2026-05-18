from __future__ import annotations

import glob
import hashlib
import logging
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_TMPDIR = tempfile.gettempdir()
_tmp_seq = 0
_tmp_seq_lock = threading.Lock()

# Audio logger. Off by default (NullHandler). Routed into the main debug log
# via debug_log.setup() when the user enables debug_log in config. This avoids
# opening a truncated /tmp/nova-audio-debug.log on every NOVA launch.
_audio_logger = logging.getLogger("nova.audio")
_audio_logger.setLevel(logging.DEBUG)
_audio_logger.addHandler(logging.NullHandler())
_audio_logger.propagate = False


@dataclass
class TtsMsg:
    text:      str
    priority:  bool = False
    voice:     Optional[str] = None
    volume:    Optional[int] = None
    cacheable: bool = True
    timestamp: float = field(default_factory=lambda: time.time())
    deduplication_key: Optional[str] = None


# Cached playback backend: set after first successful play, reset on failure.
# Values: "mpg123_pulse" | "mpg123" | "ffplay" | "afplay" | "pygame_sys" | None
_audio_backend: Optional[str] = None
_audio_backend_lock = threading.Lock()

_CACHE_MAX_BYTES = 500 * 1024 * 1024  # 500 MB
_DUPLICATE_WINDOW = 10.0  # seconds - prevent duplicate messages within this window

# Store recent messages for deduplication
_recent_messages: dict[str, float] = {}
_recent_messages_lock = threading.Lock()


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


def clear_cache() -> None:
    """Delete all cached mp3s and the voice signature file."""
    cd = _cache_dir()
    for p in cd.glob("*.mp3"):
        try:
            p.unlink()
        except OSError:
            pass
    sig_file = cd.parent / "voice.sig"
    try:
        sig_file.unlink()
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
    if "multilingual" in voice.lower():
        logging.getLogger("nova.tts").warning(
            "Voice %s is a multilingual voice. Multilingual voices are not "
            "supported because they can mix languages unexpectedly. Please "
            "select a monolingual voice in Settings.",
            voice,
        )
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


def _dedup_cleanup(current_time: float) -> None:
    """Drop dedup keys older than 2× the duplicate window. Called unconditionally
    every ~30 s from the worker loop regardless of queue pressure — previously
    only ran when the queue drained to empty, so a constantly-busy TTS loop
    could let the dict grow without bound."""
    with _recent_messages_lock:
        stale = [
            k for k, ts in _recent_messages.items()
            if (current_time - ts) > (_DUPLICATE_WINDOW * 2)
        ]
        for k in stale:
            del _recent_messages[k]


def _worker(
    q:        queue.Queue[TtsMsg],
    voice:    str,
    rate:     str,
    volume:   list[int],
    vol_lock: threading.Lock,
    stop_evt: threading.Event,
) -> None:
    pending: list[TtsMsg] = []
    _last_dedup_cleanup: float = time.time()
    _DEDUP_CLEANUP_INTERVAL = 30.0

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

        # Time-based dedup cleanup — runs whether or not the queue is busy
        # so a long chat burst never accumulates stale keys.
        current_time = time.time()
        if current_time - _last_dedup_cleanup > _DEDUP_CLEANUP_INTERVAL:
            _last_dedup_cleanup = current_time
            _dedup_cleanup(current_time)

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

        # Dedup check — single point covering both drain and blocking paths
        if msg.deduplication_key:
            now = time.time()
            with _recent_messages_lock:
                last_time = _recent_messages.get(msg.deduplication_key)
                if last_time and (now - last_time) < _DUPLICATE_WINDOW:
                    continue
                _recent_messages[msg.deduplication_key] = now

        _play(msg.text, msg.voice or voice, rate, vol, msg.cacheable)


def _play(text: str, voice: str, rate: str, volume: int, cacheable: bool = True) -> None:
    cd = _cache_dir()
    key = _cache_key(text, voice, rate)
    cached_path = cd / f"{key}.mp3"

    if cacheable and cached_path.exists():
        try:
            cached_path.touch()
        except OSError:
            pass
        _play_audio(str(cached_path), volume)
        return

    global _tmp_seq
    with _tmp_seq_lock:
        _tmp_seq += 1
        seq = _tmp_seq
    tmp = os.path.join(_TMPDIR, f"nova-tts-{os.getpid()}-{seq}.mp3")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", tmp],
            capture_output=True,
            timeout=30,
        )
        # Some edge-tts versions return rc=1 on non-fatal warnings but still write the file.
        # Treat the result as successful whenever the output file was actually written.
        file_ok = os.path.exists(tmp) and os.path.getsize(tmp) > 0
        if file_ok:
            if result.returncode != 0:
                _audio_logger.debug(
                    f"edge-tts rc={result.returncode} but output written — non-fatal warning"
                )
            if cacheable:
                try:
                    shutil.copy2(tmp, str(cached_path))
                    _evict_cache(cd)
                except OSError as e:
                    _audio_logger.warning(f"Failed to cache audio: {e}")
            _play_audio(tmp, volume)
        else:
            _audio_logger.error(f"edge-tts failed (rc={result.returncode}): {result.stderr[:200]}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _audio_logger.error(f"TTS generation error: {e}")
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def _play_audio(path: str, volume: int) -> None:
    """Play MP3. Platform-aware fallback chain with backend caching."""
    global _audio_backend
    import sys
    import subprocess
    import time

    # ── Windows ────────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        # Try pygame first (most reliable)
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume / 100.0)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            pygame.mixer.music.unload()  # release file handle (required on Windows)
            return
        except Exception as e:
            _audio_logger.warning(f"pygame playback failed: {e}")

        # Fallback 1: pygame via subprocess
        try:
            py_script = (
                f"import pygame, time; "
                f"pygame.mixer.init(); "
                f"pygame.mixer.music.load({repr(str(path))}); "
                f"pygame.mixer.music.set_volume({volume / 100.0}); "
                f"pygame.mixer.music.play(); "
                f"while pygame.mixer.music.get_busy(): time.sleep(0.05)"
            )
            result = subprocess.run([sys.executable, "-c", py_script], timeout=60,
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return
            _audio_logger.warning(f"pygame subprocess failed (rc={result.returncode})")
        except Exception as e:
            _audio_logger.warning(f"pygame subprocess error: {e}")

        # Fallback 2: Windows Media Player
        try:
            result = subprocess.run(["wmplayer", path], timeout=60, capture_output=True)
            if result.returncode == 0:
                return
            _audio_logger.warning(f"wmplayer failed (rc={result.returncode})")
        except Exception as e:
            _audio_logger.warning(f"wmplayer error: {e}")

        # Fallback 3: PowerShell MediaPlayer
        # Wait for HasAudio (confirms load), play, then sleep for actual duration.
        # Note: HasAudio stays True during playback — do NOT use it as loop condition.
        try:
            ps_path = str(path).replace('"', '`"')  # escape double-quotes for PowerShell
            ps_script = (
                f'$mp = New-Object System.Windows.Media.MediaPlayer; '
                f'$mp.Open("{ps_path}"); '
                f'$mp.Volume = {volume / 100.0}; '
                f'while (-not $mp.HasAudio) {{ Start-Sleep -Milliseconds 50 }}; '
                f'$mp.Play(); '
                f'$dur = [int]$mp.NaturalDuration.TimeSpan.TotalMilliseconds; '
                f'if ($dur -gt 0) {{ Start-Sleep -Milliseconds $dur }} else {{ Start-Sleep -Seconds 5 }}'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                timeout=60, capture_output=True, text=True
            )
            if result.returncode == 0:
                return
            _audio_logger.warning(f"PowerShell MediaPlayer failed (rc={result.returncode})")
        except Exception as e:
            _audio_logger.warning(f"PowerShell MediaPlayer error: {e}")

        _audio_logger.error("All Windows audio playback methods failed")
        return

    # ── Linux / macOS ──────────────────────────────────────────────────────────
    factor = str(int(volume * 327))  # mpg123: 32768 = 100%

    def _try_mpg123_pulse() -> bool:
        try:
            r = subprocess.run(
                ["mpg123", "-o", "pulse", "--quiet", "-f", factor, path],
                timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_mpg123() -> bool:
        try:
            r = subprocess.run(
                ["mpg123", "--quiet", "-f", factor, path],
                timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _try_afplay() -> bool:
        try:
            r = subprocess.run(
                ["afplay", "-v", f"{volume / 100.0:.3f}", path],
                timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
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
            r = subprocess.run(
                ["python3", "-c", script, path],
                timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
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
        _audio_logger.warning(f"Cached audio backend '{cached}' failed, rediscovering")
        with _audio_backend_lock:
            _audio_backend = None

    # Full discovery chain — stop at first success
    for name, fn in _backends:
        if fn():
            _audio_logger.info(f"Audio backend: {name}")
            with _audio_backend_lock:
                _audio_backend = name
            return

    _audio_logger.error("All Linux/macOS audio playback methods failed")
