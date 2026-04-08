# NOVA — Navigation, Operations, and Vessel Assistance

> [!NOTE]
> This project is 100% vibe-coded with LLM AI (Claude by Anthropic). Every line of code, every feature, and every bug fix was written through AI-assisted development.

A real-time TUI companion for **Elite Dangerous** — reads journal files, speaks events via TTS, and displays system / ship / route / bio-scan data in your terminal.

**Guides:** [Installation & Update](docs/Installation.md) · [Settings](docs/Settings.md) · [Usage Guide](docs/Usage.md)

---

## Features

### Voice & TTS
- **Live TTS** via edge-tts — speaks jump events, combat alerts, bio distances, fuel warnings, docking, and more
- **NOVA voiceovers** — fully translated into 7 languages with multiple random variants per event; user-editable TOML files per language
- **Multi-language detection** — automatically detects and voices EN, DE, FR, IT, ES, PT, RU per message
- **Twitch integration** — reads your Twitch chat anonymously and announces messages via TTS
- **YouTube live chat** — monitors your YouTube live stream chat anonymously (no API key needed)

### Exploration
- **Bio-scan assistant** — tracks sample distances, bearings, scan completion, and contextual remainder announcements per species; first footfall bonus announced when all 3 samples scanned
- **Bio value estimation** — shows genus-based value range (e.g. `~3.4M–12.9M`) before DSS, and predicted genera after FSS based on planet conditions
- **First footfall inference** — announces first footfall bonus even when the journal flag is absent, based on first-discovery status
- **High-G body warning** — TTS warning at ≥1.5 G; three repeated alerts and orange border flash for extreme gravity (≥3 G)
- **DSS efficiency** — announces whether the efficiency target was reached during detailed surface scanning
- **EDSM enrichment** — downloads EDSM nightly dumps for offline lookups; no API key needed
- **Power Play** — displays controlling power and state (Exploited / Fortified / Control / etc.) from local EDSM cache
- **Nearest inhabited system** — shows closest populated system and distance when exploring uninhabited space

### Navigation & Route
- **Route situation panel** — shows each jump in the active nav route with star type, scoopable indicator, distance from current position, jump distance, and EDSM presence; scrollable
- **Neutron route planner** — local neutron route calculator using a daily-refreshed Spansh dump; press `n` in Neutron panel to enter destination
- **Next-waypoint stations** — lists stations at the next jump destination (name, distance, services icons: M/S/O/R)
- **Fleet carrier lookup** — optionally queries Spansh API for carriers in current system (enable with `carrier_lookup = true`; cached 5 min)

### Terminal UI
- **System / Ship / Route / Bodies / Situational / Events / Chat panels**
- **Situational panel** (14 modes, cycle with `Tab` / `Shift+Tab`):
  - Auto-switches by context; toggle auto-lock with `a`
  - Panel visibility and order configurable via `situational_panels` in config
  - Active mode shown with full name in the border title
- **Power distribution (PIPs)** — live SYS/ENG/WEP pip display with half-pip support (●◑○)
- **Two-column system info** — exploration/natural data left, BGS/human data right
- **Galaxy map** — Braille top-down map of the Milky Way with route waypoints; `r` toggles scale
- **Local time** — current system time shown in the footer bar
- **Color-coded event log** — category abbreviation in category color

### Ship & Commander
- **Wallet & fleet** — Wealth panel: credit balance, fleet across all stations, cargo, materials, suit loadout, backpack
- **Engineer progress** — rank bars, rank-progress %, specialty and system for all ~36 engineers; Odyssey engineers shown as X/1 (not X/5)
- **Screenshot processing** — converts BMP→PNG, renames to `YYYY-MM-DD-HH-MM_CMDR_SYSTEM_BODY.png`, moves to `~/Pictures/Elite Dangerous`
- **Statistics** — persistent stats: jumps, distance, credits, FSS/DSS/bio, enemies, ships lost — today / week / month / year / total

### Data & Persistence
- **Persistent event log** — replays journal history from SQLite across sessions, including bodies from previous sessions
- **Keybindings backup** — backs up your ED `.binds` file on changes; last 5 versions kept
- **Stream overlay** — writes `.txt` files per data field for OBS/Streamlabs
- **Auto-installing launcher** — installs Python, NOVA, and dependencies automatically; auto-updates on every launch
- **Debug logging** — enable `debug_log = true` to write a full session log for diagnostics

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

