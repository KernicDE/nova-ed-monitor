# Feature Plan — Issues #11, #12, #13, #15, #16

---

## #16 — High G body warning (smallest scope, good first)

**Goal:** TTS warn when approaching a body >1.5g; flash red + 3× warn for extreme G (>3g).

### Data already available
- `BodyInfo.surface_gravity` (float, m/s²) — set from `Scan` event in `events.py:905`
- `state.approach_body` (str) — set by `ApproachBody` event in `events.py:682`
- `state.bodies` (dict[str, BodyInfo]) — indexed by body name

### New state fields (state.py `AppState`)
```python
high_g_alerted: bool = False   # reset on LeaveBody / SupercruiseEntry
```

### events.py changes
In the `ApproachBody` handler (currently line 682), after setting `state.approach_body`:
```python
body = state.bodies.get(_s(ev, "Body"))
if body and body.surface_gravity:
    g = body.surface_gravity / 9.81   # convert to g
    state.high_g_alerted = False       # reset on each new approach
    if g >= 3.0:
        _say(tts_q, "HighGExtreme", True, fallback=f"Warning! Extreme gravity: {g:.1f} G.")
        # schedule 2 more repeats via threading.Timer (10s, 20s)
        for delay in (10, 20):
            threading.Timer(delay, lambda: tts_q.put((True, pick("HighGExtreme", ...) or ...))).start()
    elif g >= 1.5:
        _say(tts_q, "HighGWarning", True, fallback=f"Caution: {g:.1f} G body.")
    state.high_g_alerted = True
```

On `LeaveBody` and `SupercruiseEntry`: `state.high_g_alerted = False`

### UI flash (app.py / panels.py)
- Add `high_g_extreme: bool` to `AppState`
- When extreme G approach is active, `NOVAApp._snapshot()` triggers `app.add_class("high-g-mode")`
- CSS: `Screen.high-g-mode { background: $error 15%; }` (same pattern as `combat-mode`)
- Clear on `LeaveBody`/`SupercruiseEntry` (set `high_g_extreme = False`)
- Stop flashing when `state.landed = True` or `state.in_srv = True` (on ground)

### Voicelines (en.toml)
```toml
[HighGWarning]
variants = [
    "Caution: {g} G body ahead.",
    "High gravity warning: {g} G.",
]
[HighGExtreme]
variants = [
    "Extreme gravity alert! {g} G — approach with caution.",
    "Warning! Gravity exceeds safe threshold: {g} G.",
]
```

### New config option (config.py)
```toml
high_g_threshold = 1.5        # warn above this value in G
high_g_extreme_threshold = 3.0  # flash + 3x warning above this
```

---

## #15 — ED screenshot processing

**Goal:** Watch ED screenshot folder; convert BMP → PNG; rename to timestamp+CMDR+system+body; move to `~/Pictures/Elite Dangerous/`; delete originals from ED folder.

### New file: `ed_monitor/screenshots.py`
Daemon thread (`nova-screenshots`). Polls ED screenshot folder every 2 s (same pattern as status.py polling).

```python
def screenshot_thread(state, lock, cfg):
    # Determine source dir: cfg.screenshot_dir or auto-detect
    # Auto-detect: ~/Pictures/Frontier Developments/Elite Dangerous/
    #              or Windows equivalent via journal path heuristics
    # Dest dir: cfg.screenshot_dest or ~/Pictures/Elite Dangerous/
    while True:
        _scan_for_new_screenshots(state, lock, cfg)
        time.sleep(2)
```

Screenshot processing per file:
1. Detect new files not already processed (track by inode/mtime in SQLite `screenshots` table)
2. Open with Pillow (new dependency) — ED on Linux/Proton saves BMP; newer ED saves PNG
3. Build filename: `{YYYY-MM-DD-HH-MM}_{CMDR}_{SYSTEM}_{BODY}.png`
   - Use `state.commander`, `state.system`, `state.approach_body or state.nearest_body`
   - Sanitize: replace spaces with `-`, strip special chars
