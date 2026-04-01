from __future__ import annotations

import glob
import hashlib
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_TMPDIR = tempfile.gettempdir()

# Set up audio debugging logger (file-only to prevent terminal flickering)
_audio_logger = logging.getLogger("nova.audio")
_audio_logger.setLevel(logging.DEBUG)

# Create file handler which logs debug messages to a file
audio_log_file = Path(tempfile.gettempdir()) / "nova-audio-debug.log"
file_handler = logging.FileHandler(audio_log_file, mode='w')
file_handler.setLevel(logging.DEBUG)

# Create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the handler to the logger
_audio_logger.addHandler(file_handler)

# Console logging is disabled to prevent terminal flickering


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
_BIOREADY_COOLDOWN = 30.0  # seconds - specific cooldown for BioReady messages

# Store recent messages for deduplication
_recent_messages: dict[str, float] = {}
_recent_messages_lock = threading.Lock()

# Specific cooldown for BioReady messages
_last_bioready_time = 0.0
_bioready_cooldown_lock = threading.Lock()


def _check_bioready_cooldown() -> bool:
    """Check if BioReady messages are allowed based on cooldown period."""
    global _last_bioready_time
    current_time = time.time()
    with _bioready_cooldown_lock:
        if current_time - _last_bioready_time < _BIOREADY_COOLDOWN:
            _audio_logger.info(f"BioReady message suppressed by cooldown ({current_time - _last_bioready_time:.1f}s since last)")
            return False
        _last_bioready_time = current_time
        return True


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
            # Clean up old deduplication keys periodically
            current_time = time.time()
            if current_time % 30 < 0.1:  # Clean up roughly every 30 seconds
                with _recent_messages_lock:
                    old_keys = [key for key, timestamp in _recent_messages.items() 
                              if (current_time - timestamp) > (_DUPLICATE_WINDOW * 2)]
                    for key in old_keys:
                        del _recent_messages[key]
            
            try:
                msg = q.get(timeout=0.5)
                
                # Special BioReady cooldown check
                if msg.deduplication_key and msg.deduplication_key.startswith("BioReady-"):
                    if not _check_bioready_cooldown():
                        continue  # Skip this message due to cooldown
                
                # General deduplication logic
                if msg.deduplication_key:
                    with _recent_messages_lock:
                        last_time = _recent_messages.get(msg.deduplication_key)
                        if last_time and (current_time - last_time) < _DUPLICATE_WINDOW:
                            _audio_logger.debug(f"Dropping duplicate message (key: {msg.deduplication_key})")
                            continue  # Skip this duplicate message
                        _recent_messages[msg.deduplication_key] = current_time
                
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

    _audio_logger.debug(f"TTS play requested: text='{text[:100]}...', voice={voice}, rate={rate}, volume={volume}, cacheable={cacheable}")

    if cacheable and cached_path.exists():
        # Touch to update LRU timestamp, then play directly
        try:
            cached_path.touch()
            _audio_logger.debug(f"Using cached audio file: {cached_path}")
        except OSError as e:
            _audio_logger.warning(f"Failed to touch cached file {cached_path}: {e}")
            pass
        _audio_logger.info(f"Playing cached audio: {cached_path}")
        _play_audio(str(cached_path), volume)
        _audio_logger.info(f"Playback completed for: {cached_path}")
        return

    tmp = os.path.join(_TMPDIR, f"nova-tts-{os.getpid()}.mp3")
    _audio_logger.debug(f"Generating new TTS to temp file: {tmp}")
    
    try:
        _audio_logger.debug(f"Running edge-tts command: edge-tts --voice {voice} --rate {rate} --text '{text[:50]}...' --write-media {tmp}")
        result = subprocess.run(
            ["edge-tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", tmp],
            capture_output=True,
            timeout=30,
        )
        
        _audio_logger.debug(f"edge-tts completed with return code: {result.returncode}")
        if result.stdout:
            _audio_logger.debug(f"edge-tts stdout: {result.stdout[:200]}")
        if result.stderr:
            _audio_logger.debug(f"edge-tts stderr: {result.stderr[:200]}")
        
        if result.returncode == 0 and os.path.exists(tmp):
            file_size = os.path.getsize(tmp)
            _audio_logger.debug(f"TTS generation successful, file size: {file_size} bytes")
            
            if cacheable:
                try:
                    shutil.copy2(tmp, str(cached_path))
                    _evict_cache(cd)
                    _audio_logger.debug(f"Cached audio file to: {cached_path}")
                except OSError as e:
                    _audio_logger.warning(f"Failed to cache audio file: {e}")
                    pass
            
            _audio_logger.info(f"Playing generated audio: {tmp}")
            _play_audio(tmp, volume)
            _audio_logger.info(f"Generated audio playback completed: {tmp}")
        else:
            _audio_logger.error(f"TTS generation failed or temp file missing. Return code: {result.returncode}, file exists: {os.path.exists(tmp)}")
            
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _audio_logger.error(f"TTS generation exception: {e}")
        pass
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
                _audio_logger.debug(f"Cleaned up temp file: {tmp}")
        except OSError as e:
            _audio_logger.warning(f"Failed to clean up temp file {tmp}: {e}")
            pass


