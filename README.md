# NOVA — Navigation, Operations, and Vessel Assistance

A real-time TUI companion for **Elite Dangerous** — reads journal files, speaks events via TTS, and displays system / ship / route / bio-scan data in your terminal.

## Features

- **Live TTS** via edge-tts — speaks events, chat, bio distances, fuel warnings
- **Multi-language** — detects and voices EN, DE, FR, IT, ES, PT, RU automatically
- **Twitch integration** — reads your chat anonymously, announces messages with "Twitch" prefix
- **EDSM enrichment** — fetches body data in the background (no API key needed)
- **Terminal UI** — System / Ship / Route / Bodies / Situational / Events / Chat panels
- **Bio-scan assistant** — tracks distances, bearings, completion, and first-footfall detection
- **Stream overlay** — writes a fully configurable text file for OBS/Streamlabs marquees
- **Event log** — persists journal events to SQLite across sessions

---

## Quick Start (TL;DR)

### Linux — Launcher script (easiest)
```bash
# Download once, then always use to launch NOVA:
curl -O https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh
chmod +x nova.sh
./nova.sh
```
The script installs Python and NOVA automatically if needed, then launches NOVA.
Run `./nova.sh --update` to update NOVA.

### Windows — Launcher script (easiest)
1. Download [`nova.ps1`](https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.ps1) and [`nova.bat`](https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.bat) into the same folder
2. Double-click **`nova.bat`** to launch

The script installs Python and NOVA automatically if needed.
Run `nova.bat -Update` (or open PowerShell: `.\nova.ps1 -Update`) to update NOVA.

---

## Installation

NOVA is **not on PyPI**. Use the launcher scripts above (recommended) or install directly from GitHub.

### Method 1: pip from GitHub (recommended)

Installs the latest version directly from the repository.

**Linux:**
```bash
pip install git+https://github.com/KernicDE/nova-ed-monitor.git
```

**Windows:**
```
py -m pip install git+https://github.com/KernicDE/nova-ed-monitor.git
```

> If you get a permissions error, add `--user`:
> `pip install --user git+https://github.com/KernicDE/nova-ed-monitor.git`

---

### Method 2: Download wheel from releases

