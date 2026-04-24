# NOVA UI Improvements — Batch 1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix route auto-switch, rework Route panel, fix body name display, unify scroll indicators, fix PgUp/PgDn focus behaviour, remove Stats border, rework Map panel, add Odyssey inventory, and research/apply performance improvements.

**Architecture:** All changes are in `ed_monitor/ui/panels.py`, `ed_monitor/ui/app.py`, `ed_monitor/journal.py`, and `ed_monitor/events.py`. No new files needed. Changes are logically independent and can be committed separately per task.

**Tech Stack:** Python 3.10+, Textual (TUI), Rich (rendering), httpx (EDSM), threading

---

## File Map

| File | What changes |
|------|-------------|
| `ed_monitor/ui/panels.py` | Tasks 1–7: auto-resolve, Route render, Bodies column, scroll indicators, Stats/Map/Inventory panels |
| `ed_monitor/ui/app.py` | Task 5: PgUp/PgDn for all focused panels; Task 7: up/down key for Map sub-view |
| `ed_monitor/journal.py` | Task 9: EDSM POST + batch 100 + User-Agent + 0.5s delay, watchdog |
| `ed_monitor/edsm.py` | Task 9: User-Agent header |
| `ed_monitor/status.py` | Task 9: watchdog integration, drop tick counter |
| `pyproject.toml` | Task 9: add required `watchdog>=3.0` dep |
| `ed_monitor/events.py` | Task 8: ShipLocker handler |
| `ed_monitor/state.py` | Task 8: `ship_locker` field |

---

## Task 1 — Route Panel: auto-switch when NavRoute is set

**Files:**
- Modify: `ed_monitor/ui/panels.py:3141-3172` (`_auto_resolve`)

**Context:** `_auto_resolve` already switches to `route` when `in_hyperspace and route_hops > 0` (line 3150). But it never switches to `route` when a route is merely *set* and no higher-priority mode is active. The CLAUDE.md documents that `route_hops > 0 → route` should be priority 8. That condition is missing from the code.

- [ ] **Step 1: Add `route_hops > 0` check to `_auto_resolve`**

In `panels.py` find `_auto_resolve` (line 3141). Add this block before `return "overview"` at the end:

```python
        # Route set — show route when no higher-priority context is active
        if s.route_hops > 0:
            return _v("route")
```

The full end of `_auto_resolve` becomes:

```python
        # Show missions when active (not in supercruise)
        if s.missions and not s.supercruise:
            return _v("missions")
        # Route set — show route when no higher-priority context is active
        if s.route_hops > 0:
            return _v("route")
        return "overview"
```

- [ ] **Step 2: Verify behaviour manually**

Run NOVA. Set a route in-game (or replay a NavRoute journal line). Confirm the Situational panel switches to ROU automatically.

- [ ] **Step 3: Commit**

```bash
git add ed_monitor/ui/panels.py
git commit -m "fix: auto-switch to Route panel when NavRoute is set"
```

---

## Task 2 — Route Panel: header, total ly, dynamic rows, remove Bio column

**Files:**
- Modify: `ed_monitor/ui/panels.py:3559-3711` (`_render_route`)
- Modify: `ed_monitor/ui/panels.py:3028-3048` (`SituationalPanel` class attributes — `_MAX_ROUTE_ROWS`)

**Context:**  
- Summary ("X jumps remaining → Dest") is at the **bottom** (lines 3701-3709). Move it to the **top** and add total distance `(yyyy ly)`.  
- `_MAX_ROUTE_ROWS = 20` is hardcoded (line 3625). Replace with dynamic calculation from panel height.  
- `Bio` column (line 3622) is unreliable; remove it.

- [ ] **Step 1: Move header to top + add total ly + remove Bio column**

Replace the entire `_render_route` function (lines 3559-3711) with the version below.  
Key changes:
1. Compute `total_ly` from `route_list` `StarPos` distances.
2. Render header text *before* the table.
3. Remove the `Bio` column from the table.
4. Replace `_MAX_ROUTE_ROWS` with `panel_height` parameter (default 40).

