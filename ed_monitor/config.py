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
    return str(config_dir() / "overlay")


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
    tts_chat:                 bool = True   # False = disable TTS for all chat sources at startup
    tts_twitch:               bool = True   # False = disable TTS for Twitch chat at startup
    tts_youtube:              bool = True   # False = disable TTS for YouTube chat at startup
    prune_events_days:        int  = 0      # 0 = disabled; >0 = delete events older than N days at startup
    fuel_warning_percent:     int  = 25     # 0 = disabled; fuel warning TTS when main tank drops below this %
    home_system:              str  = ""      # empty = disabled; triggers special voiceline on arrival


def _notify_self_write() -> None:
    """Tell the config watcher to ignore the file-system event that our
    own write just produced. Imports config_watcher lazily to avoid a
    circular import at module-load time (config_watcher imports nothing
    from config)."""
    try:
        from . import config_watcher
        config_watcher.notify_self_write()
    except Exception:
        # config_watcher may not yet be importable in some test setups —
        # if the notification can't land, the worst case is one spurious
        # reload which is not fatal.
        pass


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
# Voiceline files: config/voicelines/{lang}.toml (relative to install dir)
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
# overlay_dir = config/overlay

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
# Write a full debug log to logs/nova-debug.log (overwritten each run).
# Enable when you need to diagnose a problem and send the log to the developer.
# debug_log = false

# ── Situational Panels ────────────────────────────────────────────────────────
# Define visibility and order of SITUATION panel tabs (space-separated).
# Panels not listed here will not appear in NOVA and auto mode won't switch to them.
# Available: OVR BIO MAP MIS ENG BGS COL ROU NTR AST STS
# situational_panels = OVR BIO MAP MIS ENG BGS COL ROU NTR AST STS

