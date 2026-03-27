# Settings Guide

The config file is created automatically on first launch.

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/config.toml` |
| Windows | `%USERPROFILE%\.config\nova\config.toml` |

Open it with any text editor. All settings are optional — commented lines use defaults.

---

## Journal Directory

```toml
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous
```

NOVA auto-detects the journal directory on most setups. Set this only if auto-detection fails.

**Default locations:**

| Platform | Path |
|----------|------|
| Linux (Steam/Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Windows | `C:\Users\YourName\Saved Games\Frontier Developments\Elite Dangerous` |
| macOS | `~/Library/Application Support/Frontier Developments/Elite Dangerous` |

---

## TTS Voice & Language

```toml
# Language for NOVA's own voiceovers (en, de, fr, it, es, pt, ru):
# tts_lang = en

# Voice speed adjustment (e.g. +10%, -5%, +0%):
# tts_rate = +10%

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural
```

**Supported languages:** `en` (English), `de` (German), `fr` (French), `it` (Italian), `es` (Spanish), `pt` (Portuguese), `ru` (Russian)

Language detection for chat messages and in-game names is **automatic** — NOVA detects the language per message and picks the correct voice.

To find all available edge-tts voices:
```bash
edge-tts --list-voices
```

---

## Twitch Integration

```toml
# Twitch channel name — leave commented to disable:
# twitch_channel = yourchannel
```

Reads chat anonymously (no login, no API key needed). Announces messages via TTS as:
*"User {name} on Twitch says: {message}"*

---

## YouTube Live Chat

```toml
# YouTube channel handle — leave commented to disable:
# youtube_channel = @yourchannel
```

Monitors your live stream chat anonymously (no API key needed). Announces messages via TTS as:
*"User {name} on YouTube says: {message}"*

---

## Notable Body Value Threshold

```toml
# Minimum body value (Cr) to appear in the Overview notable bodies list.
# ELW / Water / Ammonia worlds, terraform candidates, and bio signals are always shown.
# notable_value_threshold = 500000
```

---

## Stream Overlay (OBS/Streamlabs)

NOVA writes a text file for use as a "Read from file" **Text** source in OBS or Streamlabs.

```toml
# overlay_line_1 = NOVA
# overlay_line_2 = {ship_name} ({ship_type})
# overlay_line_3 = {system} — {position}
# overlay_line_4 = JUMPS: {jumps_left}
# overlay_separator =      ////
# overlay_uppercase = true
# overlay_path = stream_info.txt
```

Lines whose variable evaluates to empty/zero are skipped automatically.

**Available variables:**

| Variable | Example |
|----------|---------|
| `{commander}` | `CMDR Hawk` |
| `{ship_name}` | `Krait Phantom` |
| `{ship_type}` | `KraitPhantom` |
| `{system}` | `Sol` |
| `{position}` | `Hutton Orbital` or `Deep Space` |
| `{jumps_left}` | `4` (line skipped when 0) |
| `{route_next}` | `Alpha Centauri` (line skipped when empty) |
| `{hull_pct}` | `98%` |
| `{fuel_t}` | `28.4t` |
| `{fuel_max_t}` | `32t` |

---

## Voiceline Customisation

On first launch NOVA copies all voiceline files to your config directory:

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/voicelines/` |
| Windows | `%USERPROFILE%\.config\nova\voicelines\` |

One file per language: `en.toml`, `de.toml`, `fr.toml`, `it.toml`, `es.toml`, `pt.toml`, `ru.toml`.

Each event key maps to a list of phrase variants — NOVA picks one at random. Example:

```toml
[FSDJump]
# {system}  = destination star system name
# {dist_ly} = jump distance formatted for speech
# {suffix}  = optional extra info (star class, hops remaining, population)
lines = [
    "Arrived in {system}. Jump {dist_ly}.{suffix}",
    "Hyperspace complete. Welcome to {system}.{suffix}",
    "Jump complete. Now in {system}.{suffix}",
]
```

Edit, add, or remove lines freely. On update, new event keys missing from your file fall back to the built-in automatically — **your edits are never overwritten**.