4. Save as PNG to dest dir (create if absent)
5. Delete original from ED screenshot folder

### `Screenshot` journal event
ED also fires a `Screenshot` event with `Filename`, `Width`, `Height` — hook this in `events.py` to trigger immediate processing instead of waiting for the polling interval. Pass target filename via a queue to the screenshot thread.

### New state fields
None needed — uses `state.commander`, `state.system`, `state.nearest_body` already.

### New config keys (config.py)
```toml
screenshot_dir  = ""    # ED screenshot folder; leave empty to auto-detect
screenshot_dest = ""    # destination folder; default: ~/Pictures/Elite Dangerous
```

### New dependency
`Pillow>=10.0` added to `pyproject.toml`. Pillow has prebuilt wheels for all major platforms including Python 3.14.

### DB table (db.py)
```sql
CREATE TABLE IF NOT EXISTS screenshots (
    path TEXT PRIMARY KEY,
    processed_at TEXT
);
```
Prevents reprocessing on restart.

---

## #13 — Neutron route plotter

**Goal:** User inputs a target system; NOVA plots a neutron-boosted route via Spansh, factoring in active ship's jump range.

### Spansh API endpoint
`GET https://www.spansh.co.uk/api/route` with params:
- `from`: current system name
- `to`: target system name  
- `range`: ship's jump range in ly (unladen)
- `efficiency`: 60 (default; configurable)

Response: `{"result": {"system_jumps": [...], "total_jumps": N}}`

### Jump range source
`state.jump_range` — new AppState field (float, ly). Populated from:
- `FSDJump` event: `state.jump_range = _f(ev, "JumpDist")` — this is the actual jump made, not max range
- Better: `Loadout` event has `MaxJumpRange` — use that
- Fallback: prompt user to enter manually in the plotter UI

### New file: `ed_monitor/neutron.py`
Daemon thread (`nova-neutron`). Receives `("plot", target_system)` messages via queue.
- Calls Spansh API with timeout 15s
- Writes result to `state.neutron_route` (list of system names + jump type)
- Caches per `(from_system, to_system, jump_range)` key, 5 min TTL

### UI changes
New `SituationalPanel` mode: `"neutron"` — added to `_MODES` tuple.

**Neutron panel layout:**
- Top: text input for target system (Textual `Input` widget)
- "Plot route" button → sends to neutron thread queue
- Result table: jump number | system | type (boost / normal / arrival)
- Footer shows: `N jumps | X ly total | estimated Y minutes`

**Tab cycle addition:**
`_MODES = ("auto", "overview", "inventory", "bio", "missions", "engineers", "neutron", "galaxy", "stats")`

### New state fields (state.py)
```python
jump_range:          float = 0.0   # from Loadout event
neutron_route:       list  = []    # list of dicts from Spansh result
neutron_route_from:  str   = ""
neutron_route_to:    str   = ""
```

### New config key
```toml
neutron_efficiency = 60   # Spansh route efficiency 0–100
```

---

## #12 — Enhance Engineers

**Goal:** Let user select an engineer; show finished/active/following missions with progress.

### Journal events to track (already partially in events.py)
- `EngineerProgress` — fires on load; `State` = "Unlocked"/"Invited"/"Known"/"Unknown", rank + progress
- `EngineerContribution` — materials/credits contributed toward unlock
- `EngineerCraft` — a craft was applied (counts toward progress)

### New state structure (state.py)
```python
@dataclass
class EngineerInfo:
    name:        str
    system:      str
    state:       str   # "Unlocked", "Invited", "Known", "Unknown"
    rank:        int   = 0
    rank_progress: float = 0.0   # 0–100%
    # Missions (from EngineerProgress nested array):
    missions_finished: list[dict] = field(default_factory=list)
    missions_active:   list[dict] = field(default_factory=list)
    missions_pending:  list[dict] = field(default_factory=list)

# Replace current `engineers: dict` with:
engineers: dict[str, EngineerInfo] = field(default_factory=dict)
```

### Known engineer data (static lookup)
Hardcode dict of engineer name → system + specialty in a new `ed_monitor/engineers_data.py` (or inline in panels.py). ~32 engineers total.