# ── Chat TTS ─────────────────────────────────────────────────────────────────
# Disable TTS for chat messages at startup (messages are still shown in the UI).
# Can be toggled at runtime: g = all chat, t = Twitch only, y = YouTube only, p = all.
# tts_chat    = true
# tts_twitch  = true
# tts_youtube = true
"""


def _portable_root() -> Path:
    root = os.environ.get("NOVA_PORTABLE_ROOT")
    return Path(root) if root else Path(__file__).parent.parent


def config_dir() -> Path:
    return _portable_root() / "config"


def data_dir() -> Path:
    return _portable_root() / "data"


def logs_dir() -> Path:
    return _portable_root() / "logs"


def _update_example_file(cfg_dir: Path) -> None:
    """Always overwrite config.toml.example with the bundled version.
    This ensures users always have an up-to-date reference as NOVA updates."""
    try:
        src = Path(__file__).parent / "config.toml.example"
        dst = cfg_dir / "config.toml.example"
        if src.exists():
            cfg_dir.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            _notify_self_write()  # prevent the watcher from re-triggering on this write
    except OSError:
        pass


def load() -> Config:
    cfg_dir     = config_dir()
    config_path = cfg_dir / "config.toml"

    # Always update the example file so users have the latest reference
    _update_example_file(cfg_dir)

    if not config_path.exists():
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
    tts_chat                 = True
    tts_twitch               = True
    tts_youtube              = True
    prune_events_days        = 0
    fuel_warning_percent     = 25
    home_system              = ""
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
                            "AST": "assets", "STS": "stats",
                            # Legacy abbrevs — silently migrate old configs
                            "WLT": "assets", "INV": "assets", "DKG": "overview",
                        }
                        _panels = []
                        _seen = set()
                        for a in v.split():
                            mode = _abbrev_to_mode.get(a.upper())
                            if mode and mode not in _seen:
                                _panels.append(mode)
                                _seen.add(mode)
                        if _panels:
                            situational_panels = _panels
                    case "tts_chat":
                        tts_chat = v.lower() not in ("false", "0", "no")
                    case "tts_twitch":
                        tts_twitch = v.lower() not in ("false", "0", "no")
                    case "tts_youtube":
                        tts_youtube = v.lower() not in ("false", "0", "no")
                    case "prune_events_days":
                        try:
                            prune_events_days = max(0, int(v))
                        except ValueError:
                            pass
                    case "fuel_warning_percent":
                        try:
                            fuel_warning_percent = max(0, min(100, int(v)))
                        except ValueError:
                            pass
                    case "home_system":
                        home_system = v
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
        tts_chat=tts_chat,
        tts_twitch=tts_twitch,
        tts_youtube=tts_youtube,
        prune_events_days=prune_events_days,
        fuel_warning_percent=fuel_warning_percent,
        home_system=home_system,
    )


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


def save(cfg: "Config", path: "Path | None" = None) -> None:
    """Write *cfg* back to *path* (default: ``config/config.toml`` in the install dir).

    Produces a minimal k=v file containing only the settings supported by the
    Settings overlay. Preserves no user comments; existing content is replaced.
    """
    if path is None:
        path = config_dir() / "config.toml"

    lines: list[str] = [
        "# NOVA — saved by Settings overlay\n",
        "\n",
    ]

    if cfg.journal_dir:
        lines.append(f"journal_dir = {cfg.journal_dir}\n")
    if cfg.twitch_channel:
        lines.append(f"twitch_channel = {cfg.twitch_channel}\n")
    if cfg.youtube_channel:
        lines.append(f"youtube_channel = {cfg.youtube_channel}\n")

    lines.append(f"tts_lang = {cfg.tts_lang}\n")
    lines.append(f"tts_rate = {cfg.tts_rate}\n")

    for lang, voice in cfg.tts_voices.items():
        lines.append(f"tts_voice_{lang} = {voice}\n")

    lines.append(f"default_volume = {cfg.default_volume}\n")
    lines.append(f"notable_value_threshold = {cfg.notable_value_threshold}\n")
    lines.append(f"carrier_lookup = {'true' if cfg.carrier_lookup else 'false'}\n")

    if cfg.debug_log:
        lines.append("debug_log = true\n")
    if cfg.screenshot_dir:
        lines.append(f"screenshot_dir = {cfg.screenshot_dir}\n")
    if cfg.screenshot_dest:
        lines.append(f"screenshot_dest = {cfg.screenshot_dest}\n")
    if cfg.chat_lang:
        lines.append(f"chat_lang = {cfg.chat_lang}\n")
    if cfg.situational_panels:
        _mode_to_abbrev = {
            "overview": "OVR", "bio": "BIO", "galaxy": "MAP",
            "missions": "MIS", "engineers": "ENG", "bgs": "BGS",
            "colonisation": "COL", "route": "ROU", "neutron": "NTR",
            "assets": "AST", "stats": "STS",
        }
        abbrevs = " ".join(_mode_to_abbrev.get(m, m.upper()) for m in cfg.situational_panels)
        lines.append(f"situational_panels = {abbrevs}\n")

    if cfg.tts_chat is not True:
        lines.append(f"tts_chat = {'true' if cfg.tts_chat else 'false'}\n")
    if cfg.tts_twitch is not True:
        lines.append(f"tts_twitch = {'true' if cfg.tts_twitch else 'false'}\n")
    if cfg.tts_youtube is not True:
        lines.append(f"tts_youtube = {'true' if cfg.tts_youtube else 'false'}\n")

    if cfg.prune_events_days > 0:
        lines.append(f"prune_events_days = {cfg.prune_events_days}\n")
    if cfg.fuel_warning_percent != 25:
        lines.append(f"fuel_warning_percent = {cfg.fuel_warning_percent}\n")
    if cfg.home_system:
        lines.append(f"home_system = {cfg.home_system}\n")

    try:
        path.write_text("".join(lines), encoding="utf-8")
        _notify_self_write()
    except OSError:
        pass
