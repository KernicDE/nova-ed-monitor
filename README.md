# NOVA — Navigation, Operations, and Vessel Assistance

A real-time TUI companion for **Elite Dangerous** — reads journal files, speaks events via TTS, and displays system / ship / route / bio-scan data in your terminal.

## Features

- **Live TTS** via edge-tts — speaks jump events, combat alerts, bio distances, fuel warnings, docking, and more
- **Multi-language** — detects and voices EN, DE, FR, IT, ES, PT, RU automatically per message
- **Twitch integration** — reads your Twitch chat anonymously and announces messages via TTS
- **EDSM enrichment** — fetches body data in the background (no API key needed)
- **Terminal UI** — System / Ship / Route / Bodies / Situational / Events / Chat panels
- **Bio-scan assistant** — tracks sample distances, bearings, and scan completion per species
- **Stream overlay** — writes a configurable text file for OBS/Streamlabs marquees
- **Persistent event log** — replays journal history from SQLite across sessions, including bodies scanned in previous sessions
- **Auto-installing launcher** — installs Python, NOVA, and all dependencies automatically; auto-updates on every launch

---

## Quick Start

### Linux

```bash
curl -O https://raw.githubusercontent.com/KernicDE/nova-ed-monitor/main/nova.sh
chmod +x nova.sh
./nova.sh
```

The script installs Python (if missing), creates an isolated virtual environment, installs NOVA, and launches it. On every subsequent launch it checks for updates automatically. A `nova` command is also installed to `~/.local/bin/nova`.

### Windows

⚠️ **Important:** Do NOT download files directly from the GitHub repository page — this will give you HTML content instead of the actual files. Always download from the **Releases** section.

**Option 1: Use the installer (recommended)**
1. Download [`install_windows.bat`](https://github.com/KernicDE/nova-ed-monitor/releases/latest/download/install_windows.bat) from the latest release
2. Double-click **`install_windows.bat`** to install and launch NOVA

**Option 2: Manual installation**
1. Download [`nova.ps1`](https://github.com/KernicDE/nova-ed-monitor/releases/latest/download/nova.ps1) and [`nova.bat`](https://github.com/KernicDE/nova-ed-monitor/releases/latest/download/nova.bat) from the latest release into the same folder
2. Double-click **`nova.bat`** to launch

Both methods install Python 3.12 (if missing), create a virtual environment, install NOVA, and launch it. On every launch they check for updates automatically.

---

## Running NOVA

| Platform | Command |
|----------|---------|
| Linux — launcher | `./nova.sh` |
| Linux — direct | `nova` |
| Windows — launcher | double-click `nova.bat` or run `.\nova.ps1` |

Both the launcher scripts and the `nova` command check for updates on every launch and upgrade automatically if a newer version is available on GitHub.

---

## Updating NOVA

Updates happen **automatically** on every launch — no manual action needed.

To force an immediate update run the launcher script:

```bash
# Linux
./nova.sh

# Windows
.\nova.ps1
```

---

## Uninstalling NOVA

### Linux

```bash
nova --uninstall
```

Removes the virtual environment (`~/.local/share/nova/`), config (`~/.config/nova/`), and the `nova` command itself. Prompts for confirmation. Elite Dangerous journal files are **not touched**.

After uninstalling, delete `nova.sh` manually if you no longer need it.

### Windows

```powershell
.\nova.ps1 -Uninstall
```

Or via the bat file:

```
nova.bat -Uninstall
```

Removes the virtual environment (`%LOCALAPPDATA%\nova\`), and config (`%USERPROFILE%\.config\nova\`). Prompts for confirmation. Elite Dangerous journal files are **not touched**.

After uninstalling, delete `nova.ps1` and `nova.bat` manually.

---

## Installation (alternative methods)

The launcher scripts above are the recommended way. If you prefer to install manually:

### pip from GitHub

```bash
# Linux (use a venv to avoid PEP 668 errors on modern distros)
python -m venv ~/nova-venv
~/nova-venv/bin/pip install git+https://github.com/KernicDE/nova-ed-monitor.git
~/nova-venv/bin/nova

# Windows
py -m pip install git+https://github.com/KernicDE/nova-ed-monitor.git
nova
```

### Wheel from releases

1. Go to the [Releases page](https://github.com/KernicDE/nova-ed-monitor/releases)
2. Download the `.whl` file
3. Install it:

```bash
pip install nova_ed_monitor-*.whl        # Linux (inside venv)
py -m pip install nova_ed_monitor-*.whl  # Windows
```

### Standalone Linux binary (no Python needed)

Download `nova-linux-x86_64` from the [latest release](https://github.com/KernicDE/nova-ed-monitor/releases/latest), then:

```bash
chmod +x nova-linux-x86_64
./nova-linux-x86_64
```

### Clone and install

```bash
git clone https://github.com/KernicDE/nova-ed-monitor.git
cd nova-ed-monitor
python -m venv .venv
.venv/bin/pip install .
.venv/bin/nova
```

---

## Configuration

The config file is created automatically on first launch at:

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/config.toml` |
| Windows | `%USERPROFILE%\.config\nova\config.toml` |

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

# Stream overlay output file and format:
# overlay_path = stream_info.txt
# overlay_line_1 = MY STREAM NAME
# overlay_line_2 = {ship_name} ({ship_type})
# overlay_line_3 = {system} — {position}
# overlay_line_4 = JUMPS: {jumps_left}
# overlay_separator =      ////
# overlay_uppercase = true
```

### Finding the Journal Directory Manually

Elite Dangerous journals are usually at:

| Platform | Path |
|----------|------|
| Linux (Steam / Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
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

NOVA writes a text file (`stream_info.txt` by default, in the directory where NOVA is launched) that you can add as a **Text (GDI+)** or **Text** source in OBS/Streamlabs with "Read from file" enabled.

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

Twitch messages are announced as: **"Twitch {user} {verb}: {message}"**

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

**Situational panel modes** (cycle with `Tab`): Overview · Bio scans · Missions · Inventory · Engineers

**Bio scan indicators:**
- `★` — first discovered species in the galaxy

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

## Data Paths

| Path | Platform | Contents |
|------|----------|----------|
| `~/.config/nova/config.toml` | Linux | Configuration |
| `%USERPROFILE%\.config\nova\config.toml` | Windows | Configuration |
| `~/.local/share/nova/events.db` | Linux | SQLite event log |
| `%LOCALAPPDATA%\nova\events.db` | Windows | SQLite event log |
| `~/.local/share/nova/venv/` | Linux | Python virtual environment |
| `%LOCALAPPDATA%\nova\venv\` | Windows | Python virtual environment |
| `stream_info.txt` | both | OBS/Streamlabs overlay (launch dir, configurable) |

---

## Troubleshooting

**"No events are showing / journal not found"**
→ Set `journal_dir` manually in config.toml (see above)

**"No TTS voice / audio"**
→ Make sure pygame works: on Arch try `yay -S python-pygame`; elsewhere `pip install --upgrade pygame` inside the NOVA venv

**"nova: command not found" (Linux)**
→ Run `./nova.sh` once — it installs the `nova` command to `~/.local/bin/`
→ Make sure `~/.local/bin` is in your PATH: add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`

**"Access denied" / execution policy error (Windows)**
→ Right-click `nova.bat` and choose "Run as administrator" once, or open PowerShell and run:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**TTS is too fast/slow**
→ Change `tts_rate` in config.toml — e.g. `tts_rate = +0%` for normal speed, `tts_rate = +20%` for faster

---

## License

MIT
