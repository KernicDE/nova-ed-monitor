# NOVA — Navigation, Operations, and Vessel Assistance

A real-time TUI companion for **Elite Dangerous** — reads journal files, speaks events via TTS, and displays system / ship / route / bio-scan data in your terminal.

## Features

- **Live TTS** via edge-tts — speaks events, chat, bio distances, fuel warnings
- **Multi-language** — detects and voices EN, DE, FR, IT, ES, PT, RU automatically
- **Twitch integration** — reads your chat anonymously, announces messages with "Twitch" prefix
- **EDSM enrichment** — fetches body data in the background (no API key needed)
- **Terminal UI** — System / Ship / Route / Bodies / Situational / Events / Chat panels
- **Bio-scan assistant** — tracks distances, bearings, and completion state
- **Stream overlay** — writes `stream_info.txt` for OBS/Streamlabs marquees
- **Event log** — persists journal events to SQLite across sessions

---

## Installation

### Via pipx (recommended)

```bash
pipx install nova-ed-monitor
nova
```

### Via pip

```bash
pip install nova-ed-monitor
nova
```

### From source

```bash
git clone https://github.com/KernicDE/nova-ed-monitor
cd nova-ed-monitor
pip install -e .
nova
```

NOVA auto-detects your Elite Dangerous journal directory for Steam/Proton installs.

---

## Requirements

- Python 3.11+
- `edge-tts` CLI (installed automatically with `pip install nova-ed-monitor`)
- `pygame` for audio (installed automatically)
- Elite Dangerous with journal files enabled

---

## Configuration

Config file created on first launch: **`~/.config/nova/config.toml`**

```toml
# Journal directory (auto-detected for Steam/Proton — override if needed):
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous

# Twitch integration (leave commented to disable):
# twitch_channel = yourchannel

# TTS voice rate:
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

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` / `Esc` | Quit |
| `↑` / `k` | Scroll event log up |
| `↓` / `j` | Scroll event log down |
| `PgUp` / `PgDn` | Scroll by 20 |
| `Home` / `g` | Jump to top |
| `Tab` | Cycle situational panel mode |
| `+` / `=` | Volume up |
| `-` | Volume down |

---

## Layout

```
┌─ System ─────────┬─ Ship ───────────────────────┬─ Route ────┐
│ System/faction   │ Hull/Shield/Fuel gauges      │ Nav route  │
│ BGS/security     │ Status flags                 │ or body    │
├─ Bodies ─────────┴─ Situational ────────────────┴─ Events ───┤
│ Scanned bodies   │ Overview / Inventory /        │ Event log  │
│ with FSS/DSS     │ Bio scans / Missions /        ├────────────┤
│ values and dist  │ Engineers                     │ Chat log   │
├──────────────────┴───────────────────────────────┴────────────┤
│ Keybindings                                      Vol 50% ●   │
└───────────────────────────────────────────────────────────────┘
```

---

## TTS Languages

Language is detected per message. Character sets take priority (Cyrillic → ñ → ã/õ → umlauts), then common word lists.

| Language   | Default Voice         | Chat verb  |
|------------|-----------------------|------------|
| English    | en-GB-SoniaNeural     | says       |
| German     | de-DE-KatjaNeural     | sagt       |
| French     | fr-FR-DeniseNeural    | dit        |
| Italian    | it-IT-ElsaNeural      | dice       |
| Spanish    | es-ES-ElviraNeural    | dice       |
| Portuguese | pt-PT-RaquelNeural    | diz        |
| Russian    | ru-RU-SvetlanaNeural  | говорит    |

Twitch messages are announced as: **"Twitch {user} {verb}: {message}"**

---

## Journal Auto-Detection

| Platform | Path |
|----------|------|
| Linux (Steam Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/.../Saved Games/...` |
| Linux (Steam symlink) | `~/.steam/steam/steamapps/compatdata/359320/...` |
| Linux (Flatpak Steam) | `~/.var/app/com.valvesoftware.Steam/...` |
| Windows | `~/Saved Games/Frontier Developments/Elite Dangerous` |
| macOS | `~/Library/Application Support/Frontier Developments/Elite Dangerous` |

---

## Bodies Panel Columns

| Column | Meaning |
|--------|---------|
| Body   | Short name, indented: planet / ↳ moon |
| Type   | Abbreviated body type |
| Value  | Actual value or `~est` |
| Dist   | Distance from arrival (ls) |
| Bio/Geo| Signal counts |
| Atm    | Atmosphere |
| Lnd    | Landable |
| ★      | First discovered |
| T      | Terraformable |
| Sc     | `F`=FSS scanned, `D`=DSS mapped, `FD`=both |

---

## Data Paths

| Path | Contents |
|------|----------|
| `~/.config/nova/config.toml` | Configuration |
| `~/.local/share/nova/events.db` | SQLite event log |
| `./stream_info.txt` | OBS/Streamlabs overlay (written to current dir) |

---

## Architecture

```
ed_monitor/
  __main__.py    Entry point, thread launcher
  config.py      Config (~/.config/nova/config.toml)
  state.py       AppState + dataclasses (thread-safe shared state)
  events.py      Journal event handlers, TTS, language detection
  journal.py     Journal file tail + inode rotation + DB replay
  status.py      Status.json / Cargo.json / Materials.json polling
  edsm.py        EDSM body/station fetch (GET-only, no key needed)
  db.py          SQLite persistence
  tts.py         edge-tts subprocess + pygame playback
  twitch.py      Twitch IRC anonymous reader
  overlay.py     stream_info.txt writer
  ui/app.py      NOVAApp (Textual TUI, 500ms refresh)
  ui/panels.py   All panel widgets
```

Threads: `journal`, `status`, `tts`, `edsm`, `twitch` (optional), `overlay`
State: `AppState` protected by `threading.RLock` — threads write, Textual reads via snapshot.

---

## License

MIT
