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


def _default_overlay_dir() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return str(Path(xdg) / "nova" / "overlay")
    return str(Path.home() / ".config" / "nova" / "overlay")


@dataclass
class Config:
    journal_dir:              Path
    twitch_channel:           str  = ""
    youtube_channel:          str  = ""
    tts_rate:                 str  = "+10%"
    tts_lang:                 str  = "en"
    tts_voices:               dict = field(default_factory=lambda: dict(_DEFAULT_VOICES))
    overlay_dir:              str  = field(default_factory=_default_overlay_dir)
    notable_value_threshold:  int  = 500_000
    default_volume:           int  = 50
    carrier_lookup:           bool = False
    debug_log:                bool = False
    screenshot_dir:           str  = ""    # ED screenshot source dir (auto-detected if empty)
    screenshot_dest:          str  = ""    # destination dir (default: ~/Pictures/Elite Dangerous)
    chat_lang:                str  = ""    # fallback language for chat TTS (empty = auto-detect)
    situational_panels:       list = field(default_factory=list)  # [] = default order/all visible


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

# Fallback language for chat TTS (in-game, Twitch, YouTube).
# Auto-detection is used first; this applies when detection returns English.
# Set to your squad's language if messages are often short or ambiguous (e.g. de).
# chat_lang = de

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural

# ── Stream Overlay ────────────────────────────────────────────────────────────
# Individual .txt files are written to the overlay directory for use in OBS/Streamlabs.
# Each file contains one piece of information (e.g. system.txt, ship_name.txt).
# Files: commander, ship_name, ship_type, ship_ident, system, position, station,
#        approach_body, route_destination, route_next, jumps_left, hull, fuel,
#        fuel_max, fuel_reservoir, cargo, heat, shields, status, supercruise,
#        docked, landed, power, power_state, allegiance, economy, security,
#        government, population, nearest_inhabited, heading, altitude, coordinates
# overlay_dir = ~/.config/nova/overlay

# ── Audio ─────────────────────────────────────────────────────────────────────
# Default TTS/audio volume at startup (0–100):
# default_volume = 50

# ── Notable Bodies ────────────────────────────────────────────────────────────
# Minimum body value (Cr) to appear in the Notable Bodies list in the Overview.
# Bodies with bio signals, ELW/Water/Ammonia types, and terraform candidates
# are always included regardless of this threshold.
# notable_value_threshold = 500000

# ── Fleet Carriers ─────────────────────────────────────────────────────────────
# Enable Spansh API lookup for fleet carriers in current system (max 1 req/5 min):
# carrier_lookup = false

# ── Debug Logging ─────────────────────────────────────────────────────────────
# Write a full debug log to ~/.config/nova/nova-debug.log (overwritten each run).
# Enable when you need to diagnose a problem and send the log to the developer.
# debug_log = false

# ── Situational Panels ────────────────────────────────────────────────────────
# Define visibility and order of SITUATION panel tabs (space-separated).
# Panels not listed here will not appear in NOVA and auto mode won't switch to them.
# Available: OVR BIO MAP MIS ENG BGS COL ROU NTR WLT INV DKG STS
# situational_panels = OVR BIO MAP MIS ENG BGS COL ROU NTR WLT INV DKG STS
"""


def config_dir() -> Path:
    """Return the NOVA config directory (~/.config/nova or $XDG_CONFIG_HOME/nova)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nova"
    return Path.home() / ".config" / "nova"


