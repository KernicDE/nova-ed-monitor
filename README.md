# NOVA — Navigation, Operations, and Vessel Assistance

> [!NOTE]
> This project is 100% vibe-coded with LLM AI (Claude by Anthropic). Every line of code, every feature, and every bug fix was written through AI-assisted development.

A real-time TUI companion for **Elite Dangerous** — reads journal files, speaks events via TTS, and displays system / ship / route / bio-scan data in your terminal.

**Guides:** [Installation & Update](docs/Installation.md) · [Settings](docs/Settings.md) · [Usage Guide](docs/Usage.md)

## Features

- **Live TTS** via edge-tts — speaks jump events, combat alerts, bio distances, fuel warnings, docking, and more
- **NOVA voiceovers** — NOVA's own callouts are fully translated into all 7 supported languages with multiple random variants per event; user-editable TOML files per language
- **Multi-language** — detects and voices EN, DE, FR, IT, ES, PT, RU automatically per message
- **Twitch integration** — reads your Twitch chat anonymously and announces messages via TTS
- **YouTube live chat** — monitors your YouTube live stream chat anonymously (no API key needed) and announces messages via TTS
- **EDSM enrichment** — fetches body data in the background (no API key needed); downloads EDSM nightly dumps once per day for offline lookups
- **Power Play** — displays the controlling power and state (Exploited / Fortified / Control / etc.) for any system from the local EDSM cache
- **Nearest inhabited system** — shows the closest populated system and distance (ly) when exploring uninhabited space
- **Next-waypoint stations** — lists stations at the next jump destination in the Route panel (name, distance, services icons: M/S/O/R)
- **Terminal UI** — System / Ship / Route / Bodies / Situational / Events / Chat panels
- **Bio-scan assistant** — tracks sample distances, bearings, scan completion, and contextual remainder announcements per species
- **Bio value estimation** — shows genus-based value range (e.g. `~3.4M–12.9M`) in the Bodies panel before full scan
- **Galaxy map** — Braille-rendered top-down map of the Milky Way with route waypoints
- **DSS efficiency** — announces whether the efficiency target was reached during detailed surface scanning
- **First footfall inference** — announces first footfall even when the journal flag is absent, based on first-discovery status
- **Statistics** — persistent stats page: jumps, distance, credits, FSS/DSS/bio counts and values, enemies destroyed, ships lost — broken down by today / week / month / year / total
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
# tts_voice_fr = fr-FR-DeniseNeural
# tts_voice_it = it-IT-ElsaNeural
# tts_voice_es = es-ES-ElviraNeural
# tts_voice_pt = pt-PT-RaquelNeural
# tts_voice_ru = ru-RU-SvetlanaNeural

# Stream overlay — each overlay_line_N defines one segment, joined by the separator.
# Lines whose variable evaluates to empty/zero are skipped automatically.
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

# Notable Bodies threshold: minimum body value (Cr) to appear in the Overview notable list.
# ELW / Water / Ammonia worlds, terraform candidates, and bio signals are always shown.
# notable_value_threshold = 500000
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
| `?` | Help & About screen |
| `↑` / `k` | Scroll event log up |
| `↓` / `j` | Scroll event log down |
| `PgUp` / `PgDn` | Scroll by 20 lines |
| `Home` / `g` | Jump to latest events |
| `Tab` | Cycle situational panel mode |
| `r` | Toggle galaxy map scale (galactic ↔ regional ±1000 ly) |
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

## Voiceline Customisation

On first launch NOVA copies all voiceline files into your config directory so they are easy to find and edit:

| Platform | Path |
|----------|------|
| Linux | `~/.config/nova/voicelines/` |
| Windows | `%USERPROFILE%\.config\nova\voicelines\` |

One file per language: `en.toml`, `de.toml`, `fr.toml`, `it.toml`, `es.toml`, `pt.toml`, `ru.toml`.

Each event key maps to a list of phrase variants — NOVA picks one at random each time. All available `{variables}` are documented in comments above each event key. Example:

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

Edit, add, or remove lines freely. On update, new event keys missing from your file fall back to the built-in automatically — your edits are never overwritten.

Set the voiceover language in config.toml:

```toml
tts_lang = de
```

Supported codes: `en`, `de`, `fr`, `it`, `es`, `pt`, `ru`

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

Chat messages are announced as: **"User {name} on Twitch {verb}: {message}"** / **"User {name} on YouTube {verb}: {message}"**

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

**System panel** shows population, economy, security, government, allegiance, faction, body counts, FSS progress, station count, Power Play state, and nearest inhabited system (when exploring uninhabited space).

**Route panel** shows the nav route, next-jump star type, distance, and — from the EDSM dump cache — a list of stations at the next waypoint with service icons (M=market, S=shipyard, O=outfitting, R=repair).

**Situational panel modes** (cycle with `Tab`):

| Mode | Description |
|------|-------------|
| Auto | Switches automatically: Bio → Missions → Overview |
| Overview | System diagram, notable bodies, session stats |
| Bio | Active bio scans with distances and bearings |
| Missions | Active mission list |
| Inventory | Cargo and materials |
| Engineers | Engineer unlock progress |
| Galaxy | Braille top-down galaxy map — `r` toggles galactic (±65k ly) / regional (±1k ly) |
| Stats | Persistent statistics: jumps, credits, FSS/DSS/bio, enemies, ships lost |

**Bio scan indicators:**
- `★` — first discovered species in the galaxy

---

## Bodies Panel Columns

| Column | Meaning |
|--------|---------|
| Body   | Short name, indented: planet / ↳ moon |
| Type   | Abbreviated body type |
| Val    | Actual scan value (gold if >1M Cr), `~3.4M–12.9M` genus estimate in amber while bio unsolved, or `~est` for planet type estimate |
| Dist   | Distance from arrival (ls) |
| B      | Bio signal count; `3✓` (gold) when all bio scans complete |
| G      | Geological signal count |
| LTA    | Flags: `L`=Landable, `T`=Terraformable, `A`=Atmosphere |
| F      | `●` = FSS scanned |
| D      | `●` = DSS mapped |

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
