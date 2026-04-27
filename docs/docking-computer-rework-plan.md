# Docking Computer (DKG) Rework Plan

> Issue #113 — Fix mirroring, add mailslot orientation, and explore better visualisations.

---

## 1. Immediate Fixes (already applied)

### 1.1 Mirroring / orientation
The old diagram placed **pad 1 at 12 o'clock** (top). In-game, pad 1 is the bottom-centre pad closest to the access corridor (mailslot). The diagram has been rotated 180° so that:
- **Angle 0 = bottom** (6 o'clock, front / mailslot side).
- Numbers increase **clockwise** around the rings, matching the actual station layout.

### 1.2 Mailslot & navigation lights
A small indicator row has been added at the bottom of the ASCII diagram:
- **Red dot ●** on the left  → port side (keep clear when entering).
- **▼** in the centre        → mailslot / access corridor.
- **Green dot ●** on the right → starboard side (safe entry side).

This matches the in-game rule: *enter with green on your right*.

---

## 2. Concepts for Further Improvements

### 2.1 Unrolled-cylinder (map) view
The current ring view is a top-down cross-section of a cylinder. It works, but pads that are actually in straight lines ("rows") appear on ellipses.

**Concept A — Flat map view**
Unroll the inner wall into a rectangle:
- **X-axis**: angle around the station (0° = bottom centre, increasing clockwise).
- **Y-axis**: depth from the mailslot (front = bottom, back = top).

Each "line" of pads becomes a vertical column. This makes it trivial to see:
- Which pads are near the front (easy to spot after entry).
- Which pads are on the same "row" as your assigned pad.

ASCII mock-up (compressed):
```
        BACK WALL
  9  21  33   39   34  22  10
  8  20  32   37   35  23  11
  7  19  31   38   36  24  12
  ●───●───●─[▼]─●───●───●
  6  18  30   25   26  13   1
  5  17  29        27  14   2
  4  16  28        28  15   3
        MAILSLOT
```
*(Numbers are illustrative; actual counts vary by ring.)*

### 2.2 Station-type-aware layouts
Currently the same ring diagram is shown regardless of `StationType`. The journal provides this type, so we could branch:

| StationType | Layout idea |
|-------------|-------------|
| `Coriolis` / `Orbis` / `Ocellus` | Ring or unrolled map (as above). |
| `Outpost` | Flat 2×2 or cross layout — outposts have only 4–5 exposed pads arranged in a T or cross. |
| `MegaShip` | Linear row — mega-ships have pads in a straight line along the hull. |
| `FleetCarrier` | Simple 8-pad circle or 2×4 grid. |
| `PlanetaryPort` / `CraterOutpost` | Flat grid — these are surface bases with a regular grid layout. |

**Implementation sketch:**
```python
if stype in ("Coriolis", "Orbis", "Ocellus"):
    return _render_docking_coriolis(s)
elif stype == "Outpost":
    return _render_docking_outpost(s)
elif "Carrier" in stype:
    return _render_docking_carrier(s)
...
```

### 2.3 3D-ish perspective
Instead of a pure top-down view, a **slight perspective** (dimetric) could show depth:
- Pads near the back wall drawn higher up and slightly smaller/dimmer.
- Pads near the mailslot drawn lower and brighter.
- This gives an intuitive "fly-in" feeling without true 3D math.

### 2.4 Rotational-correction hint
Add a small arrow or spin indicator:
- Coriolis / Orbis spin **counter-clockwise** when viewed from the outside front.
- Show a `⟲` or `⟳` next to the mailslot indicator so pilots know which way to rotate to match the station.

### 2.5 Pad-size colour coding
Use different colours or shapes per pad size:
- Large pads: `██`
- Medium pads: `▪▪`
- Small pads: `··`
This helps pilots quickly judge which ring their pad is on.

---

## 3. Recommended Next Steps

1. **Gather reference data** — dump `StationType` values from the journal for Outposts, Mega Ships, Fleet Carriers, and Planetary Ports to confirm exact strings.
2. **Prototype the unrolled map** for Coriolis/Orbis. It is arguably more useful than the ring view because depth (distance from mailslot) is explicit.
3. **Implement Outpost layout** next — it is the most common non-Coriolis docking scenario and has a very simple geometry.
4. **Add rotational arrow** once the base layout is stable.
5. **Keep the ASCII constraint** — the TUI is pure text, so all visuals must work in a monospace grid. Avoid complex Unicode box-drawing unless it degrades gracefully.

---

## 4. Files Involved

- `ed_monitor/ui/panels.py` — `_render_docking()` and future station-type branches.
- `ed_monitor/events.py` — `DockingGranted` already captures `StationType` and `LandingPad`.
- `ed_monitor/state.py` — `docked_station_type`, `docked_pad`.