```python
def _render_route(s: AppState, scroll: int = 0, panel_height: int = 40) -> RenderableType:
    """Nav route panel: jump#, system, star class+scoopable, body count, dist, jump dist, EDSM."""
    import math as _math

    route = s.route_list
    if not route:
        t = Text()
        t.append("No nav route active.\n", style=P.LABEL)
        t.append("Set a route in-game to populate this view.", style="dim rgb(100,100,100)")
        return t

    edsm   = getattr(s, "route_list_edsm",   {})
    bodies = getattr(s, "route_bodies_edsm",  {})
    cur_pos = s.star_pos  # (x, y, z) or None

    _SCOOPABLE = frozenset("OBAFGKM")

    def _fmt_ly(d: float) -> str:
        if d <= 0:    return "—"
        if d >= 1000: return f"{d/1000:.1f}k"
        return f"{d:.1f}"

    def _star_col(sc: str) -> str:
        c = sc[:1] if sc else ""
        if c == "O": return "rgb(140,160,255)"
        if c == "B": return "rgb(180,210,255)"
        if c == "A": return "white"
        if c == "F": return "rgb(255,255,200)"
        if c == "G": return "rgb(255,230,120)"
        if c == "K": return "rgb(255,160,80)"
        if c == "M": return P.HUD_CRIT
        if c == "L": return "rgb(160,60,30)"
        if c in ("T", "Y"): return "rgb(100,80,60)"
        if c == "N": return "rgb(180,220,255)"
        if c == "H": return P.LABEL
        if sc.startswith("D"): return "rgb(200,230,255)"
        return P.LABEL

    # Skip current system (route[0]); display route[1:]
    display_route = route[1:]
    if not display_route:
        t = Text()
        t.append("Last jump — route complete.\n", style=P.LABEL)
        if s.route_destination:
            t.append(s.route_destination, style="white")
        return t

    # Compute total remaining distance (cur_pos → last waypoint)
    total_ly = 0.0
    if cur_pos:
        prev = cur_pos
        for entry in display_route:
            sp = entry.get("StarPos")
            if sp and isinstance(sp, list) and len(sp) >= 3:
                dx = sp[0] - prev[0]; dy = sp[1] - prev[1]; dz = sp[2] - prev[2]
                total_ly += _math.sqrt(dx*dx + dy*dy + dz*dz)
                prev = (sp[0], sp[1], sp[2])

    # ── Header ───────────────────────────────────────────────────────────────
    hops = s.route_hops
    word = "jump" if hops == 1 else "jumps"
    hdr = Text()
    hdr.append(f"  {hops} {word} remaining", style=P.AMBER)
    if total_ly > 0:
        hdr.append(f" ({_fmt_ly(total_ly)} ly)", style=P.LABEL)
    if s.route_destination:
        hdr.append(" → ", style=P.LABEL)
        hdr.append(s.route_destination, style="bold white")
    hdr.append("\n")

    parts: list[RenderableType] = [hdr]

    effective_scroll = min(scroll, max(0, len(display_route) - 1))
    if effective_scroll > 0:
        more_t = Text()
        more_t.append(f"  ▲ {effective_scroll} more above\n", style=P.LABEL)
        parts.append(more_t)

    tbl = Table(show_header=True, show_edge=False, box=None,
                padding=(0, 1), header_style=f"bold {P.LABEL}")
    tbl.add_column("#",      width=3,  justify="right",  no_wrap=True)
    tbl.add_column("System", width=18, no_wrap=True)
    tbl.add_column("★",      width=5,  no_wrap=True)
    tbl.add_column("Bd",     width=2,  justify="right",  no_wrap=True)
    tbl.add_column("Dist",   width=7,  justify="right",  no_wrap=True)
    tbl.add_column("Jump",   width=6,  justify="right",  no_wrap=True)
    tbl.add_column("✦",      width=1,  justify="center", no_wrap=True)

    # Dynamic rows: panel height minus header (1) + table header (1) + footer indicator (1) = 3
    max_rows = max(5, panel_height - 5)

    prev_pos = cur_pos
    visible  = display_route[effective_scroll:effective_scroll + max_rows]

    for i, entry in enumerate(visible, start=effective_scroll + 1):
        name       = entry.get("StarSystem", "?")
        pos_list   = entry.get("StarPos")
        star_class = entry.get("StarClass", "?")

        scoopable = star_class[:1] in _SCOOPABLE if star_class else False

        if cur_pos and pos_list:
            dx = pos_list[0] - cur_pos[0]
            dy = pos_list[1] - cur_pos[1]
            dz = pos_list[2] - cur_pos[2]
            dist_cur = _math.sqrt(dx*dx + dy*dy + dz*dz)
        else:
            dist_cur = 0.0

        if prev_pos and pos_list:
            dx = pos_list[0] - prev_pos[0]
            dy = pos_list[1] - prev_pos[1]
            dz = pos_list[2] - prev_pos[2]
            jump_d = _math.sqrt(dx*dx + dy*dy + dz*dz)
        else:
            jump_d = 0.0

        edsm_entry = edsm.get(name)
        if edsm_entry is None:
            edsm_text = Text("?", style=P.LABEL)
        elif edsm_entry.get("live_known") is False and not edsm_entry.get("x"):
            edsm_text = Text("✗", style=P.HUD_CRIT)
        else:
            edsm_text = Text("✓", style=P.HUD_GREEN)

        sc_short  = (star_class[:3] if star_class else "?").ljust(3)
        sc_col    = _star_col(star_class or "")
        star_cell = Text()
        star_cell.append(sc_short, style=sc_col)
        star_cell.append("⛽" if scoopable else " ·", style=P.HUD_GREEN if scoopable else "dim rgb(70,70,70)")

        population = (edsm_entry or {}).get("population", 0) or 0
        name_style = "rgb(255,235,180)" if population > 0 else "white"

        body_entry = bodies.get(name)
        if body_entry is None:
            bd_text = Text("…", style=P.LABEL)
        else:
            bd = body_entry.get("bodies", 0)
            bd_text = Text(str(bd) if bd else "·", style=P.WHITE if bd else "dim")

        tbl.add_row(
            Text(str(i), style=P.LABEL),
            Text(name[:18], style=name_style),
            star_cell,
            bd_text,
            Text(_fmt_ly(dist_cur), style=P.WHITE),
            Text(_fmt_ly(jump_d),   style=P.LABEL),
            edsm_text,
        )

        if pos_list:
            prev_pos = (pos_list[0], pos_list[1], pos_list[2])

    parts.append(tbl)

    remaining_below = len(display_route) - (effective_scroll + len(visible))
    if remaining_below > 0:
        more_b = Text()
        more_b.append(f"  ▼ {remaining_below} more below\n", style=P.LABEL)
        parts.append(more_b)

    return Group(*parts)
```

- [ ] **Step 2: Pass `panel_height` from SituationalPanel render**

In `SituationalPanel.render` (around line 3272), change:

```python
        if self._active == "route":
            return _render_route(s, scroll=self._route_scroll)
```

to:

```python
        if self._active == "route":
            return _render_route(s, scroll=self._route_scroll,
                                 panel_height=self.size.height)
```

- [ ] **Step 3: Verify route panel visually**

Run NOVA with a route active. Confirm:
1. Header "X jumps remaining (yyyy ly) → Dest" appears at the top.
2. Bio column is gone.
3. List extends further (more rows visible).

- [ ] **Step 4: Commit**

```bash
git add ed_monitor/ui/panels.py
git commit -m "feat: rework Route panel — header at top with total ly, dynamic rows, remove Bio column"
```

---

## Task 3 — Scanned Bodies: fix full system name display

**Files:**
- Modify: `ed_monitor/ui/panels.py:1104` (Body column definition in `BodiesPanel.render`)

**Context:** The `Body` column at line 1104 has `width=11` but no `no_wrap=True`. When a body's `_short_name` returns a long string (e.g. a body not starting with the system name prefix), Rich wraps it across multiple rows, making the system name appear in the cell. Fix: add `no_wrap=True`.

- [ ] **Step 1: Add `no_wrap=True` to Body column**

Change line 1104 from:
```python
        tbl.add_column("Body", style="white", width=11, header_style=HDR)
```
to:
```python
        tbl.add_column("Body", style="white", width=11, header_style=HDR, no_wrap=True)
```