def _play_audio(path: str, volume: int) -> None:
    """Play MP3. Platform-aware fallback chain with backend caching."""
    global _audio_backend
    import sys
    import subprocess
    import time

    _audio_logger.info(f"Playing audio file: {path}, volume: {volume}%, platform: {sys.platform}")

    # ── Windows ────────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        _audio_logger.debug("Using Windows audio playback methods")
        
        # Try pygame first (most reliable cross-platform approach)
        try:
            import pygame
            _audio_logger.debug("Attempting direct pygame playback")
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume / 100.0)
            pygame.mixer.music.play()
            _audio_logger.info("Pygame playback started successfully")
            # Wait for playback to complete
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            _audio_logger.info("Pygame playback completed")
            return
        except Exception as e:
            _audio_logger.warning(f"Direct pygame playback failed: {e}")
            pass
        
        # Fallback 1: Use pygame with explicit Python subprocess
        try:
            import subprocess
            _audio_logger.debug("Attempting pygame via Python subprocess")
            py_script = (
                f"import pygame, time; "
                f"pygame.mixer.init(); "
                f"pygame.mixer.music.load('{path}'); "
                f"pygame.mixer.music.set_volume({volume / 100.0}); "
                f"pygame.mixer.music.play(); "
                f"while pygame.mixer.music.get_busy(): time.sleep(0.05)"
            )
            result = subprocess.run([sys.executable, "-c", py_script], timeout=60, 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                _audio_logger.info("Pygame subprocess playback completed")
                return
            else:
                _audio_logger.warning(f"Pygame subprocess failed with code {result.returncode}")
        except Exception as e:
            _audio_logger.warning(f"Pygame subprocess exception: {e}")
            pass
        
        # Fallback 2: Use Windows Media Player via subprocess
        try:
            _audio_logger.debug("Attempting Windows Media Player")
            result = subprocess.run(["wmplayer", path], timeout=60, capture_output=True)
            if result.returncode == 0:
                _audio_logger.info("Windows Media Player playback completed")
                return
            else:
                _audio_logger.warning(f"Windows Media Player failed with code {result.returncode}")
        except Exception as e:
            _audio_logger.warning(f"Windows Media Player exception: {e}")
            pass
        
        # Fallback 3: Use PowerShell with better error handling
        try:
            _audio_logger.debug("Attempting PowerShell MediaPlayer")
            ps_script = (
                f'$mp = New-Object System.Windows.Media.MediaPlayer; '
                f'$mp.Open("{path}"); '
                f'$mp.Volume = {volume / 100.0}; '
                f'$mp.Play(); '
                f'while ($mp.HasAudio) {{ Start-Sleep -Milliseconds 50 }}'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                timeout=60, capture_output=True, text=True
            )
            if result.returncode == 0:
                _audio_logger.info("PowerShell MediaPlayer playback completed")
            else:
                _audio_logger.warning(f"PowerShell MediaPlayer failed with code {result.returncode}")
        except Exception as e:
            _audio_logger.warning(f"PowerShell MediaPlayer exception: {e}")
            pass
        
        _audio_logger.error("All Windows audio playback methods failed")
        return

    # ── Linux / macOS ──────────────────────────────────────────────────────────
    _audio_logger.debug("Using Linux/macOS audio playback methods")
    factor = str(int(volume * 327))  # mpg123: 32768 = 100%

    def _try_mpg123_pulse() -> bool:
        try:
            _audio_logger.debug("Trying mpg123 with pulse audio")
            r = subprocess.run(
                ["mpg123", "-o", "pulse", "--quiet", "-f", factor, path],
                timeout=60,
            )
            if r.returncode == 0:
                _audio_logger.info("mpg123 pulse audio playback successful")
            else:
                _audio_logger.warning(f"mpg123 pulse audio failed with code {r.returncode}")
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            _audio_logger.debug(f"mpg123 pulse audio exception: {e}")
            return False

    def _try_mpg123() -> bool:
        try:
            _audio_logger.debug("Trying mpg123 without pulse")
            r = subprocess.run(
                ["mpg123", "--quiet", "-f", factor, path],
                timeout=60,
            )
            if r.returncode == 0:
                _audio_logger.info("mpg123 playback successful")
            else:
                _audio_logger.warning(f"mpg123 failed with code {r.returncode}")
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            _audio_logger.debug(f"mpg123 exception: {e}")
            return False

    def _try_ffplay() -> bool:
        try:
            _audio_logger.debug("Trying ffplay")
            r = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                 "-volume", str(volume), path],
                timeout=60,
            )
            if r.returncode == 0:
                _audio_logger.info("ffplay playback successful")
            else:
                _audio_logger.warning(f"ffplay failed with code {r.returncode}")
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            _audio_logger.debug(f"ffplay exception: {e}")
            return False

    def _try_afplay() -> bool:
        try:
            _audio_logger.debug("Trying afplay (macOS)")
            r = subprocess.run(["afplay", "-v", f"{volume / 100.0:.3f}", path], timeout=60)
            if r.returncode == 0:
                _audio_logger.info("afplay playback successful")
            else:
                _audio_logger.warning(f"afplay failed with code {r.returncode}")
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            _audio_logger.debug(f"afplay exception: {e}")
            return False

    def _try_pygame_sys() -> bool:
        try:
            _audio_logger.debug("Trying pygame system fallback")
            script = (
                "import pygame, sys, time\n"
                "pygame.mixer.init()\n"
                "pygame.mixer.music.load(sys.argv[1])\n"
                f"pygame.mixer.music.set_volume({volume / 100.0:.3f})\n"
                "pygame.mixer.music.play()\n"
                "while pygame.mixer.music.get_busy(): time.sleep(0.05)\n"
            )
            r = subprocess.run(["python3", "-c", script, path], timeout=60)
            if r.returncode == 0:
                _audio_logger.info("pygame system fallback successful")
            else:
                _audio_logger.warning(f"pygame system fallback failed with code {r.returncode}")
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            _audio_logger.debug(f"pygame system fallback exception: {e}")
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
        _audio_logger.debug(f"Trying cached backend: {cached}")
        fn = next((f for n, f in _backends if n == cached), None)
        if fn is not None and fn():
            return
        # Cached backend failed — reset and fall through to full chain
        _audio_logger.warning(f"Cached backend {cached} failed, trying all backends")
        with _audio_backend_lock:
            _audio_backend = None

    # Full discovery chain
    _audio_logger.debug("Trying all audio backends in order")
    for name, fn in _backends:
        _audio_logger.debug(f"Trying backend: {name}")
        if fn():
            _audio_logger.info(f"Successfully used backend: {name}")
            with _audio_backend_lock:
                _audio_backend = name

    _audio_logger.error("All Linux/macOS audio playback methods failed")