### events.py changes
Expand `EngineerProgress` handler to populate the new `EngineerInfo` structure including missions array from `Missions` key in the event.

### UI changes (panels.py `EngineersPanel`)
Current engineers panel shows a simple rank table. New layout:

**Left column:** scrollable list of all engineers with status indicator (locked/invited/unlocked + rank stars). Click/keyboard to select.

**Right column (for selected engineer):**
- Name, system, specialty
- Rank bar (filled segments 1–5)
- Missions section:
  - Finished: green checkmark list
  - Active: with required material/count and current progress bar
  - Following: what must be done to unlock next mission

This is the most stateful UI change — but purely display-side, no new threads needed.

---

## #11 — Wallet and inventory (largest scope)

**Goal:** New SituationalPanel mode showing credit balance + fleet summary + current cargo/materials/suit loadout.

### New SituationalPanel mode: `"wealth"`
Added to `_MODES`. Replaces/extends the existing `"inventory"` mode (or merges into it — decide at implementation time).

### Data sources

**Credits (balance):**
- `LoadGame` event has `Credits` field — not currently read. Add: `state.credits = _i(ev, "Credits")`
- `Statistics` event has `Credits` and `Assets` in `Bank_Account` block
- Update on: `MissionCompleted`, `MarketSell`, `MarketBuy`, `SellExplorationData`, etc.

**Ships across the galaxy:**
- `StoredShips` journal event (fires after visiting shipyard): list of ships with `StarSystem`, `StationName`, `ShipType`, `Name`
- Store as `state.stored_ships: list[dict]`

**Current ship inventory:**
- `state.cargo: list` — already populated from Cargo.json (status.py)
- `state.materials_raw/mfg/enc` — already populated

**Suit loadout:**
- `SuitLoadout` journal event: suit name, modules, weapons
- Store as `state.suit_loadout: dict`

**Backpack (on-foot inventory):**
- `BackpackChange` / `Backpack` journal events

### New state fields (state.py)
```python
credits:        int   = 0
stored_ships:   list  = []   # from StoredShips event
suit_loadout:   dict  = {}   # from SuitLoadout event
backpack:       dict  = {}   # from Backpack/BackpackChange
```

### Panel layout (panels.py `WealthPanel` or expanded `InventoryPanel`)
```
┌─ WEALTH ──────────────────────────────┐
│  Balance: 1,234,567,890 Cr             │
│  Assets:  2,100,000,000 Cr (est.)      │
├─ FLEET ────────────────────────────────│
│  Krait MkII "The Void Dancer"   [HERE] │
│  Anaconda "Deep Runner"  Shinrarta     │
│  Python "Hauler"         Jameson       │
├─ CARGO (12/64t) ───────────────────────│
│  Tritium ×32  Void Opals ×8  ...       │
├─ MATERIALS ────────────────────────────│
│  Raw: 47 items   Mfg: 23   Enc: 18     │
├─ SUIT / BACKPACK ──────────────────────│
│  Maverick Suit G5 | Energylink G4      │
└────────────────────────────────────────┘
```

### Implementation order
1. Add `state.credits`, `state.stored_ships`, `state.suit_loadout`, `state.backpack` to `AppState`
2. Populate from journal events in `events.py`
3. Build `WealthPanel` widget (new class in panels.py, or expand existing `InventoryPanel`)
4. Add `"wealth"` to `_MODES` (replace `"inventory"` or keep both — `"inventory"` currently shows materials)
5. Hook into `_snapshot()` in app.py

---

## Suggested implementation order

| Priority | Issue | Why first |
|---|---|---|
| 1 | #16 High G warning | Self-contained, minimal scope, no new deps |
| 2 | #15 Screenshot processing | New thread + Pillow dep, but no UI changes |
| 3 | #12 Engineers enhance | State + UI only, no new threads |
| 4 | #11 Wallet/inventory | Most events to wire up, largest UI |
| 5 | #13 Neutron plotter | New API thread + interactive UI input widget |