- [ ] **Step 2: Verify no wrapping**

Run NOVA and observe the Scanned Bodies panel. Bodies with long names should be truncated at 11 chars, not wrapped.

- [ ] **Step 3: Commit**

```bash
git add ed_monitor/ui/panels.py
git commit -m "fix: prevent body name wrapping in Scanned Bodies panel"
```

---

## Task 4 — Unified scroll indicators in all panel borders

**Files:**
- Modify: `ed_monitor/ui/panels.py` — `BodiesPanel`, `SituationalPanel`, `EventLogPanel`, `ChatLogPanel`, all `_render_*` functions

**Context:** Currently:
- `BodiesPanel`: shows `▲{n}` in `border_title` only (no bottom indicator)
- All other panels: show inline text `▲ N more above` / `▼ N more below` inside the content
- `EventLogPanel` / `ChatLogPanel`: no indicators at all

**Uniform design — same for every scrollable panel:**
- `border_title` = `"◈ Panel Name  ▲{n}"` when n > 0, else `"◈ Panel Name"` (hidden when at top)
- `border_subtitle` = `f"▼{n}"` when n > 0, else `""` (hidden when nothing below)
- Format: `▲ N` / `▼ N` — no "more above/below" text anywhere

The `_render_*` functions cannot set widget properties — all indicator logic lives in `render()` / `update()` of each panel widget. The `_render_*` functions have all inline scroll text removed.

---

### 4a — BodiesPanel

**How to count:** `above = effective_scroll`. `below = max(0, total_bodies - effective_scroll - panel_height + 2)` using `self.size.height` for `panel_height` (subtract 2 for borders). When `self.size.height` is 0 (not yet mounted), fall back to `total_bodies - effective_scroll - 1`.

- [ ] **Step 1: Update BodiesPanel border indicators**

In `BodiesPanel.render()` (lines 1151-1158), replace the existing border title block with:

```python
        total_bodies = len(visible)
        effective_scroll = min(self._scroll, max(0, total_bodies - 1))

        above = effective_scroll
        panel_h = self.size.height or 0
        below = max(0, total_bodies - effective_scroll - max(1, panel_h - 2))

        self.border_title = (f"◈ Scanned Bodies  ▲{above}" if above > 0
                             else "◈ Scanned Bodies")
        self.border_subtitle = (f"▼{below}" if below > 0 else "")
```

- [ ] **Step 2: Verify BodiesPanel indicators**

Scroll down in Scanned Bodies. `▲{n}` appears in top border, `▼{n}` in bottom border. Both disappear when not needed.

---

### 4b — SituationalPanel

- [ ] **Step 3: Add `_update_scroll_indicators` to SituationalPanel**

Add this method just before `render()`:

```python
    def _update_scroll_indicators(self, s: AppState) -> None:
        """Update border_title / border_subtitle with ▲N / ▼N scroll indicators."""
        mode = self._active

        if mode == "route":
            route  = s.route_list or []
            total  = max(0, len(route) - 1)
            scroll = self._route_scroll
        elif mode == "bgs":
            total  = 9999
            scroll = self._bgs_scroll
        elif mode == "colonisation":
            total  = 9999
            scroll = self._colonisation_scroll
        elif mode == "neutron":
            total  = 9999
            scroll = self._neutron_scroll
        elif mode == "galaxy":
            # MAP mode: show sub-view indicator instead of scroll
            _subs = ("system", "regional", "galaxy")
            idx   = _subs.index(self._galaxy_submode) + 1 if self._galaxy_submode in _subs else 1
            self.border_title    = self._make_title()
            self.border_subtitle = f"{idx}/3"
            return
        else:
            total  = 9999
            scroll = self._general_scroll

        above = scroll
        panel_h = self.size.height or 0
        below = max(0, total - scroll - max(1, panel_h - 2)) if total < 9999 else (1 if scroll > 0 else 0)

        base = self._make_title()
        self.border_title    = f"{base}  ▲{above}" if above > 0 else base
        self.border_subtitle = f"▼{below}" if below > 0 else ""
```

- [ ] **Step 4: Call from `render()`**

At the start of `SituationalPanel.render()`, before the `if self._snap is None:` check:

```python
        if self._snap is not None:
            self._update_scroll_indicators(self._snap)
```

Also remove the MAP sub-view subtitle logic from `_update_scroll_indicators` in Task 7 since it is now consolidated here (it is already in the method above).

---

### 4c — EventLogPanel + ChatLogPanel

EventLogPanel shows events from `self._scroll` to the end of the list — so `above = self._scroll` (older events hidden), and `below` is events that overflow the panel height past the end of visible content.

- [ ] **Step 5: Add indicators to EventLogPanel.render()**

In `EventLogPanel.render()` (line ~3785), after computing `events` and before `return`:

```python
        above = self._scroll
        panel_h = self.size.height or 0
        below = max(0, len(events) - self._scroll - max(1, panel_h - 2))

        self.border_title    = (f"◈ Event Log  ▲{above}" if above > 0
                                else "◈ Event Log")
        self.border_subtitle = (f"▼{below}" if below > 0 else "")
```

- [ ] **Step 6: Add indicators to ChatLogPanel.render()**

Same pattern in `ChatLogPanel.render()`:

```python
        above = self._scroll
        panel_h = self.size.height or 0
        below = max(0, len(chats) - self._scroll - max(1, panel_h - 2))

        self.border_title    = (f"◈ Chat  ▲{above}" if above > 0 else "◈ Chat")
        self.border_subtitle = (f"▼{below}" if below > 0 else "")
```

---

### 4d — Remove all inline scroll text from `_render_*` functions

- [ ] **Step 7: Strip inline scroll text**

Find and remove every `▲ N more above` / `▼ N more below` inline block across:
- `_render_route` (already removed in Task 2 — skip)
- `_render_bio` (lines ~1330, ~1567)
- `_render_missions` (line ~1654)
- `_render_engineers` (line ~1775)
- `_render_inventory` (line ~1568)
- `_render_bgs`
- `_render_colonisation`
- `_render_neutron`

For each: delete the `if effective_scroll > 0: more_t = Text(); more_t.append("  ▲ ..."); parts.append(more_t)` block and equivalent `remaining_below` block at the bottom.