def load() -> Config:
    cfg_dir     = config_dir()
    config_path = cfg_dir / "config.toml"

    # Migrate from old ed-monitor config dir if new one doesn't exist
    if not config_path.exists():
        old_path = _old_config_path()
        if old_path and old_path.exists():
            cfg_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(old_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            cfg_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")

    journal_dir       = None
    twitch_channel    = ""
    youtube_channel   = ""
    tts_rate                 = "+10%"
    tts_lang                 = "en"
    tts_voices               = dict(_DEFAULT_VOICES)
    overlay_dir              = _default_overlay_dir()
    notable_value_threshold  = 500_000
    default_volume           = 50
    carrier_lookup           = False
    debug_log                = False
    screenshot_dir           = ""
    screenshot_dest          = ""
    chat_lang                = ""
    situational_panels: list = []
    active_keys: set[str] = set()

    _KNOWN_KEYS = {
        "journal_dir", "twitch_channel", "youtube_channel",
        "tts_rate", "tts_lang", "overlay_dir",
        "default_volume", "notable_value_threshold", "carrier_lookup",
        "debug_log", "screenshot_dir", "screenshot_dest", "chat_lang",
        "situational_panels",
    }

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
                    case "overlay_dir":
                        overlay_dir = v
                    case "default_volume":
                        try:
                            default_volume = max(0, min(100, int(v)))
                        except ValueError:
                            pass
                    case "notable_value_threshold":
                        try:
                            notable_value_threshold = int(v)
                        except ValueError:
                            pass
                    case "carrier_lookup":
                        carrier_lookup = v.lower() in ("true", "1", "yes")
                    case "debug_log":
                        debug_log = v.lower() in ("true", "1", "yes")
                    case "screenshot_dir":
                        screenshot_dir = v
                    case "screenshot_dest":
                        screenshot_dest = v
                    case "chat_lang":
                        _valid = {"en", "de", "fr", "it", "es", "pt", "ru"}
                        if v in _valid:
                            chat_lang = v
                    case "situational_panels":
                        _abbrev_to_mode = {
                            "OVR": "overview", "BIO": "bio", "MAP": "galaxy",
                            "MIS": "missions", "ENG": "engineers", "BGS": "bgs",
                            "COL": "colonisation", "ROU": "route", "NTR": "neutron",
                            "WLT": "wealth", "INV": "inventory", "DKG": "docking", "STS": "stats",
                        }
                        _panels = [_abbrev_to_mode[a.upper()] for a in v.split() if a.upper() in _abbrev_to_mode]
                        if _panels:
                            situational_panels = _panels
                    case _ if k.startswith("tts_voice_"):
                        lang = k[len("tts_voice_"):]
                        if lang and v:
                            tts_voices[lang] = v
                    # Silently accept old overlay_* keys so existing configs don't error
        # Rewrite the file if it is missing the new overlay section (outdated format).
        if "# overlay_dir" not in text:
            active_lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#") and "=" in line
                # Drop unknown/stale keys; keep known keys and tts_voice_* prefix
                and (line.strip().split("=")[0].strip() in _KNOWN_KEYS
                     or line.strip().split("=")[0].strip().startswith("tts_voice_"))
                # Drop old overlay_line_N / overlay_separator / overlay_path / overlay_uppercase
                and not line.strip().startswith("overlay_line_")
                and not line.strip().startswith("overlay_separator")
                and not line.strip().startswith("overlay_path")
                and not line.strip().startswith("overlay_uppercase")
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
                ("# default_volume", "\n# ── Audio ────────────────────────────────────────────────────────────────────\n# Default TTS/audio volume at startup (0–100):\n# default_volume = 50\n"),
                ("# carrier_lookup", "\n# ── Fleet Carriers ─────────────────────────────────────────────────────────────\n# Enable Spansh API lookup for fleet carriers in current system (max 1 req/5 min):\n# carrier_lookup = false\n"),
                ("# debug_log", "\n# ── Debug Logging ─────────────────────────────────────────────────────────────\n# Write a full debug log to ~/.config/nova/nova-debug.log (overwritten each run).\n# Enable when you need to diagnose a problem and send the log to the developer.\n# debug_log = false\n"),
                ("# chat_lang", "\n# Fallback language for chat TTS (in-game, Twitch, YouTube).\n# Auto-detection is used first; this applies when detection returns English.\n# Set to your squad's language if messages are often short or ambiguous (e.g. de).\n# chat_lang = de\n"),
            ]
            appended = False
            for marker, section in _NEW_SECTIONS:
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

    return Config(
        journal_dir=journal_dir,
        twitch_channel=twitch_channel,
        youtube_channel=youtube_channel,
        tts_rate=tts_rate,
        tts_lang=tts_lang,
        tts_voices=tts_voices,
        overlay_dir=overlay_dir,
        notable_value_threshold=notable_value_threshold,
        default_volume=default_volume,
        carrier_lookup=carrier_lookup,
        debug_log=debug_log,
        screenshot_dir=screenshot_dir,
        screenshot_dest=screenshot_dest,
        chat_lang=chat_lang,
        situational_panels=situational_panels,
    )