1. Download [`install_windows.bat`](https://github.com/KernicDE/nova-ed-monitor/releases/latest/download/install_windows.bat) from the latest release
2. Double-click **`install_windows.bat`**

That's it. The installer downloads the launcher files to `%USERPROFILE%\nova\`, installs Python 3.12 (if missing), creates an isolated virtual environment, installs NOVA, and launches it.

On every subsequent launch, double-click **`nova.bat`** in `%USERPROFILE%\nova\`. It checks for updates automatically each time.

> ⚠️ Always download from the **Releases** section — downloading script files from the GitHub repository page gives you HTML, not the actual file.

---

## Running NOVA

| Platform | Command |
|----------|---------|
| Linux — launcher | `./nova.sh` |
| Linux — direct | `nova` |
| Windows — launcher | double-click `nova.bat` in `%USERPROFILE%\nova\` |

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

# TTS voices per language (edge-tts voice names):
# tts_voice_en = en-GB-SoniaNeural
# tts_voice_de = de-DE-KatjaNeural

# Notable Bodies threshold (Cr):
# notable_value_threshold = 500000

# Fleet carrier lookup via Spansh API:
# carrier_lookup = false

# Situational panel visibility and order:
# situational_panels = OVR BIO MAP MIS ENG BGS COL ROU NTR WLT INV DKG STS

# Screenshot processing:
# screenshot_dir  = /path/to/ED/screenshots
# screenshot_dest = ~/Pictures/Elite Dangerous

# Debug log:
# debug_log = false
```

### Finding the Journal Directory Manually

| Platform | Path |
|----------|------|
| Linux (Steam / Proton) | `~/.local/share/Steam/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous` |
| Windows | `C:\Users\YourName\Saved Games\Frontier Developments\Elite Dangerous` |
| macOS | `~/Library/Application Support/Frontier Developments/Elite Dangerous` |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` / `Esc` | Quit |
| `?` | Help & About screen |
| `Tab` | Cycle situational panel forward |
| `Shift+Tab` | Cycle situational panel backward |
| `a` | Toggle auto panel switching on/off |
| `↑` / `k` | Scroll situational panel up |
| `↓` / `j` | Scroll situational panel down |
| `PgUp` / `PgDn` | Scroll event log by 20 lines |
| `Home` / `g` | Jump to latest events |
| `w` / `s` | Scroll bodies panel up / down |
| `n` | Enter neutron route destination (Neutron panel) |
| `r` | Toggle galaxy map scale (galactic ↔ regional) |
| `+` / `=` | Volume up |
| `-` | Volume down |

---

## UI Layout

```
┌─ System ─────────┬─ Ship ──────────────────────┬─ Route ────┐
│ System/faction   │ Hull/Shield/Fuel gauges     │ Nav route  │
├──────────────────┴─────────────────────────────┴────────────┤
│ Scanned Bodies   │ SITUATION panel             │ Events     │
│ (FSS, DSS,       │ (14 modes, Tab to cycle)    ├────────────┤
│  values, dist)   │                             │ Chat log   │
├──────────────────┴─────────────────────────────┴────────────┤
│ q Quit  Tab Mode  ? Help  ↑↓ Scroll  +/- Vol  HH:MM  v1.x  │
└─────────────────────────────────────────────────────────────┘
```

### Situational Panel Modes

The border title shows all modes as abbreviations; the active one expands to its full name.
`***` = Auto mode indicator (dim blue when locked with `a`).

| Abbrev | Full Name | Description |
|--------|-----------|-------------|
| `***` | AUTO | Auto-switches by context; lock/unlock with `a` |
| `OVR` | OVERVIEW | System diagram, notable bodies, session stats |
| `BIO` | BIOLOGICAL | Active bio scans with distances and bearings |
| `MAP` | GALAXY MAP | Braille top-down galaxy map (`r` = scale toggle) |
| `MIS` | MISSION | Active mission list |
| `ENG` | ENGINEERS | Rank bars, progress %, specialty and system |
| `BGS` | BGS | BGS activity log |
| `COL` | COLONISATION | Construction site commodity progress |
| `ROU` | ROUTE | Nav route: star type, scoopable, distances, EDSM |
| `NTR` | NEUTRON | Local neutron route planner (`n` = new route) |
| `WLT` | WALLET | Credits, fleet, cargo, suit loadout, backpack |
| `INV` | INVENTORY | Cargo and materials |
| `DKG` | DOCKING | Station pad diagram |
| `STS` | STATISTICS | Persistent statistics |

**Auto mode priority:** Docking granted → Bio (active/pre-scan) → Colonisation → Missions → Overview; Stats when offline.

**Panel config:** Set `situational_panels = OVR BIO ROU MIS ...` in config.toml to control which panels appear and in what order. Omitted panels are hidden from the title bar and auto-switching.

---

## Bodies Panel Columns

| Column | Meaning |
|--------|---------|
| Body | Short name, indented: planet / ↳ moon |
| Type | Abbreviated body type |
| Val | Actual scan value (gold), `~3.4M–12.9M` genus estimate (amber), or `~est` for planet type estimate |
| Dist | Distance from arrival (ls) |
| B | Bio signal count; `3✓` (gold) when all bio scans complete |
| G | Geological signal count |
| LTA | Flags: `L`=Landable, `T`=Terraformable, `A`=Atmosphere |
| F | `●` = FSS scanned |
| D | `●` = DSS mapped |

---

## Stream Overlay for OBS/Streamlabs

NOVA writes individual `.txt` files to `~/.config/nova/overlay/` (configurable via `overlay_dir`). Add each file as a **Text** source in OBS/Streamlabs with "Read from file" enabled.

Available files: `commander`, `ship_name`, `ship_type`, `ship_ident`, `system`, `position`, `station`, `approach_body`, `route_destination`, `route_next`, `jumps_left`, `hull`, `fuel`, `fuel_max`, `fuel_reservoir`, `cargo`, `heat`, `shields`, `status`, `supercruise`, `docked`, `landed`, `power`, `power_state`, `allegiance`, `economy`, `security`, `government`, `population`, `nearest_inhabited`, `heading`, `altitude`, `coordinates`

---

## Voiceline Customisation

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/voicelines/` |
| Windows | `%USERPROFILE%\.config\nova\voicelines\` |

One file per language: `en.toml`, `de.toml`, `fr.toml`, `it.toml`, `es.toml`, `pt.toml`, `ru.toml`.

Each event key maps to a list of phrase variants — NOVA picks one at random each time. Edit, add, or remove lines freely. On update, new event keys missing from your file fall back to the built-in automatically.

```toml
[FSDJump]
# {system}  = destination star system name
# {dist_ly} = jump distance formatted for speech
lines = [
    "Arrived in {system}. Jump {dist_ly}.{suffix}",
    "Hyperspace complete. Welcome to {system}.{suffix}",
]
```

---

## TTS Languages

| Language | Default Voice | Chat verb |
|----------|---------------|-----------|
| English | en-GB-SoniaNeural | says |
| German | de-DE-KatjaNeural | sagt |
| French | fr-FR-DeniseNeural | dit |
| Italian | it-IT-ElsaNeural | dice |
| Spanish | es-ES-ElviraNeural | dice |
| Portuguese | pt-PT-RaquelNeural | diz |
| Russian | ru-RU-SvetlanaNeural | говорит |

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
| `~/.config/nova/bindings_backup/` | Linux | Keybindings backups |
| `%USERPROFILE%\.config\nova\bindings_backup\` | Windows | Keybindings backups |
| `~/.config/nova/nova-debug.log` | Linux | Debug log (when `debug_log = true`) |
| `%USERPROFILE%\.config\nova\nova-debug.log` | Windows | Debug log (when `debug_log = true`) |

---

## Troubleshooting

**"No events are showing / journal not found"**
→ Set `journal_dir` manually in config.toml

**"No TTS voice / audio"**
→ On Arch: `yay -S python-pygame`; elsewhere: `pip install --upgrade pygame` inside the NOVA venv

**"nova: command not found" (Linux)**
→ Run `./nova.sh` once; add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`

**"Access denied" / execution policy error (Windows)**
→ Right-click `nova.bat` → "Run as administrator" once, or run:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**TTS is too fast/slow**
→ Change `tts_rate` in config.toml — e.g. `tts_rate = +0%` for normal, `tts_rate = +20%` for faster

**Something is broken / need to report a bug**
→ Add `debug_log = true` to config.toml, reproduce the issue, then send `nova-debug.log` with your report

---

## License

MIT