- [ ] **Step 8: Verify all panels**

Check BodiesPanel, SituationalPanel (Route/Bio/Missions/Engineers/Inventory/BGS), EventLogPanel, ChatLogPanel. All should show `▲N` in top border and `▼N` in bottom border, hidden when 0.

- [ ] **Step 9: Commit**

```bash
git add ed_monitor/ui/panels.py
git commit -m "feat: uniform ▲N/▼N scroll indicators in all panel borders"
```

---

## Task 5 — Tab/Shift+Tab: PgUp/PgDn for all focused panels (1–3)

**Files:**
- Modify: `ed_monitor/ui/panels.py` — add `_scroll` + `scroll_*` to `SystemPanel`, `ShipPanel`, `RoutePanel`
- Modify: `ed_monitor/ui/app.py:460-574` — `_scroll_focused`, `on_key` PgUp/PgDn

**Context:** Currently `_scroll_focused` only handles panels 4–6. Panels 1–3 (System, Ship, RoutePanel/target) can be focused via Tab but PgUp/PgDn falls through to SituationalPanel scrolling. We need:
1. Add `_scroll: int` + a scroll accessor to each of `SystemPanel`, `ShipPanel`, `RoutePanel`.
2. Pass the scroll offset into their render methods.
3. Update `_scroll_focused` to handle panels 1–3.
4. Arrow up/down still only scrolls SituationalPanel (no change).

---

### 5a — SystemPanel scrolling

- [ ] **Step 1: Add `_scroll` to SystemPanel**

In `SystemPanel` class (line ~300), add after `class SystemPanel(_Panel):`:

```python
    _scroll: int = 0

    def scroll_system(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()
```

In `SystemPanel.render()`, before `return`, add `_scroll` to the content rendering. Because SystemPanel renders a Rich `Text`/`Table` via `render()`, we need to capture the full text and return a paginated slice. The simplest approach: wrap the existing render output in a custom Text that skips the first `_scroll` lines.

Since Rich renderables can't be trivially sliced, the cleanest fix is to render to a string, split by lines, and return the visible portion. Add at end of `SystemPanel.render()`:

```python
    def render(self):
        if self._snap is None:
            return Text("")
        # ... existing render logic builds `content: RenderableType` ...
        # Wrap in scrollable Text by converting to lines
        # (existing render already returns a Rich object — keep as-is for now;
        #  scroll support for SystemPanel is low-priority since it rarely overflows)
        return content
```

> **Note:** SystemPanel and ShipPanel content is short and rarely needs scrolling. Implement minimal support: `scroll_system`/`scroll_ship` increment `_scroll` but the render ignores it for now (visual feedback only via border indicator). Full line-slice rendering can be added in a follow-up if needed.

- [ ] **Step 2: Add `scroll_ship` to ShipPanel and `scroll_route_panel` to RoutePanel**

Similarly add to `ShipPanel`:
```python
    _scroll: int = 0
    def scroll_ship(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()
```

And to `RoutePanel` (panels.py ~750):
```python
    _scroll: int = 0
    def scroll_route_panel(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()
```

- [ ] **Step 3: Update `_scroll_focused` in `app.py`**

Change `_scroll_focused` (app.py:460) to handle all 6 panels:

```python
    def _scroll_focused(self, delta: int) -> None:
        """Scroll up/down in the currently focused numbered panel."""
        n = self._focused_panel
        if n == 1:
            self.query_one(SystemPanel).scroll_system(delta)
        elif n == 2:
            self.query_one(ShipPanel).scroll_ship(delta)
        elif n == 3:
            self.query_one(RoutePanel).scroll_route_panel(delta)
        elif n == 4:
            self.query_one(BodiesPanel).scroll_bodies(delta)
        elif n == 5:
            self.query_one(EventLogPanel).scroll_log(delta)
        elif n == 6:
            self.query_one(ChatLogPanel).scroll_chat(delta)
```

- [ ] **Step 4: Update PgUp/PgDn conditions in `on_key`**

Change the condition from `if self._focused_panel in (4, 5, 6):` to `if self._focused_panel != 0:`:

```python
        elif key == "pagedown":
            if self._focused_panel != 0:
                self._scroll_focused(5)
            else:
                sit = self.query_one(SituationalPanel)
                # ... existing situational scroll ...

        elif key == "pageup":
            if self._focused_panel != 0:
                self._scroll_focused(-5)
            else:
                sit = self.query_one(SituationalPanel)
                # ... existing situational scroll ...
```

- [ ] **Step 5: Verify Tab → PgDn → PgUp works for panels 1–3**

Press `1`, then `PgDn` — it should call `scroll_system(5)` (no visible change yet but no crash). Press `Tab` to cycle through 1→2→3 and confirm PgUp/PgDn doesn't scroll the situational panel.

- [ ] **Step 6: Commit**

```bash
git add ed_monitor/ui/panels.py ed_monitor/ui/app.py
git commit -m "fix: PgUp/PgDn scrolls any focused panel, not just panels 4-6"
```

---

## Task 6 — Remove inner border from Statistics panel

**Files:**
- Modify: `ed_monitor/ui/panels.py:3355-3363` (`_render_stats`)

**Context:** `_render_stats` wraps its table in a `Panel(tbl, title="STATISTICS", ...)` (line 3360), adding an inner box border. All other situational panels use plain text/table headers with no inner `Panel`. Remove the `Panel` wrapper; replace with a plain text header line.

- [ ] **Step 1: Remove `Panel` wrapper from `_render_stats`**

Replace lines 3355-3363:
```python
    disclaimer = Text(
        "* Estimated payouts incl. bonuses. Unsold data is retained if killed.",
        style="rgb(70,70,70)",
    )
    return Group(
        Panel(tbl, title="STATISTICS", title_align="left",
              border_style=P.LABEL, padding=(0, 0), expand=True),
        disclaimer,
    )
```

with:
```python
    hdr = Text()
    hdr.append("STATISTICS\n", style=f"bold {P.AMBER}")

    disclaimer = Text(
        "* Estimated payouts incl. bonuses. Unsold data is retained if killed.",
        style="rgb(70,70,70)",
    )
    return Group(hdr, tbl, disclaimer)
```

