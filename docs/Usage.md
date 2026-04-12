# Usage Guide

## Starting NOVA

| Platform | Command |
|----------|---------|
| Linux — launcher | `./nova.sh` or `nova` |
| Windows — launcher | double-click `nova.bat` in `%USERPROFILE%\nova\` |
| Standalone binary | `./nova-linux-x86_64` |

NOVA automatically finds your Elite Dangerous journal files and starts monitoring. Launch it before or after starting the game — it will catch up.

---

## Interface Overview

```
┌─ System ─────────┬─ Ship ──────────────────────┬─ Target ───┐
│ System/faction   │ Hull/Shield/Fuel gauges     │ Nearby /   │
│                  │                             │ targeted   │
├──────────────────┴─────────────────────────────┴────────────┤
│ Scanned Bodies   │ Overview / Wealth / Bio /    │ Events     │
│ (FSS, DSS,       │ Missions / Engineers /       ├────────────┤
│  values, dist)   │ Neutron / Galaxy / Stats     │ Chat log   │
├──────────────────┴──────────────────────────────┴────────────┤
│ Keybindings                                     Vol 50% ●   │
└───────────────────────────────────────────────────────────────┘
```

**Mode indicators** (border colour):
- White/grey — Normal flight
- Orange — Extreme gravity approach (≥3 G)
- Green — Analysis mode (FSS/DSS)
- Purple — On foot
- Red — Combat mode
- Dark grey — Offline (game not running)

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
| `PgUp` / `PgDn` | Scroll focused panel by 5 (or situational panel when none focused) |
| `Home` / `g` | Jump to latest events (event log) |
| `w` / `s` | Scroll bodies panel up / down |
| `r` | Toggle galaxy map scale (galactic ↔ regional) |
| `n` | Open neutron route destination input (Neutron mode only) |
| `+` / `=` | Volume up (+5%) |
| `−` | Volume down (−5%) |

---

## Situational Panel (centre)

Press `Tab` / `Shift+Tab` to cycle through modes. Press `a` to lock/unlock auto-switching.

| Mode | Abbrev | Auto? | Description |
|------|--------|-------|-------------|
| **Auto** | `***` | — | Switches by context; `a` to toggle lock |
| Overview | `OVR` | ✓ | System diagram, notable bodies, session totals; nearest inhabited when in uninhabited space |
| Biological | `BIO` | ✓ | Active bio scans — distances, bearings, sample counts |
| Galaxy Map | `MAP` | — | Braille top-down galaxy map (`r` to toggle scale) |
| Missions | `MIS` | ✓ | Active mission list |
| Engineers | `ENG` | — | Rank bars, rank-progress %, specialty and system per engineer |
| BGS | `BGS` | — | BGS activity log for the current system |
| Colonisation | `COL` | ✓ | Construction site progress |
| Route | `ROU` | ✓ | Nav route with jump distances and EDSM body/station info |
| Neutron | `NTR` | — | Neutron route planner — press `n` to enter destination |
| Wallet | `WLT` | — | Credit balance, fleet locations, cargo, suit loadout, backpack |
| Inventory | `INV` | — | Cargo hold and materials |
| Docking | `DKG` | ✓ | Docking pad diagram |
| Statistics | `STS` | ✓ (offline) | Persistent statistics by today / week / month / year / total |

**Auto-switch priority (highest first):** offline → Stats · docking granted → Docking · incomplete bio scans or DSS'd bio body → Bio · colonisation active in system → Colonisation · missions (not in supercruise) → Missions · route set → Route · default → Overview.

---

## System Panel (top left)

Shows current system info in a two-column layout: natural/exploration data on the left, human/BGS data on the right.

| Left column | Right column |
|-------------|--------------|
| Bodies (stars/planets/moons) | Economy |
| FSS scan progress (stars always count as done) | Security |
| Power Play affiliation | Government / Allegiance |
| | Controlling faction |
| | Station count |

Below the two-column table, a single position line is shown when on a surface:
`At <nearest body>     Pos <lat, lon>     Alt <altitude m>`

Power Play state colour coding:
- Cyan — Control
- Green — Fortified / Stronghold
- Amber — Exploited
- Yellow — Contested
- Red — Turmoil

Power Play and nearest-inhabited data is sourced from EDSM nightly dumps, refreshed automatically once per day.

---

## Target Panel (top right)

Shows the most relevant target or nearby object. Priority order:

| Context | Content |
|---------|---------|
| Docked | Station name, type, economy, allegiance, distance, and services |
| Ship targeted | Ship type, pilot + rank, faction, legal status, bounty, shield/hull %, scan stage |
| Body targeted | Body type, arrival distance, atmosphere, landability + gravity, bio/geo signals, terraform flag |
| Approaching / nearby body | Same body details as above, labelled `APPROACHING` or `NEARBY` |
| Nearest station | Name, distance, type, and service icons from EDSM data |
| Nothing | Current system name and last jump distance |

**Ship target scan stages:** targeting a ship and keeping the lock progressively reveals more info — shield/hull at stage 1, faction and legal status at stage 2, full scan at stage 3.

**Legal status colours:** green = Clean · amber = Lawless · red = Wanted / Hostile / Enemy

---

## Bodies Panel (left)

Shows all scanned bodies in the current system.

| Column | Meaning |
|--------|---------|
| Body | Short name — indented moons shown as ↳ child |
| Type | Abbreviated body type |
| Val | Scan value (gold if >1M Cr); ×3.3 mapping bonus included when body is unmapped; `~3.4M–12.9M` estimate in amber before full scan |
| Dist | Distance from arrival (ls) |
| B | Bio signal count; `3✓` in gold when all scans complete |
| G | Geological signal count |
| LTA | `L`=Landable `T`=Terraformable `A`=Atmosphere |
| F | `●` = FSS scanned (stars always count as done) |
| D | `●` = DSS mapped |

**`★`** next to a species name = first discovered in the galaxy.

Bodies where `WasFootfalled=false` is set in the FSS scan data are pre-flagged for first footfall — NOVA announces the bonus as soon as you disembark, without waiting for the `FirstFootfall` journal flag.

---

## TTS & Volume

NOVA speaks jump events, combat alerts, bio distances, fuel warnings, docking, and more.

- Adjust volume with `+`/`=` (up) and `−` (down). Current volume is shown in the footer.
- Change speed in [config.toml](Settings#tts-voice--language): `tts_rate = +20%` (faster) or `+0%` (normal)
- Change voice or language in [config.toml](Settings#tts-voice--language)

Audio is generated at full quality and adjusted to your selected volume at playback.

---

## Bio Scan Assistant

When you scan a biological species on a planet surface:

1. NOVA shows the scan in the **Bio** panel with sample count, distance to next sample, and compass bearing
2. When you are far enough away from your last sample to take the next one, NOVA announces it via TTS
3. After all 3 samples, the scan is marked complete with total value

Minimum sample distances are species-specific — NOVA knows them all.

---

## High-G Body Warning

When your ship approaches a body with significant surface gravity, NOVA warns you via TTS:

| Gravity | Behaviour |
|---------|-----------|
| ≥ 1.5 G | Single TTS warning: *"Caution: 2.3 G body ahead."* |
| ≥ 3.0 G | Three TTS warnings spaced 10 s apart + full orange border flash |

The orange flash and repeat warnings stop automatically when the ship touches the ground. Both the warning and the flash clear on departure (`LeaveBody`) or when entering supercruise.

---

## Wealth Panel

The **Wealth** panel shows your financial and inventory overview across all locations:

- **Balance** — current credit total, tracked from login, market transactions, missions, and exploration sales
- **Fleet** — current ship plus all stored ships with their station and system
- **Cargo** — items currently in your ship's cargo hold
- **Materials** — count of raw / manufactured / encoded materials
- **Suit Loadout** — equipped suit and weapons (when on foot)
- **Backpack** — item counts while on foot

Data updates automatically from journal events. Open the in-game outfitting or shipyard interface once per session to populate the fleet list (`StoredShips` journal event).

---

## Neutron Route Planner

The **Neutron** panel plots neutron-boosted routes to any destination entirely offline:

1. Press `Tab` until the Neutron panel is active
2. Press `n` — a destination input box appears
3. Type the exact system name (as shown in-game) and press Enter
4. The route appears: each row shows the system, jump distance, and a `⚡` marker for neutron boosts

The planner uses your ship's current **max jump range** (read from the `Loadout` journal event — fly your ship at least once per session for accurate results). Neutron stars provide a 4× range boost.

Route data comes from a local Spansh neutron-star dump (`systems_neutron.json.gz`) refreshed once per day. No live internet connection is needed to plot routes. The first download takes place in the background on startup.

---

## Screenshot Processing

NOVA automatically processes screenshots taken in Elite Dangerous:

1. Detects new files in the ED screenshot folder (auto-detected for Proton and native installs)
2. Converts BMP → PNG if needed
3. Renames to `YYYY-MM-DD-HH-MM_CMDR_SYSTEM_BODY.png`
4. Moves to `~/Pictures/Elite Dangerous` (created automatically)

No setup required. To override folders, see [Settings → Screenshot Processing](Settings#screenshot-processing).

---

## Engineers Panel

The **Engineers** panel shows all ~36 engineers grouped by status:

- **Unlocked** — rank bar (1–5), rank-progress % toward next rank, specialty
- **In Progress** — current unlock stage (Known / Invited / Acquainted), progress bar
- **Locked / Unknown** — engineers not yet contacted

Data comes from the `EngineerProgress` journal event (fired automatically at game login). The specialty and home system columns use built-in static data.

---

## Statistics

The **Stats** panel (`Tab` to Stats, or automatic when offline) shows persistent statistics across all sessions:

| Stat | Description |
|------|-------------|
| Jumps | FSD / carrier jumps |
| Distance ly | Total jump distance (k = thousands ly, M = millions ly) |
| Credits + | Total credits earned |
| Credits − | Total credits spent |
| FSS Bodies | Bodies scanned via FSS |
| Undiscov. | Previously undiscovered bodies |
| Value | Total FSS value |
| DSS Bodies | Bodies mapped via DSS |
| Bio Scanned | Bio samples completed |
| 1st Ffall. | First footfall planets |
| Enemies | Ships destroyed |
| Ships Lost | Your ships lost |

Columns: **Today** / **Week** / **Month** / **Year** / **Total**

Numbers > 1,000 are abbreviated: `1.2k` = 1,200 · `3.4M` = 3,400,000 · `1.2B` = 1,200,000,000

---

## Offline Mode

When Elite Dangerous is not running, NOVA enters **offline mode** (dark grey borders). The Situational panel automatically shows the **Stats** page. All historical data from previous sessions is available.

---

## Twitch & YouTube Chat

If configured (see [Settings](Settings)), NOVA reads your stream chat and announces messages via TTS. Messages also appear in the **Chat log** panel (bottom right).

---

## Keybindings Backup

NOVA watches your Elite Dangerous `.binds` file in the background. Whenever it detects a change (e.g. after editing bindings in-game), it automatically creates a timestamped backup in `~/.config/nova/bindings_backup/` and logs a `SYS` event in the event log. The last 5 backups are kept. No setup required.

---

## Stream Overlay

NOVA writes a text file (`stream_info.txt` by default in your launch directory) with live game data. Add it as a **Text (GDI+)** / **Text** source in OBS or Streamlabs with "Read from file" enabled.

See the [Settings Guide](Settings#stream-overlay-obsstreamlabs) for available variables and format options.
