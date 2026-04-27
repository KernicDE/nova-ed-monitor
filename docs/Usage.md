# Usage Guide

## Starting NOVA

| Platform | Command |
|----------|---------|
| Linux | `./nova.sh` (from the folder containing the script) |
| Windows | Right-click `nova.ps1` → **Run with PowerShell** |
| Standalone binary | `./nova-linux-x86_64` |

NOVA automatically finds your Elite Dangerous journal files and starts monitoring. Launch it before or after starting the game — it will catch up. On startup, NOVA replays your most recent journal files to rebuild per-system body data, so you see the current state of the galaxy immediately without having to re-scan.

---

## Interface Overview

```
┌─ Position ────────┬─ Ship ─────────────────────┬─ Target ───┐
│ System/faction    │ Hull/Shield/Fuel gauges     │ Nearby /   │
│ Body on approach  │                             │ targeted   │
├───────────────────┴─────────────────────────────┴────────────┤
│ Scanned Bodies    │ Overview / Wealth / Bio /    │ Events     │
│ (FSS, DSS,        │ Missions / Engineers /       ├────────────┤
│  values, dist)    │ Neutron / Galaxy / Stats     │ Chat log   │
├───────────────────┴──────────────────────────────┴────────────┤
│ q s Tab ? ↑↓ +/-                                Vol 50% ●   │
└────────────────────────────────────────────────────────────────┘
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
| `s` | Open Settings overlay |
| `?` | Help & About screen |
| `Tab` | Cycle focused panel forward (1→6) |
| `Shift+Tab` | Cycle focused panel backward (6→1) |
| `a` | Toggle auto panel switching on/off |
| `↑` / `k` | Scroll situational panel up (MAP mode: previous sub-view) |
| `↓` / `j` | Scroll situational panel down (MAP mode: next sub-view) |
| `PgUp` / `PgDn` | Scroll focused panel by 5 (or situational panel when none focused) |
| `Home` / `End` | Jump to top / bottom of focused panel |
| `s` | Open settings overlay |
| `r` | Cycle Maps sub-screen forward (system → regional → galaxy) |
| `n` | Open neutron route destination input (Neutron mode only) |
| `m` | Mute / unmute all TTS |
| `Enter` | Engineers: open detail / return to list |
| `g` | Toggle in-game chat TTS |
| `t` | Toggle Twitch chat TTS |
| `y` | Toggle YouTube chat TTS |
| `p` | Toggle all chat TTS at once |
| `+` / `=` | Volume up (+5%) |
| `−` | Volume down (−5%) |

---

## Settings Overlay

Press **`s`** from anywhere in NOVA to open the Settings overlay.

- Navigate rows with **↑/↓**
- Change toggles and selectors with **←/→**
- Edit text fields with **Enter** (confirm with Enter, cancel with Esc)
- Press **SAVE** to write all changes and apply them immediately
- Press **ESC** to close without saving

Voice selection is hierarchical: language → locale → voice name (powered by the edge-tts voice catalog). All changes take effect immediately without restarting NOVA.

---

## Situational Panel (centre)

Press `Tab` / `Shift+Tab` to cycle through modes. Press `a` to lock/unlock auto-switching.

| Mode | Abbrev | Auto? | Description |
|------|--------|-------|-------------|
| **Auto** | `***` | — | Switches by context; `a` to toggle lock |
| Overview | `OVR` | ✓ | Dashboard: session stats · credits/cargo/missions · route + galactic position · notable bodies (capped to fit) · BGS / PowerPlay / nearest inhabited / fleet carrier / neutron route (when space permits) |
| Biological | `BIO` | ✓ | Active bio scans — distances, bearings, sample counts |
| Maps | `MAP` | — | System diagram → regional map → galaxy map (`r` or `↑`/`↓` to cycle) |
| Missions | `MIS` | ✓ | Active missions and massacre kill progress bars |
| Engineers | `ENG` | — | Rank bars, rank-progress %, specialty and system per engineer |
| BGS | `BGS` | — | Per-faction BGS activity counts for the current system (today's tick) |
| Colonisation | `COL` | ✓ | Construction site commodity progress |
| Route | `ROU` | ✓ | Nav route: jumps remaining + total ly → destination at top; star class, scoopable, distances, EDSM body counts; auto-activates when a route is set |
| Neutron | `NTR` | — | Neutron route planner — press `n` to enter destination |
| Wallet | `WLT` | — | Balance · fleet · cargo · suit loadout + weapons · backpack |
| Inventory | `INV` | — | Cargo · raw / manufactured / encoded materials |
| Docking | `DKG` | ✓ | Station pad diagram — concentric rings with mailslot at centre; only assigned pad shown, active ring highlighted |
| Statistics | `STS` | ✓ (offline) | Persistent stats: today / week / month / year / total |

**Auto-switch priority (highest first):** offline → Stats · hyperspace with route → Route · docking granted → Docking · incomplete bio scans or DSS'd bio body → Bio · colonisation active in system → Colonisation · missions (not in supercruise) → Missions · route set → Route · default → Overview.

---

## Position Panel (top left)

Shows current system info in a two-column layout: natural/exploration data on the left, human/BGS data on the right.

| Left column | Right column |
|-------------|--------------|
| Bodies (stars/planets/moons) | Economy |
| FSS scan progress (stars always count as done) | Security |
| Power Play affiliation | Government / Allegiance |
| | Controlling faction |
| | Station count |

**Body details on approach:** when your ship approaches a known body, a body section appears below the system table showing type, gravity (red ≥3 G / yellow ≥1.5 G), radius, surface temperature, atmosphere, bio/geo signal counts, volcanism, and terraform flag.

A position footer shows when on or near a surface:
`At <body>     Pos <lat, lon>     Alt <altitude m>`

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
| Val | **FSS'd, unmapped:** maximum projected DSS payout (efficiency bonus assumed) — **gold** if first-discovery+mapping, **amber** if first-mapping, white otherwise. **DSS'd:** actual mapped value. **Not FSS'd:** `~estimate` in amber. |
| Dist | Distance from arrival (ls) |
| B | Bio signal count; `3✓` in gold when all scans complete |
| G | Geological signal count |
| LTA | `L`=Landable `T`=Terraformable `A`=Atmosphere |
| F | `●` = FSS scanned (stars always count as done) |
| D | `●` = DSS mapped |

Values always use the Frontier formula (EDSM values are ignored). The displayed value is the maximum possible payout assuming efficiency bonus — when you actually achieve it, the final value matches.

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

Repeat warnings and the flash **cancel instantly** on any of: landing, entering supercruise, starting another approach, an FSD jump, or a game shutdown. The warnings never fire against a body you've already left.

---

## Wealth Panel

The **Wealth** panel shows your financial and inventory overview across all locations:

- **Balance** — current credit total, tracked from login, market transactions, missions, and exploration sales
- **Fleet** — current ship plus all stored ships with their station and system
- **Cargo** — items currently in your ship's cargo hold
- **Materials** — count of raw / manufactured / encoded materials
- **Suit Loadout** — equipped suit and weapons (when on foot)
- **Backpack** — item counts while on foot
- **Odyssey materials** — detailed per-item listing of backpack contents (Items / Components / Consumables / Data) and ship locker contents, shown in blue; populated from the `ShipLocker` and `Backpack` journal events

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

The **Engineers** panel shows all 38 engineers in a single sorted list. Each row is numbered and shows `[H]` (Horizons) or `[O]` (Odyssey) prefix, name, rank pips, specialty, and system in separate columns.

**Rank pip colour:**
- Green filled dots — Unlocked (1–5 for Horizons, `●` for Odyssey)
- Amber partial bar — In Progress (with percentage)
- Amber empty dots `○○○○○` — Known / Invited / Acquainted (no progress yet)
- Dim grey `·····` — Unknown (not yet contacted)

Rows have alternating backgrounds (like the Scanned Bodies panel) for easy reading.

**Sort order:** Horizons before Odyssey; within each: Unlocked → In Progress → Known / Unknown; then by rank (highest first), then by name.

Data comes from the `EngineerProgress` journal event (fired automatically at game login). Engineers not yet in the journal appear at the bottom with grey dots.

**Interactive controls:**

| Key | Action |
|-----|--------|
| `↑` / `↓` or `k` / `j` | Move cursor between engineers |
| `Enter` | Open detail view (unlock condition + full module list) or return to list |

The detail view shows the unlock requirement, leveling hint, and every module/grade this engineer handles.

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