Also remove the `from rich.panel import Panel` import *inside* `_render_stats` if it exists (check — it's imported at the top of the file already).

- [ ] **Step 2: Verify Statistics panel looks like other panels**

Switch to STS mode. Confirm no inner box, header "STATISTICS" styled like other panel headers (amber/gold).

- [ ] **Step 3: Commit**

```bash
git add ed_monitor/ui/panels.py
git commit -m "fix: remove inner border from Statistics panel for visual consistency"
```

---

## Task 7 — Map panel: remove border + arrow up/down sub-view cycling

**Files:**
- Modify: `ed_monitor/ui/panels.py:2723-2820` (`_render_galaxy`)
- Modify: `ed_monitor/ui/app.py:510-541` (`on_key` — left/right/up/down handling)
- Modify: `ed_monitor/ui/panels.py:3110-3115` (`toggle_galaxy_scale`)

**Context:**
1. Galaxy/regional map has an inner `Panel` border (`framed = Panel(canvas_text, ...)` line 2799). Remove it like Stats.
2. Currently `r` key cycles system→regional→galaxy. User wants **arrow up/down** to cycle (infinite loop). Arrow left/right currently cycle situational panel modes — keep that. When MAP mode is active, up/down should cycle sub-views instead of scrolling.
3. Show a sub-view indicator (e.g. "1/3") in the panel's border title area.

---

### 7a — Remove inner border from galaxy map

- [ ] **Step 1: Remove `Panel` wrapper from `_render_galaxy`**

Find lines ~2799-2800:
```python
    framed = Panel(canvas_text, title=title_str, title_align="center",
                   border_style=P.LABEL, padding=(0, 0), expand=True)
```

Replace with:
```python
    title_line = Text()
    title_line.append(f"  {title_str}\n", style=f"bold {P.LABEL}")
    framed = Group(title_line, canvas_text)
```

Also update references to `framed` below (line 2809: `parts: list[RenderableType] = [framed]` — stays the same).

- [ ] **Step 2: Verify galaxy map has no inner border**

Switch to MAP → regional → galaxy views. Confirm no inner border box around the canvas.

---

### 7b — Arrow up/down cycles MAP sub-views

- [ ] **Step 3: Update `on_key` in `app.py` to intercept up/down when MAP is active**

In `on_key`, find the `elif key in ("down", "j"):` block (line 517). Add a special case at the top:

```python
        elif key in ("down", "j"):
            sit = self.query_one(SituationalPanel)
            if sit._active == "galaxy":
                sit.toggle_galaxy_scale()   # forward = down
            elif sit._active == "neutron":
                sit.scroll_neutron(1)
            elif sit._active == "bgs":
                sit.scroll_bgs(1)
            elif sit._active == "colonisation":
                sit.scroll_colonisation(1)
            elif sit._active == "route":
                sit.scroll_route(1)
            else:
                sit.scroll_general(1)

        elif key in ("up", "k"):
            sit = self.query_one(SituationalPanel)
            if sit._active == "galaxy":
                sit.toggle_galaxy_scale_back()   # backward = up
            elif sit._active == "neutron":
                sit.scroll_neutron(-1)
            elif sit._active == "bgs":
                sit.scroll_bgs(-1)
            elif sit._active == "colonisation":
                sit.scroll_colonisation(-1)
            elif sit._active == "route":
                sit.scroll_route(-1)
            else:
                sit.scroll_general(-1)
```

- [ ] **Step 4: Add `toggle_galaxy_scale_back` to SituationalPanel**

In `SituationalPanel` (panels.py ~3110), add next to `toggle_galaxy_scale`:

```python
    def toggle_galaxy_scale_back(self) -> None:
        """Cycle MAP sub-screens backward: galaxy → regional → system."""
        _cycle = ("system", "regional", "galaxy")
        idx = _cycle.index(self._galaxy_submode) if self._galaxy_submode in _cycle else 0
        self._galaxy_submode = _cycle[(idx - 1) % len(_cycle)]
        self.refresh()
```

- [ ] **Step 5: Show sub-view indicator in border**

In `_update_scroll_indicators` (added in Task 4), add a MAP case:

```python
        if mode == "galaxy":
            sub   = self._galaxy_submode
            _subs = ("system", "regional", "galaxy")
            idx   = _subs.index(sub) + 1 if sub in _subs else 1
            self.border_subtitle = f"{idx}/3  "
            return   # no scroll indicators needed for MAP
```

- [ ] **Step 6: Update help screen text**

In `HelpScreen.compose()` (app.py ~66-80), update the `r` entry and `↑ / k` / `↓ / j` entries:

```python
("↑ / k",  "Scroll up (MAP mode: previous sub-view)"),
("↓ / j",  "Scroll down (MAP mode: next sub-view)"),
("r",       "Cycle Maps sub-screen (also ↑/↓ in MAP mode)"),
```

- [ ] **Step 7: Verify MAP sub-view cycling**

Switch to MAP mode. Press `↓` repeatedly: system → regional → galaxy → system (infinite loop). Press `↑`: same in reverse.

- [ ] **Step 8: Commit**

```bash
git add ed_monitor/ui/panels.py ed_monitor/ui/app.py
git commit -m "feat: Map panel — remove inner border, cycle sub-views with arrow up/down (infinite)"
```

---

## Task 8 — Inventory: add Odyssey materials (backpack + ship locker)

**Files:**
- Modify: `ed_monitor/state.py` — add `ship_locker: dict` field
- Modify: `ed_monitor/events.py` — handle `ShipLocker` event
- Modify: `ed_monitor/ui/panels.py:1544-1616` (`_render_inventory`)

**Context:** `state.backpack` already holds Odyssey on-foot items (Items, Components, Consumables, Data). `ShipLocker` event (same structure) holds the ship-stored Odyssey items. Neither is currently shown in the Inventory panel. Add a new section "ODYSSEY" (separated visually) after the existing Horizons materials.

`ShipLocker` journal event structure:
```json
{ "event": "ShipLocker", "Items": [...], "Components": [...], "Consumables": [...], "Data": [...] }
```
Each item: `{ "Name": "...", "Name_Localised": "...", "OwnerID": ..., "MissionID": ..., "Count": ... }`

---

### 8a — State + events

- [ ] **Step 1: Add `ship_locker` to AppState**

In `state.py`, after `backpack`:
```python
    ship_locker: dict = field(default_factory=dict)   # from ShipLocker event
```

- [ ] **Step 2: Handle `ShipLocker` in events.py**

In `events.py`, after the `case "Backpack":` block (line ~2115), add:

```python
        case "ShipLocker":
            state.ship_locker = {
                "items":       ev.get("Items")       or [],
                "components":  ev.get("Components")  or [],
                "consumables": ev.get("Consumables") or [],
                "data":        ev.get("Data")        or [],
            }
            return None
```

---

### 8b — Render in Inventory panel

- [ ] **Step 3: Add Odyssey section to `_render_inventory`**

After the existing `_flush_tbl()` call at the end of `_render_inventory` (line 1614), before `return Group(*parts)`, add:

```python
    # ── Odyssey materials (backpack + ship locker) ──────────────────────────
    def _ody_section(label: str, items: list) -> None:
        """Render one Odyssey category (Items / Components / Consumables / Data)."""
        if not items:
            return
        parts.append(Text("\n"))
        parts.append(_section_header(label))
        ody_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        ody_tbl.add_column("name",  style="rgb(200,220,255)")   # blue-tinted = Odyssey
        ody_tbl.add_column("count", justify="right")
        for item in sorted(items, key=lambda x: (x.get("Name_Localised") or x.get("Name", "")).lower()):
            name  = item.get("Name_Localised") or item.get("Name", "?")
            count = item.get("Count", 0)
            cnt_col = P.HUD_WARN if count >= 100 else ("white" if count >= 30 else P.LABEL)
            ody_tbl.add_row(name, Text(str(count), style=f"bold {cnt_col}"))
        parts.append(ody_tbl)

    # Odyssey divider header
    has_backpack = any(state.backpack.get(k) for k in ("items", "components", "consumables", "data"))
    has_locker   = any(state.ship_locker.get(k) for k in ("items", "components", "consumables", "data"))
    if has_backpack or has_locker:
        parts.append(Text("\n"))
        div = Text()
        div.append("── ODYSSEY ──────────────────────\n", style=f"bold {P.AMBER}")
        parts.append(div)

    if has_backpack:
        bp = state.backpack
        _ody_section("BACKPACK — Items",       bp.get("items", []))
        _ody_section("BACKPACK — Components",  bp.get("components", []))
        _ody_section("BACKPACK — Consumables", bp.get("consumables", []))
        _ody_section("BACKPACK — Data",        bp.get("data", []))

    if has_locker:
        lk = state.ship_locker
        _ody_section("LOCKER — Items",       lk.get("items", []))
        _ody_section("LOCKER — Components",  lk.get("components", []))
        _ody_section("LOCKER — Consumables", lk.get("consumables", []))
        _ody_section("LOCKER — Data",        lk.get("data", []))
```

Note: `state` is passed as `s` in `_render_inventory`. Rename `state` references above to `s`.

- [ ] **Step 4: Verify Odyssey section appears**

Launch NOVA with an Odyssey game session. Switch to INV mode. Confirm "── ODYSSEY ──" divider and sub-sections appear after the regular Horizons materials. Items should be blue-tinted to distinguish from regular white Horizons materials.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/state.py ed_monitor/events.py ed_monitor/ui/panels.py
git commit -m "feat: add Odyssey materials (backpack + ship locker) to Inventory panel"
```

---

## Task 9 — Performance: EDSM rate limit + file watching research

**Files:**
- Modify: `ed_monitor/journal.py:308` (`_fetch_route_bodies_live`)
- Modify: `ed_monitor/journal.py:222-223` (`_fetch_route_edsm_live`)
- Research/document: journal and status.json polling

### 9a — EDSM API improvements

**Findings (comparing Gemini's recommendations against the existing code):**

`_fetch_route_edsm_live` (existence check):
- **Already batched** using `api-v1/systems` with `systemName[]` — good.
- **Gap 1:** Uses `client.get()` — URL length risk for long routes. Switch to POST.
- **Gap 2:** Batch size is 50; EDSM supports up to 100 per request. Increase.
- **Gap 3:** No `User-Agent` header — EDSM asks tools to identify themselves.
- **Gap 4:** 1.0s sleep between batches — with 100 systems/batch, two batches covers 200 systems; reduce to 0.5s.

`_fetch_route_bodies_live` (body/bio counts):
- **No batch endpoint exists** for `api-system-v1/bodies` — must stay per-system.
- **Gap:** 1.0s delay per system; reduce to 0.5s.
- **Gap:** No `User-Agent` header.

`edsm.py` (current system body fetch):
- **Gap:** No `User-Agent` header.

**User-Agent value:** `nova-ed-monitor/{version} (Elite Dangerous companion; github.com/KernicDE/nova-ed-monitor)`

**Files:**
- Modify: `ed_monitor/journal.py:191-223` (`_fetch_route_edsm_live`) — POST, batch 100, User-Agent, 0.5s delay
- Modify: `ed_monitor/journal.py:277-309` (`_fetch_route_bodies_live`) — 0.5s delay, User-Agent
- Modify: `ed_monitor/edsm.py:28` (`_run`) — User-Agent on httpx client

- [ ] **Step 1: Update `_fetch_route_edsm_live` — POST, batch 100, User-Agent, 0.5s**

Replace lines 191-223 inside `_fetch_route_edsm_live`:

```python
        # Batch query EDSM — up to 100 names per POST request
        _EDSM_BATCH = 100
        _EDSM_URL   = "https://www.edsm.net/api-v1/systems"
        _UA         = f"nova-ed-monitor (Elite Dangerous companion; github.com/KernicDE/nova-ed-monitor)"
        now_str     = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        new_cache_entries: list[dict] = []

        try:
            client = httpx.Client(timeout=15.0, headers={"User-Agent": _UA})
            for i in range(0, len(to_fetch), _EDSM_BATCH):
                batch  = to_fetch[i:i + _EDSM_BATCH]
                params = [("systemName[]", n) for n in batch]
                params.append(("showId", "1"))
                try:
                    resp  = client.post(_EDSM_URL, data=dict_from_pairs(params))
                    resp.raise_for_status()
                    found = {s["name"] for s in resp.json() if isinstance(s, dict) and "name" in s}
                except Exception:
                    found = set()

                for name in batch:
                    known = name in found
                    new_cache_entries.append({
                        "name": name, "known": int(known),
                        "scoopable": -1, "cached_at": now_str,
                    })

                updates = {n: {"live_known": n in found} for n in batch}
                with lock:
                    state.route_list_edsm = {**state.route_list_edsm, **updates}

                if i + _EDSM_BATCH < len(to_fetch):
                    _time.sleep(0.5)  # 100 systems/batch: 0.5s is polite

            client.close()
        except Exception:
            pass
```

Note: `systemName[]` as repeated keys can't use `dict()` directly — httpx's `post(data=...)` accepts a list of tuples for repeated keys. Change `data=dict_from_pairs(params)` to just `data=params` (httpx accepts `list[tuple]` for `data`):

```python
                    resp  = client.post(_EDSM_URL, data=params)
```

- [ ] **Step 2: Update `_fetch_route_bodies_live` — 0.5s delay, User-Agent**

Change line 278 and 308-309:
```python
            client = httpx.Client(timeout=15.0, headers={"User-Agent": _UA})
```
(add `_UA` constant same as above), and:
```python
                if i < len(to_fetch) - 1:
                    _time.sleep(0.5)  # EDSM bodies: 0.5s between per-system requests
```

- [ ] **Step 3: Add User-Agent to `edsm.py`**

In `edsm.py` line 28, change:
```python
    client = httpx.Client(timeout=15.0)
```
to:
```python
    _UA = "nova-ed-monitor (Elite Dangerous companion; github.com/KernicDE/nova-ed-monitor)"
    client = httpx.Client(timeout=15.0, headers={"User-Agent": _UA})
```

- [ ] **Step 4: Verify no EDSM 429 errors in logs**

Run NOVA with a long route (100+ systems). Check logs (`nova.journal`) for HTTP 429 or "Network error" from either fetch function. If 429 appears on bodies fetch, increase delay to 0.75s.

### 9b — Event-driven file watching with watchdog (required dependency)

**Problem with current polling:**  
`_follow()` calls `fd.read(65536)` + `time.sleep(0.2)` **5 times per second, forever** — even when docked in a station for 30 minutes. `status.py` does the same with `os.stat()`. Each cycle = kernel syscalls + context switches, zero value when nothing is changing. With `inotify`/`watchdog`, threads **park in the kernel** between events — truly 0 CPU until the OS notifies of a change.

**Why required (not optional):**  
`watchdog` is small (~100KB), well-maintained (used by Django dev server, pytest-watch, mkdocs), and all users benefit automatically. No two-path complexity. If the observer fails at *runtime* (e.g. network FS, Proton quirk), we catch the exception and fall back to polling — but the import always succeeds.

**What one watchdog observer covers:**  
Both `journal.py` and `status.py` watch the *same* journal directory. Each module creates its own observer (watchdog supports multiple observers per directory; on Linux they share the same kernel inotify fd). This keeps the modules independent with no shared state.

Files watched per module:
- `journal.py` observer: journal `.log` files (new lines, file rotation)
- `status.py` observer: `Status.json`, `Cargo.json`, `Materials.json` — all in same dir

**Status.json: bio-distance still gets 0.2s tick:**  
`status.py` line 86 only calls `_check_bio_distance` when `_on_surface and _has_active`. So the wait timeout is `0.2` in that case, `5.0` otherwise. Result: on surface with active bio scan → wakes every 0.2s same as today; all other states → sleeps until a file actually changes.

**Backends per platform:**
- Linux (game via Proton): `InotifyObserver` — kernel inotify, 0 CPU between events
- macOS: `FSEventsObserver` — kernel FSEvents
- Windows: `ReadDirectoryChangesW`

---

**Files:**
- Modify: `pyproject.toml` — add `watchdog>=3.0` to required deps
- Modify: `ed_monitor/journal.py` — module-level event + `_start_watchdog()` + replace sleeps
- Modify: `ed_monitor/status.py` — same pattern, timeout varies on bio-surface state

- [ ] **Step 3: Add watchdog to required dependencies in `pyproject.toml`**

```toml
dependencies = [
    "textual>=0.80.0",
    "httpx>=0.27.0",
    "edge-tts>=7.0.0",
    "pygame>=2.5.0",
    "Pillow>=10.0",
    "watchdog>=3.0",
]
```

- [ ] **Step 4: Add event + `_start_watchdog` to `journal.py`**

After the existing module-level locks (lines 55-56), add:

```python
# Wakes _follow() and monitor() when a journal .log file in the directory changes.
_journal_dir_changed: threading.Event = threading.Event()
_watchdog_active: bool = False


def _start_watchdog(journal_dir: Path) -> None:
    global _watchdog_active
    from watchdog.observers import Observer           # type: ignore[import]
    from watchdog.events import FileSystemEventHandler  # type: ignore[import]

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event) -> None:         # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(".log"):
                _journal_dir_changed.set()
        def on_created(self, event) -> None:          # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(".log"):
                _journal_dir_changed.set()

    try:
        obs = Observer()
        obs.schedule(_Handler(), str(journal_dir), recursive=False)
        obs.daemon = True
        obs.start()
        _watchdog_active = True
        _log.info("Journal watching: inotify/watchdog active (zero-CPU idle)")
    except Exception as exc:
        _log.warning(f"Journal watching: watchdog failed ({exc}) — falling back to polling")
