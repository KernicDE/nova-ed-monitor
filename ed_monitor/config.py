from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT_VOICES: dict[str, str] = {
    "en": "en-GB-SoniaNeural",
    "de": "de-DE-KatjaNeural",
    "fr": "fr-FR-DeniseNeural",
    "it": "it-IT-ElsaNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-PT-RaquelNeural",
    "ru": "ru-RU-SvetlanaNeural",
}

# Default overlay segments — replicate original hardcoded output
_DEFAULT_OVERLAY_SEGMENTS = [
    "NOVA",
    "SHIP: {ship_name} ({ship_type})",
    "POSITION: {system} {position}",
    "JUMPS LEFT: {jumps_left}",      # skipped automatically when jumps_left == 0
]
_DEFAULT_OVERLAY_SEPARATOR = "     ////     "


@dataclass
class Config:
    journal_dir:              Path
    twitch_channel:           str  = ""
    youtube_channel:          str  = ""
    tts_rate:                 str  = "+10%"
    tts_lang:                 str  = "en"
    tts_voices:               dict = field(default_factory=lambda: dict(_DEFAULT_VOICES))
    overlay_segments:         list = field(default_factory=lambda: list(_DEFAULT_OVERLAY_SEGMENTS))
    overlay_separator:        str  = _DEFAULT_OVERLAY_SEPARATOR
    overlay_uppercase:        bool = True
    overlay_path:             str  = "stream_info.txt"
    notable_value_threshold:  int  = 500_000


DEFAULT_CONFIG = """\
# NOVA — Navigation, Operations, and Vessel Assistance
# All settings are optional. The journal directory is auto-detected.
# Remove the leading '#' from a line to activate that setting.

# Journal directory (leave commented to auto-detect):
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous

# Twitch integration — leave commented to disable:
# twitch_channel = yourchannel

# YouTube live chat — leave commented to disable:
# youtube_channel = @yourchannel

# TTS voice rate adjustment (e.g. +10%, -5%, +0%):
# tts_rate = +10%

# Language for NOVA's own voiceovers (en, de, fr, it, es, pt, ru):
# tts_lang = en
# Voiceline files: ~/.config/nova/voicelines/{lang}.toml
# Copy from ed_monitor/voicelines/{lang}.toml to customise individual event lines.

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural

# ── Stream Overlay ────────────────────────────────────────────────────────────
# Each overlay_line_N defines one segment. Segments are joined by the separator.
# Lines containing a variable that evaluates to empty/zero are skipped.
#
# Available variables:
#   {commander}    — Commander name
#   {ship_name}    — Ship name
#   {ship_type}    — Ship type (e.g. "Krait Phantom")
#   {system}       — Current star system
#   {position}     — Station, approach body, or "Deep Space"
#   {jumps_left}   — Remaining jumps in route (skipped when 0)
#   {route_next}   — Next jump destination (skipped when empty)
#   {hull_pct}     — Hull integrity percentage (e.g. "98%")
#   {fuel_t}       — Current fuel in tonnes (e.g. "28.4t")
#   {fuel_max_t}   — Max fuel capacity (e.g. "32t")
#
# overlay_line_1 = NOVA
# overlay_line_2 = {ship_name} ({ship_type})
# overlay_line_3 = {system} — {position}
# overlay_line_4 = JUMPS: {jumps_left}
# overlay_separator =      ////
# overlay_uppercase = true
# overlay_path = stream_info.txt

# ── Notable Bodies ────────────────────────────────────────────────────────────
# Minimum body value (Cr) to appear in the Notable Bodies list in the Overview.
# Bodies with bio signals, ELW/Water/Ammonia types, and terraform candidates
# are always included regardless of this threshold.
# notable_value_threshold = 500000
"""


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"


