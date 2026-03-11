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


@dataclass
class Config:
    journal_dir:    Path
    twitch_channel: str  = ""
    tts_rate:       str  = "+10%"
    tts_voices:     dict = field(default_factory=lambda: dict(_DEFAULT_VOICES))


DEFAULT_CONFIG = """\
# NOVA — Navigation, Operations, and Vessel Assistance
# All settings are optional. The journal directory is auto-detected.
# Remove the leading '#' from a line to activate that setting.

# Journal directory (leave commented to auto-detect):
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous

# Twitch integration — leave commented to disable:
# twitch_channel = yourchannel

# TTS voice rate adjustment (e.g. +10%, -5%, +0%):
# tts_rate = +10%

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural
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
            config_path.write_text(old_path.read_text())
        else:
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG)

    journal_dir    = None
    twitch_channel = ""
    tts_rate       = "+10%"
    tts_voices     = dict(_DEFAULT_VOICES)

    try:
        text = config_path.read_text()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                match k:
                    case "journal_dir":
                        p = Path(v)
                        if p.is_dir():
                            journal_dir = p
                    case "twitch_channel":
                        channel = v.lstrip("#").strip()
                        if channel:
                            twitch_channel = channel
                    case "tts_rate":
                        tts_rate = v
                    case _ if k.startswith("tts_voice_"):
                        lang = k[len("tts_voice_"):]
                        if lang and v:
                            tts_voices[lang] = v
    except OSError:
        pass

    if journal_dir is None:
        journal_dir = discover_journal() or Path(".")

    return Config(
        journal_dir=journal_dir,
        twitch_channel=twitch_channel,
        tts_rate=tts_rate,
        tts_voices=tts_voices,
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