```

- [ ] **Step 5: Call `_start_watchdog` once in `monitor()`**

At the top of `monitor()` (line ~407), before the `while True:` loop:

```python
    _start_watchdog(journal_dir)
```

- [ ] **Step 6: Replace `time.sleep(0.2)` in `_follow()` with event wait**

In `_follow()`, replace line 730:
```python
                time.sleep(0.2)
```
with:
```python
                if _watchdog_active:
                    _journal_dir_changed.wait(timeout=5.0)
                    _journal_dir_changed.clear()
                else:
                    time.sleep(0.2)
```

5s timeout = safety net. In practice fires in <1ms on Linux/Windows when a line is appended.

- [ ] **Step 7: Replace `time.sleep(2.0)` in `monitor()` outer loop**

```python
            if _watchdog_active:
                _journal_dir_changed.wait(timeout=10.0)
                _journal_dir_changed.clear()
            else:
                time.sleep(2.0)
```

### 9c — status.py: event-driven watching

**Files:**
- Modify: `ed_monitor/status.py` — event + `_start_watchdog_status()` + replace `time.sleep(0.2)`

- [ ] **Step 8: Add event + `_start_watchdog_status` to `status.py`**

After the imports and before `monitor()`, add:

```python
_status_dir_changed: threading.Event = threading.Event()
_status_watchdog_active: bool = False

