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
┌─ System ─────────┬─ Ship ──────────────────────┬─ Route ────┐
│ System/faction   │ Hull/Shield/Fuel gauges     │ Nav route  │
├──────────────────┴─────────────────────────────┴────────────┤
│ Scanned Bodies   │ Overview / Bio / Missions /  │ Events     │
│ (FSS, DSS,       │ Inventory / Engineers /      ├────────────┤
│  values, dist)   │ Galaxy / Stats               │ Chat log   │
├──────────────────┴──────────────────────────────┴────────────┤
│ Keybindings                                     Vol 50% ●   │
└───────────────────────────────────────────────────────────────┘
```

**Mode indicators** (border colour):
- White/grey — Normal flight
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
| `Tab` | Cycle situational panel mode |
| `r` | Toggle galaxy map scale (galactic ↔ regional ±1000 ly) |
| `↑` / `k` | Scroll event log up |
| `↓` / `j` | Scroll event log down |
| `PgUp` / `PgDn` | Scroll event log by 20 lines |
| `Home` / `g` | Jump to latest events |
| `+` / `=` | Volume up (+5%) |
| `−` | Volume down (−5%) |

---

## Situational Panel (centre)

Press `Tab` to cycle through modes. In **Auto** mode NOVA switches automatically:

| Mode | Auto? | Description |
|------|-------|-------------|
| **Auto** | — | Bio → Missions → Overview; Stats when offline |
| Overview | ✓ | System diagram, notable bodies, session totals |
| Bio | ✓ | Active bio scans — distances, bearings, sample counts |
| Missions | ✓ | Active mission list |
| Inventory | — | Cargo hold and materials |
| Engineers | — | Engineer unlock progress |
| Galaxy | — | Braille top-down galaxy map (`r` to toggle scale) |
| Stats | ✓ (offline) | Persistent statistics by today / week / month / year / total |

---

## Bodies Panel (left)

Shows all scanned bodies in the current system.

| Column | Meaning |
|--------|---------|
| Body | Short name — indented moons shown as ↳ child |
| Type | Abbreviated body type |
| Val | Scan value (gold if >1M Cr); `~3.4M–12.9M` estimate in amber before full scan |
| Dist | Distance from arrival (ls) |
| B | Bio signal count; `3✓` in gold when all scans complete |
| G | Geological signal count |
| LTA | `L`=Landable `T`=Terraformable `A`=Atmosphere |
| F | `●` = FSS scanned |
| D | `●` = DSS mapped |

**`★`** next to a species name = first discovered in the galaxy.

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

## Stream Overlay

NOVA writes a text file (`stream_info.txt` by default in your launch directory) with live game data. Add it as a **Text (GDI+)** / **Text** source in OBS or Streamlabs with "Read from file" enabled.

See the [Settings Guide](Settings#stream-overlay-obsstreamlabs) for available variables and format options.