def load() -> Config:
    config_dir  = _config_dir()
    config_path = config_dir / "config.toml"

    # Migrate from old ed-monitor config dir if new one doesn't exist
    if not config_path.exists():
        old_path = _old_config_path()
        if old_path and old_path.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(old_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")

    journal_dir       = None
    twitch_channel    = ""
    youtube_channel   = ""
    tts_rate          = "+10%"
    tts_lang          = "en"
    tts_voices        = dict(_DEFAULT_VOICES)
    overlay_lines: dict[int, str] = {}
    overlay_separator        = _DEFAULT_OVERLAY_SEPARATOR
    overlay_uppercase        = True
    overlay_path             = "stream_info.txt"
    notable_value_threshold  = 500_000
    active_keys: set[str] = set()

    try:
        text = config_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                active_keys.add(k)
                match k:
                    case "journal_dir":
                        p = Path(v)
                        if p.is_dir():
                            journal_dir = p
                    case "twitch_channel":
                        channel = v.lstrip("#").strip()
                        if channel:
                            twitch_channel = channel
                    case "youtube_channel":
                        channel = v.lstrip("@").strip()
                        if channel:
                            youtube_channel = channel
                    case "tts_rate":
                        tts_rate = v
                    case "tts_lang":
                        _valid = {"en", "de", "fr", "it", "es", "pt", "ru"}
                        if v in _valid:
                            tts_lang = v
                    case "overlay_separator":
                        overlay_separator = v
                    case "overlay_uppercase":
                        overlay_uppercase = v.lower() not in ("false", "0", "no")
                    case "overlay_path":
                        overlay_path = v
                    case "notable_value_threshold":
                        try:
                            notable_value_threshold = int(v)
                        except ValueError:
                            pass
                    case _ if k.startswith("tts_voice_"):
                        lang = k[len("tts_voice_"):]
                        if lang and v:
                            tts_voices[lang] = v
                    case _ if k.startswith("overlay_line_"):
                        try:
                            idx = int(k[len("overlay_line_"):])
                            overlay_lines[idx] = v
                        except ValueError:
                            pass
        # Rewrite the file if it is missing the full template (outdated format).
        # Preserve any active settings by prepending them before the template.
        if "# overlay_line_1" not in text:
            active_lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#") and "=" in line
            ]
            if active_lines:
                prefix = "# Active settings (preserved from previous config):\n"
                prefix += "\n".join(active_lines) + "\n\n"
            else:
                prefix = ""
            config_path.write_text(prefix + DEFAULT_CONFIG, encoding="utf-8")
        else:
            # Append new sections if missing from an existing config file
            _NEW_SECTIONS = [
                ("# notable_value_threshold", "\n# ── Notable Bodies ───────────────────────────────────────────────────────────\n# Minimum body value (Cr) to appear in the Notable Bodies list in the Overview.\n# Bodies with bio signals, ELW/Water/Ammonia types, and terraform candidates\n# are always included regardless of this threshold.\n# notable_value_threshold = 500000\n"),
                ("# tts_lang", "\n# ── Language ─────────────────────────────────────────────────────────────────\n# Language for NOVA's own voiceovers (en, de, fr, it, es, pt, ru):\n# tts_lang = en\n# Voiceline files: ~/.config/nova/voicelines/{lang}.toml (copy from defaults to customise)\n"),
            ]
            appended = False
            for marker, section in _NEW_SECTIONS:
                # Strip "# " to get the bare key name so we match both
                # the commented form ("# auto_honk") and active form ("auto_honk = true")
                key = marker.lstrip("#").strip().split()[0]
                if key not in text:
                    text += section
                    appended = True
            if appended:
                try:
                    config_path.write_text(text, encoding="utf-8")
                except OSError:
                    pass
    except OSError:
        pass

    if journal_dir is None:
        journal_dir = discover_journal() or Path(".")

    # Build overlay segments from numbered lines if any were specified
    if overlay_lines:
        overlay_segments = [overlay_lines[i] for i in sorted(overlay_lines)]
    else:
        overlay_segments = list(_DEFAULT_OVERLAY_SEGMENTS)

    return Config(
        journal_dir=journal_dir,
        twitch_channel=twitch_channel,
        youtube_channel=youtube_channel,
        tts_rate=tts_rate,
        tts_lang=tts_lang,
        tts_voices=tts_voices,
        overlay_segments=overlay_segments,
        overlay_separator=overlay_separator,
        overlay_uppercase=overlay_uppercase,
        overlay_path=overlay_path,
        notable_value_threshold=notable_value_threshold,
    )


def _old_config_path() -> Path | None:
    """Return path to old ed-monitor config file, if it exists."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        p = Path(xdg) / "ed-monitor" / "config.toml"
    else:
        p = Path.home() / ".config" / "ed-monitor" / "config.toml"
    return p if p.exists() else None


def discover_journal() -> Path | None:
    home    = Path.home()
    ed_path = Path("Saved Games/Frontier Developments/Elite Dangerous")
    proton  = Path("pfx/drive_c/users/steamuser") / ed_path

    candidates = [
        # Linux: Proton — default Steam install
        home / ".local/share/Steam/steamapps/compatdata/359320" / proton,
        # Linux: Proton — alternate Steam symlink
        home / ".steam/steam/steamapps/compatdata/359320" / proton,
        # Linux: Proton — Flatpak Steam
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/359320" / proton,
        # Windows native (common path)
        Path.home() / ed_path,
        # macOS
        home / "Library/Application Support/Frontier Developments/Elite Dangerous",
    ]

    for p in candidates:
        if p.is_dir():
            return p
    return None