1. Go to the [Releases page](https://github.com/KernicDE/nova-ed-monitor/releases)
2. Download the `.whl` file (e.g. `nova_ed_monitor-1.1.0-py3-none-any.whl`)
3. Install it:

```bash
# Linux
pip install nova_ed_monitor-*.whl

# Windows
py -m pip install nova_ed_monitor-*.whl
```

---

### Method 3: Clone and install

```bash
git clone https://github.com/KernicDE/nova-ed-monitor.git
cd nova-ed-monitor
pip install .
```

---

### Full Linux Setup — Step by Step

**Step 1: Check Python version**
```bash
python --version
```
Need Python 3.11 or higher. If not installed:

- **Arch Linux / Manjaro:** `sudo pacman -S python`
- **Ubuntu / Debian / Mint:** `sudo apt install python3 python3-pip`
- **Fedora:** `sudo dnf install python3 python3-pip`

**Step 2: Install NOVA**
```bash
pip install git+https://github.com/KernicDE/nova-ed-monitor.git
```

**Step 3: Audio support** (needed for TTS playback)

Most Linux desktops have this already. If you hear no voice:
- Arch: `yay -S python-pygame` or `pip install pygame --upgrade`
- Ubuntu: `sudo apt install python3-pygame` or `pip install pygame --upgrade`

**Step 4: Run NOVA**
```bash
nova
```
NOVA will auto-detect your Elite Dangerous journal files (Steam/Proton).
If it can't find them, see **Configuration** below.

---

### Full Windows Setup — Step by Step

**Step 1: Install Python**

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download and run the installer
3. **IMPORTANT:** Check **"Add Python to PATH"** before clicking Install

**Step 2: Open Command Prompt** — press `Win + R`, type `cmd`, press Enter

**Step 3: Install NOVA**
```
py -m pip install git+https://github.com/KernicDE/nova-ed-monitor.git
```

**Step 4: Run NOVA**
```
py -m ed_monitor
```

> The `nova` command also works if Python's Scripts folder is in PATH.

**Step 5 (optional): Desktop shortcut**

1. Right-click desktop → New → Shortcut
2. Enter: `cmd /k "py -m ed_monitor"`
3. Name it "NOVA"

---

### Updating NOVA

```bash
# Linux
pip install --upgrade git+https://github.com/KernicDE/nova-ed-monitor.git

# Windows
py -m pip install --upgrade git+https://github.com/KernicDE/nova-ed-monitor.git
```

---

## Configuration

The config file is created automatically on first launch at:
- **Linux:** `~/.config/nova/config.toml`
- **Windows:** `%APPDATA%\nova\config.toml` (or `C:\Users\YourName\.config\nova\config.toml`)

Open it with any text editor to adjust settings:

```toml
# Journal directory (auto-detected for Steam/Proton — override if needed):
# journal_dir = /path/to/Saved Games/Frontier Developments/Elite Dangerous

# Twitch integration (leave commented to disable):
# twitch_channel = yourchannel

# TTS voice rate:
# tts_rate = +10%

# TTS voices per language:
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural

# Stream overlay (custom format):
# overlay_line_1 = MY STREAM NAME
# overlay_line_2 = {ship_name} ({ship_type})
# overlay_line_3 = {system} — {position}
# overlay_line_4 = JUMPS: {jumps_left}
# overlay_separator =      ////
# overlay_uppercase = true
# overlay_path = stream_info.txt
```

### Finding the Journal Directory Manually

Elite Dangerous journals are usually at:

| Platform | Path |
|----------|------|
| Linux (Steam Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Windows | `C:\Users\YourName\Saved Games\Frontier Developments\Elite Dangerous` |
| macOS | `~/Library/Application Support/Frontier Developments/Elite Dangerous` |

Set it in config like this:
```toml
journal_dir = /home/yourname/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` / `Esc` | Quit |
| `↑` / `k` | Scroll event log up |
| `↓` / `j` | Scroll event log down |
| `PgUp` / `PgDn` | Scroll by 20 lines |
| `Home` / `g` | Jump to latest events |
| `Tab` | Cycle situational panel mode |
| `+` / `=` | Volume up |
| `-` | Volume down |

---

## Stream Overlay for OBS/Streamlabs

NOVA writes a text file (`stream_info.txt` by default) that you can add as a **Text (GDI+)** or **Text** source in OBS/Streamlabs with "Read from file" enabled.

**Custom format example** (in config.toml):
```toml
overlay_line_1 = MY STREAM
overlay_line_2 = {commander} in {ship_name}
overlay_line_3 = {system} / {position}
overlay_line_4 = {jumps_left} jumps left
overlay_separator =   |
overlay_uppercase = false
```

**Available variables:**

| Variable | Example output |
|----------|---------------|
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

## TTS Languages

Language is detected automatically per message:

| Language   | Default Voice         | Chat verb  |
|------------|-----------------------|------------|
| English    | en-GB-SoniaNeural     | says       |
| German     | de-DE-KatjaNeural     | sagt       |
| French     | fr-FR-DeniseNeural    | dit        |
| Italian    | it-IT-ElsaNeural      | dice       |
| Spanish    | es-ES-ElviraNeural    | dice       |
| Portuguese | pt-PT-RaquelNeural    | diz        |
| Russian    | ru-RU-SvetlanaNeural  | говорит    |

Twitch messages: **"Twitch {user} {verb}: {message}"**

---

## UI Layout

```
┌─ System ─────────┬─ Ship ──────────────────────┬─ Route ────┐
│ System/faction   │ Hull/Shield/Fuel gauges     │ Nav route  │
├──────────────────┴─────────────────────────────┴────────────┤
│ Scanned Bodies   │ Overview / Bio / Missions /  │ Events     │
│ (FSS, DSS,       │ Inventory / Engineers        ├────────────┤
│  values, dist)   │                              │ Chat log   │
├──────────────────┴──────────────────────────────┴────────────┤
│ Keybindings                                     Vol 50% ●   │
└───────────────────────────────────────────────────────────────┘
```

**Bio scan indicators:**
- `★` — first discovered species
- `✦` — first footfall on this body

---

## Bodies Panel Columns

| Column | Meaning |
|--------|---------|
| Body   | Short name, indented: planet / ↳ moon |
| Type   | Abbreviated body type |
| Value  | Actual or `~est` estimated |
| Dist   | Distance from arrival (ls) |
| Bio/Geo| Signal counts |
| Atm    | Atmosphere |
| Lnd    | Landable |
| ★      | First discovered |
| T      | Terraformable |
| Sc     | `F`=FSS scanned, `D`=DSS mapped |

---

## Troubleshooting

**"No events are showing / journal not found"**
→ Set `journal_dir` manually in config.toml (see above)

**"No TTS voice / audio"**
→ Make sure `edge-tts` is installed: `pip install edge-tts`
→ Make sure pygame works: `pip install --upgrade pygame`

**"nova command not found" (Linux)**
→ Try `python -m ed_monitor` instead
→ Or add `~/.local/bin` to your PATH: `export PATH="$HOME/.local/bin:$PATH"` (add to `~/.bashrc`)

**"nova command not found" (Windows)**
→ Use `py -m ed_monitor` instead
→ Or re-install Python with "Add to PATH" checked

**TTS is too fast/slow**
→ Change `tts_rate` in config.toml (e.g. `tts_rate = +0%` for normal, `tts_rate = +20%` for faster)

---

## Data Paths

| Path | Contents |
|------|----------|
| `~/.config/nova/config.toml` | Configuration |
| `~/.local/share/nova/events.db` | SQLite event log |
| `./stream_info.txt` | OBS/Streamlabs overlay (current dir, configurable) |

---

## License

MIT
