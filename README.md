# NOVA — Navigation, Operations, and Vessel Assistance

> [!NOTE]
> This project is 100 % vibe-coded with LLM AI (Claude by Anthropic, Kimi by Moonshot AI). Every line of code, every feature, and every bug fix was written through AI-assisted development.

A real-time TUI companion for **Elite Dangerous**. Tails the journal, speaks events via TTS, and renders a cockpit-style dashboard in your terminal.

---

## Quick Start

### Linux

```bash
curl -O https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh
chmod +x nova.sh
./nova.sh
```

### Windows

1. Download [`nova.ps1`](https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1) — right-click → **Save As** into a folder of your choice (e.g. `C:\Nova\`).
2. Right-click **`nova.ps1`** → **Run with PowerShell**.

> If PowerShell blocks the script, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Both launchers install Python (if missing), create a `venv` next to the script, install NOVA, and auto-update on every subsequent launch. **All data lives in the same folder as the launcher** — config, database, logs, venv. Nothing is installed system-wide.

Full installation options (pip, wheel, standalone Linux binary, clone) are in **[docs/Installation.md](docs/Installation.md)**.

---

## Documentation

| Guide | Contents |
|-------|----------|
| **[Installation & Update](docs/Installation.md)** | Launcher scripts, pip install, data paths, uninstall, troubleshooting. |
| **[Settings](docs/Settings.md)** | Every `config.toml` key, voiceline customisation, template engine, stream overlay. |
| **[Usage Guide](docs/Usage.md)** | Keyboard shortcuts, every panel explained, bio/neutron/high-G workflows, stats. |

---

## Features at a glance

### Voice
- Live TTS via **edge-tts** with random variants per event and full template engine (includes, conditionals, AND/OR). 7 built-in languages.
- **Multi-language chat detection** for Twitch / YouTube / in-game chat — each message voiced in its detected language.
- Hot-reloadable voiceline files (`en.toml`, `de.toml`, …) with `add` / `replace` / `replace = []` semantics.
- Optional **AI-generated voice lines** — swap the static template system for on-the-fly text from `kimi -p` or `claude -p` (opt-in, `voice_engine` setting). Falls back to the static line if the CLI is missing, slow, or errors out. Rapid event bursts (e.g. FSS scans) are grouped into a single AI call.
- Optional **personality file** shapes the AI's tone (`config/personality/default.toml`), mirroring the voiceline override pattern.
- Optional **ambient commentary** — NOVA occasionally remarks on your situation unprompted, every 180–360 s (random, togglable), when AI voice is enabled.

### Exploration
- Bio-scan assistant: sample distances, compass bearings, scan completion, first-footfall bonus detection.
- Bio value range estimates from FSS data (predicted genera) → DSS-confirmed ranges → actual scan values.
- Frontier-formula body values with full DSS multiplier chain (first-discovered, first-mapped, efficiency, Odyssey footfall).
- High-G body warning at ≥ 1.5 G (single) and ≥ 3 G (repeat + orange border flash).

### Navigation & Maps
- **Route** panel with per-waypoint star class, scoopable flag, distances, and live EDSM body/bio totals.
- Offline **neutron route planner** (Spansh dump, daily refresh).
- Fleet-carrier lookup (Spansh API, opt-in).
- Galaxy map (Braille, with route waypoints) — system / regional / galactic zoom.

### Terminal UI
- 14-mode **Situational** panel, auto-switching by context (`a` to lock). Mission panel groups by destination with cargo totals, type badges, reward column, wing/influence markers, and massacre kill-stack bars with per-threshold milestones.
- In-app **Settings overlay** (`s` key) — every key, live-applied.
- **Custom themes** — TOML-based colour theming with two built-in palettes (Default, Sakura Night) and full user customisation.
- Hot-reload for `config.toml` and voiceline files within ~2 s.
- Power-distribution pips, two-column system info, color-coded event + chat logs.

### Integrations
- **Twitch** chat (anonymous, no API key) → panel + TTS.
- **YouTube** live chat (anonymous, no API key) → panel + TTS.
- **EDSM** nightly dumps (systems / stations / Power Play) stored locally.
- **Spansh** API for fleet carriers (opt-in).
- Stream **overlay**: per-field `.txt` files for OBS / Streamlabs.
- Automatic **screenshot** rename + BMP→PNG conversion.
- Automatic **.binds** file backups (last 5 kept).

---

## Configuration

The config file is created automatically on first launch. Press **`s`** inside NOVA for the in-app settings overlay — the easiest way to change anything without editing files.

| Install type | Path |
|-------------|------|
| Portable (launcher) — Linux | `<script folder>/config/config.toml` |
| Portable (launcher) — Windows | `<script folder>\config\config.toml` |
| System install — Linux | `~/.config/nova/config.toml` |
| System install — Windows | `%USERPROFILE%\.config\nova\config.toml` |

See **[docs/Settings.md](docs/Settings.md)** for every key, including AI-generated voice, personality, and ambient commentary.

---

## Keyboard shortcuts (summary)

| Key | Action |
|-----|--------|
| `q` / `Esc` | Quit |
| `s` | Open Settings overlay |
| `?` | Help & About screen |
| `Tab` / `Shift+Tab` | Cycle focused panel forward/backward (1→6) |
| `a` | Toggle auto-switching |
| `↑` / `↓` / `k` / `j` | Scroll situational panel (`MAP`: cycle sub-view) |
| `←` / `→` | Cycle situational panel modes |
| `PgUp` / `PgDn` | Scroll focused panel (or situational when none focused) |
| `Home` / `End` | Jump to top / bottom of focused panel |
| `Enter` | Engineers: open detail / return to list |
| `n` | Neutron route destination input (Neutron mode only) |
| `+` / `=` / `−` | Volume ±5 % |
| `m` / `g` / `t` / `y` / `p` | Mute all / chat / twitch / youtube / all-chat |

Full list with context-specific bindings in **[docs/Usage.md](docs/Usage.md)**.

---

## TTS languages

| Language | Default voice |
|----------|---------------|
| English | `en-GB-SoniaNeural` |
| German | `de-DE-KatjaNeural` |
| French | `fr-FR-DeniseNeural` |
| Italian | `it-IT-ElsaNeural` |
| Spanish | `es-ES-ElviraNeural` |
| Portuguese | `pt-PT-RaquelNeural` |
| Russian | `ru-RU-SvetlanaNeural` |

Change per-language voice in `config.toml` (`tts_voice_en = en-US-GuyNeural` etc.) or via the Settings overlay. `edge-tts --list-voices` shows every available voice.

---

## Requirements

- **Python 3.11+** (3.12 / 3.13 / 3.14 tested)
- **Linux, macOS, Windows** — all first-class
- For Linux on Steam/Proton the journal directory is auto-detected via the default Steam path, the Flatpak Steam path, and Heroic Games Launcher prefixes

---

## License

MIT — see `LICENSE`.
