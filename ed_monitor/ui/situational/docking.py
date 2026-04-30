from __future__ import annotations

import math
import queue
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ...state import AppState, BodyInfo, EngineerInfo, EventCategory, LogEvent
from .. import palette as P
from ... import events
from ...events import _BIO_GENUS_VALUE_RANGE, _BIO_SPECIES_VALUES, bio_variant
from ...config import Config
from ..panels import (
    _data_table, _section_header, _kv_row, _kv_line, _two_column_table,
    _short_name, _natural_key,
    _body_color, _abbrev_type, _body_value, _body_value_color,
    _fmt_cr_compact, _fmt_value, _fmt_ls_compact, _fmt_metres,
    _fmt_notable_val, _de,
)


def _render_docking(s: AppState, panel_w: int = 60, panel_h: int = 24) -> RenderableType:
    """Docking pad circular diagram — front view of the station.

    Mailslot is at the centre; rings go outward from front to back.
    Only the assigned landing pad is shown readable; other pads are hidden.
    Ring layout (Coriolis/Orbis):
      Inner  (1–12):  large pads, nearest to mailslot
      Mid-1  (13–24): large pads
      Mid-2  (25–36): medium pads
      Outer  (37–40): small pads, back wall
    """
    import math as _math

    pad = s.docked_pad
    stn = s.docked_station_name or s.station or "Unknown Station"
    stype = s.docked_station_type or s.station_type or ""

    _KNOWN_PAD_DIAGRAMS = frozenset({
        "Coriolis", "Orbis", "Ocellus",
    })

    parts: list[RenderableType] = []

    # ── Header ───────────────────────────────────────────────────────────────
    _mp = P.mp(s.ui_mode)
    parts.append(_section_header("DOCKING", _mp["h1"], _mp["bg"]))
    head = Text()
    if stype:
        head.append(f"{stype}\n", style=P.LABEL)
    if pad > 0:
        head.append("Pad ", style=P.LABEL)
        head.append(f"{pad}\n", style="bold rgb(0,255,150)")
    if head:
        parts.append(head)

    if stype and stype not in _KNOWN_PAD_DIAGRAMS:
        fallback = Text()
        fallback.append(
            f"  Pad diagram not available for {stype}.\n", style=P.LABEL
        )
        parts.append(fallback)
        return Group(*parts)

    # ── Circular grid diagram ────────────────────────────────────────────────
    # Scale to fill available space (2× to 2.5× relative to original 38×13)
    header_lines = 2 + (1 if stype else 0) + (1 if pad > 0 else 0)
    avail_h = max(13, panel_h - header_lines - 2)  # reserve 2 for hint + margin
    avail_w = max(38, panel_w)
    scale = min(avail_w / 38, avail_h / 13)
    scale = max(scale, 2.0)
    scale = min(scale, 2.5)

    base_w, base_h = 38, 13
    W = int(base_w * scale)
    H = int(base_h * scale)
    if W % 2 == 0:
        W -= 1
    if H % 2 == 0:
        H -= 1
    cx, cy = W // 2, H // 2

    BLANK = (" ", "")
    grid: list[list[tuple]] = [[BLANK] * W for _ in range(H)]

    def place(gx: int, gy: int, label: str, style: str) -> None:
        sx = gx - len(label) // 2
        for j, ch in enumerate(label):
            x = sx + j
            if 0 <= gy < H and 0 <= x < W:
                grid[gy][x] = (ch, style)

    # Ring geometry: (rx, ry, start_pad, count)
    # Evenly-spaced circular rings (rx ≈ 2×ry for round shape in monospace).
    # Reversed: inner ring = nearest to mailslot, outer = furthest.
    base_rings = [(4, 2, 1, 12), (6, 3, 13, 12), (8, 4, 25, 12), (10, 5, 37, 4)]
    ring_defs = [
        (max(3, int(rx * scale)), max(2, int(ry * scale)), start, count)
        for rx, ry, start, count in base_rings
    ]

    # Determine active ring and hint
    active_idx = -1
    hint_text = ""
    for idx, (_, _, start, count) in enumerate(ring_defs):
        if start <= pad < start + count:
            active_idx = idx
            break
    if active_idx == 0:
        hint_text = "Front ring (large pad) — nearest mailslot"
    elif active_idx == 1:
        hint_text = "Mid-front ring (large pad)"
    elif active_idx == 2:
        hint_text = "Mid-rear ring (medium pad)"
    elif active_idx == 3:
        hint_text = "Rear ring (small pad) — back wall"

    # Draw concentric ring outlines — active ring bright, others dim
    for idx, (rx, ry, _, _) in enumerate(ring_defs):
        steps = max(rx, ry) * 6
        dot_style = "rgb(150,150,150)" if idx == active_idx else P.DIM
        for i in range(steps):
            angle = _math.pi + i * 2 * _math.pi / steps
            gx = int(round(cx + rx * _math.sin(angle)))
            gy = int(round(cy - ry * _math.cos(angle)))
            if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] == BLANK:
                grid[gy][gx] = ("·", dot_style)

    # Place only the assigned pad on the active ring
    if active_idx >= 0:
        rx, ry, start, count = ring_defs[active_idx]
        i = pad - start
        angle = _math.pi + i * 2 * _math.pi / count
        gx = int(round(cx + rx * _math.sin(angle)))
        gy = int(round(cy - ry * _math.cos(angle)))
        place(gx, gy, f"[{pad}]", "bold white")

    # Mailslot in the centre with red/green nav lights beside it
    place(cx - 2, cy, "●", "bold rgb(255,60,60)")   # red  — port / left
    place(cx,     cy, "▼", "bold white")             # mailslot
    place(cx + 2, cy, "●", "bold rgb(0,255,100)")   # green — starboard / right

    # Build diagram Text and centre horizontally within the panel
    diag = Text()
    h_pad = max(0, (panel_w - W) // 2)
    for row in grid:
        if h_pad:
            diag.append(" " * h_pad)
        for ch, sty in row:
            diag.append(ch, style=sty) if sty else diag.append(ch)
        diag.append("\n")
    parts.append(diag)

    # Centre vertically: add blank lines above if there's extra room
    v_pad = max(0, panel_h - header_lines - H - (1 if hint_text else 0))
    if v_pad > 1:
        top_pad = v_pad // 2
        parts.insert(1, Text("\n" * top_pad))

    hint = Text()
    if hint_text:
        hint.append(f"{hint_text}\n", style=P.LABEL)
    parts.append(hint)

    return Group(*parts)