_STATUS_FILES = frozenset({"Status.json", "Cargo.json", "Materials.json"})


def _start_watchdog_status(journal_dir: Path) -> None:
    global _status_watchdog_active
    from watchdog.observers import Observer           # type: ignore[import]
    from watchdog.events import FileSystemEventHandler  # type: ignore[import]

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event) -> None:         # type: ignore[override]
            if not event.is_directory and os.path.basename(event.src_path) in _STATUS_FILES:
                _status_dir_changed.set()
        def on_created(self, event) -> None:          # type: ignore[override]
            if not event.is_directory and os.path.basename(event.src_path) in _STATUS_FILES:
                _status_dir_changed.set()

    try:
        obs = Observer()
        obs.schedule(_Handler(), str(journal_dir), recursive=False)
        obs.daemon = True
        obs.start()
        _status_watchdog_active = True
        _log.info("Status watching: inotify/watchdog active (zero-CPU idle)")
    except Exception as exc:
        _log.warning(f"Status watching: watchdog failed ({exc}) — falling back to polling")
```

- [ ] **Step 9: Call `_start_watchdog_status` in `status.monitor()`**

At the top of `monitor()` (line ~51), before `while True:`:

```python
    _start_watchdog_status(journal_dir)
```

Also move the `_on_surface` / `_has_active` state into the outer loop scope so the timeout can reference it. Introduce two tracking variables before `while True:`:

```python
    _on_surface_cache: bool = False
    _has_active_cache: bool = False
