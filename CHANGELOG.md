# Changelog

## v2.14.1 — 2026-05-07

### Bug Fixes

- **#120 Fix wording in docking computer**
  - Coriolis, Orbis, and Ocellus station hints now use **Front / Back** terminology instead of inner / outer rings
  - All cylindrical station types are now consistent with the spatial layout relative to the mailslot

- **#121 Slow refresh rate of position in orbital cruise**
  - Status monitor now **slow-polls (5 s) in deep space** when no lat/lon/alt data is present
  - Fast-poll (0.2 s) preserved for: landed, SRV, on-foot, orbital cruise, and near-surface flight
  - Reduces unnecessary CPU load when exact positions aren't needed

---

## v2.14.0 — 2026-05-07

### Enhancements

- **#122 Material Tracker** — Complete grade-based material inventory in the Assets panel
  - Shows all 120 materials (Raw G1–G4, Manufactured/Encoded G1–G5) even at zero count
  - Compact tables with grade labels, count/cap, ASCII progress bars, and percentage
  - Colour-coded stock levels: dim grey (empty) → white → amber (near cap) → green (well stocked)

- **#123 Fuel Warning** — Configurable low-fuel threshold (default 25%, set to 0 to disable)
  - TTS warning + event log entry when main tank drops below threshold
  - Auto-resets on refuel; never repeats until refuelled

- **#124 Home System** — Set your home system in Settings or `config.toml`
  - Arrival triggers a "Welcome home, Commander." voiceline

- **#125 Panel Toggles in Settings** — Show, hide, and reorder situational panels directly in the Settings overlay (`s` key)
  - Enter a number to activate and position a panel (lowest = leftmost)
  - Leave the field empty to hide a panel
  - Gaps in numbering are allowed

### Other

- Added voiceline keys across all 7 languages: `LowFuel`, `FSDJump_Home`
- 339 tests passing

---

## v2.13.1 — 2026-05-07

### Bug Fixes

- **#119** Fleet carrier bay diagram and asteroid base ring view
- **#118** Mission panel: destination grouping, kill stacking, type badges, reward column
- **#120** AsteroidBase docking hints changed from "Inner / Outer" to "Front / Back"
- **#121** Status.json fast-polling for ship/orbital-cruise/SRV near surfaces

---

## v2.13.0 — 2026-05-02

### Breaking Changes

- Refactored to pure portable mode — migration helpers removed

### Fixes

- Coriolis pad placement, docking diagram height, notable why width, route arrival TTS
- Windows: UTF-8 BOM in `nova.ps1`
- Carrier bay pad contrast
- Help screen scrollable with arrow keys, close with ESC

---

## v2.12.4 — 2026-05-01

### Fixes

- UI style guide refinements

---

## v2.12.3 — 2026-05-01

### Fixes

- Mode-aware palette and ship status bar improvements

---

## v2.12.2 — 2026-05-01

### Fixes

- WEP (hardpoints) and Night Vision added to ship status bar

---

## v2.12.1 — 2026-05-01

### Fixes

- Cargo bar removed from Ship panel to fit 2-row button bar
- Uniform green/grey color for all non-mode status buttons

---

## v2.12.0 — 2026-05-01

### Features

- UI style guide and palette system

---

## v2.11.0 — 2026-05-01

### Features

- Initial release with situational panel system