def _old_config_path() -> Path | None:
    """Return path to old ed-monitor config file, if it exists."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        p = Path(xdg) / "ed-monitor" / "config.toml"
    else:
        p = Path.home() / ".config" / "ed-monitor" / "config.toml"
    return p if p.exists() else None


def _heroic_journal() -> "Path | None":
    """Try to find the ED journal dir from Heroic Games Launcher config."""
    import json as _json

    ed_path   = Path("Saved Games/Frontier Developments/Elite Dangerous")
    wine_user = Path("drive_c/users/steamuser") / ed_path
    ptn_user  = Path("pfx/drive_c/users/steamuser") / ed_path

    # Heroic config dirs: native install and Flatpak
    heroic_cfg_dirs = [
        Path.home() / ".config/heroic",
        Path.home() / ".var/app/com.heroicgameslauncher.hgl/config/heroic",
    ]

    _ED_KEYWORDS = {"elite dangerous", "elite-dangerous", "elitedangerous"}

    for cfg_dir in heroic_cfg_dirs:
        games_cfg = cfg_dir / "GamesConfig"
        if not games_cfg.is_dir():
            continue
        for json_file in games_cfg.iterdir():
            if json_file.suffix != ".json":
                continue
            try:
                data = _json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
                # GamesConfig files are keyed by app ID; the value is the config dict
                for _app_id, game_cfg in data.items() if isinstance(data, dict) else []:
                    if not isinstance(game_cfg, dict):
                        continue
                    title = str(game_cfg.get("title", "")).lower()
                    if not any(kw in title for kw in _ED_KEYWORDS):
                        continue
                    prefix = game_cfg.get("winePrefix") or game_cfg.get("winePrefixPath")
                    if prefix:
                        base = Path(prefix)
                        for suffix in (wine_user, ptn_user):
                            p = base / suffix
                            if p.is_dir():
                                return p
            except Exception:
                continue

    return None


def discover_journal() -> Path | None:
    home    = Path.home()
    ed_path = Path("Saved Games/Frontier Developments/Elite Dangerous")
    proton  = Path("pfx/drive_c/users/steamuser") / ed_path
    wine    = Path("drive_c/users/steamuser") / ed_path

    candidates = [
        # Linux: Proton — default Steam install
        home / ".local/share/Steam/steamapps/compatdata/359320" / proton,
        # Linux: Proton — alternate Steam symlink
        home / ".steam/steam/steamapps/compatdata/359320" / proton,
        # Linux: Proton — Flatpak Steam
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/359320" / proton,
        # Heroic Games Launcher (native + Flatpak) — game-named prefix, Wine or Proton
        home / "Games/Heroic/Prefixes/Elite Dangerous" / wine,
        home / "Games/Heroic/Prefixes/Elite Dangerous" / proton,
        # Heroic — "default" prefix group (some versions use this layout)
        home / "Games/Heroic/Prefixes/default/Elite Dangerous" / wine,
        home / "Games/Heroic/Prefixes/default/Elite Dangerous" / proton,
        # Windows native (common path)
        home / ed_path,
        # macOS
        home / "Library/Application Support/Frontier Developments/Elite Dangerous",
    ]

    for p in candidates:
        if p.is_dir():
            return p

    # Fall back to parsing Heroic's GamesConfig for custom prefix locations
    return _heroic_journal()