```

Update them after the mtime check block (after the try/except, before the sleep):

```python
        with lock:
            _on_surface_cache = (state.landed or state.in_srv or
                                  (not state.in_main_ship and not state.in_srv))
            _has_active_cache = any(
                not sc.complete and sc.samples > 0
                for sc in state.bio_scans
            )
```

- [ ] **Step 10: Replace `time.sleep(0.2)` in `status.py` with event wait**

Replace line 134:
```python
        time.sleep(0.2)
```
with:
```python
        if _status_watchdog_active:
            need_fast = _on_surface_cache and _has_active_cache
            _status_dir_changed.wait(timeout=0.2 if need_fast else 5.0)
            _status_dir_changed.clear()
        else:
            time.sleep(0.2)
```

Also remove the `tick` counter and the `if tick % 10 == 0:` guard (lines 115-129). With watchdog waking on Cargo.json / Materials.json changes directly, we can check them on every wakeup — the mtime guard ensures no re-read unless changed:

```python
        # Check cargo and materials on every wakeup (mtime-gated, no re-read unless changed)
        try:
            mtime = os.stat(cargo_path).st_mtime
            if mtime != last_cargo:
                last_cargo = mtime
                _apply_cargo(cargo_path, state, lock)
        except OSError:
            pass
        try:
            mtime = os.stat(mats_path).st_mtime
            if mtime != last_mats:
                last_mats = mtime
                _apply_materials(mats_path, state, lock)
        except OSError:
            pass
```

This also means Cargo/Materials changes are detected immediately (on the wakeup triggered by the file change) rather than with up to 2s lag.

- [ ] **Step 11: Verify status monitoring still works**

Run NOVA. Dock at a station — buy cargo — confirm Cargo panel updates immediately. Go on foot with bio scan active — confirm bio distance updates at ~0.2s. Check logs for `"Status watching: inotify/watchdog active"`.

- [ ] **Step 12: Commit all performance changes**

```bash
git add pyproject.toml ed_monitor/journal.py ed_monitor/status.py
git commit -m "perf: watchdog for zero-CPU idle in journal + status watching; faster Cargo/Materials detection"
```

Then:

```bash
git add ed_monitor/journal.py
git commit -m "perf: reduce EDSM bodies fetch delay from 1.0s to 0.5s"
```

---

## Self-Review Checklist

- [x] **Task 1** — Route auto-switch: adds missing `route_hops > 0` → route condition ✓
- [x] **Task 2** — Route panel header: moves summary to top, adds ly total, removes Bio, dynamic rows ✓
- [x] **Task 3** — Body name display: adds `no_wrap=True` to Body column ✓
- [x] **Task 4** — Scroll indicators: moves from inline content to border_title/border_subtitle ✓
- [x] **Task 5** — Focus + PgUp/PgDn: all 6 panels covered, up/down still → situational only ✓
- [x] **Task 6** — Stats border: removes `Panel` wrapper, adds text header ✓
- [x] **Task 7** — Map: removes inner Panel, up/down cycles sub-views, shows 1/3 indicator ✓
- [x] **Task 8** — Odyssey inventory: `ShipLocker` event, backpack display, blue-tinted section ✓
- [x] **Task 9** — Performance: existence check → POST + 100/batch; bodies 0.5s delay; User-Agent on all EDSM clients; watchdog for zero-CPU idle in journal + status ✓

**Spec gaps found:**
- Task 4 scroll indicator "right corner": Textual `border_title` is left-aligned by default and `border_subtitle` is also left-aligned. To push to the right, append padding spaces or use `border_subtitle` alignment. Marked as approximate — exact right-alignment in Textual borders requires CSS or padding tricks. `border_subtitle` itself displays bottom-center. This is a known Textual limitation; the indicators will appear in the border but may not be pixel-perfect right-aligned.
- Task 5 note: SystemPanel and ShipPanel content is short (rarely > 30 lines). The `scroll_*` methods are wired up for correctness but actual content slicing is deferred. PgUp/PgDn won't visibly scroll them until render logic is extended — but they also won't crash or redirect to SituationalPanel.
