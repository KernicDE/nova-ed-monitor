from __future__ import annotations

import math as _math

from rich.console import Group, RenderableType
from rich.text import Text

from ...state import AppState
from .. import palette as P
from ..panels import _section_header


# ── Fleet Carrier bay layout (Drake-class) ────────────────────────────────────
#
# Physical layout (front of carrier = top, cockpit = bottom):
#
#         FRONT (bay entrance)
#         7L  8L
# 13S 16S  5L  6L 14S 15S
#     10M  3L  4L 12M
#      9M  1L  2L 11M
#         COCKPIT
#
# 8 Large + 4 Medium + 4 Small = 16 pads total.
# Each row in _CARRIER_GRID: list of (pad_number, size) or None for empty space.

_CARRIER_GRID: list[list[tuple[int, str] | None]] = [
    [None,      None,      (7,  "L"), (8,  "L"), None,      None     ],  # row 0: front
    [(13, "S"), (16, "S"), (5,  "L"), (6,  "L"), (14, "S"), (15, "S")],  # row 1: mid
    [None,      (10, "M"), (3,  "L"), (4,  "L"), (12, "M"), None     ],  # row 2: rear
    [None,      (9,  "M"), (1,  "L"), (2,  "L"), (11, "M"), None     ],  # row 3: cockpit
]

# Reverse lookup: pad_number → (row_index, size)
_CARRIER_PAD_INFO: dict[int, tuple[int, str]] = {}
for _r, _row in enumerate(_CARRIER_GRID):
    for _cell in _row:
        if _cell is not None:
            _p, _s = _cell
            _CARRIER_PAD_INFO[_p] = (_r, _s)

_CARRIER_ROW_NAMES: dict[int, str] = {
    0: "Front bay",
    1: "Mid bay",
    2: "Rear bay",
    3: "Cockpit row",
}
_CARRIER_SIZE_NAMES: dict[str, str] = {
    "L": "large pad",
    "M": "medium pad",
    "S": "small pad — outer wing",
}
# Colour for unassigned pads by size (assigned pad is always bold white)
_CARRIER_SIZE_STYLE: dict[str, str] = {
    "L": P.LABEL_LIGHT,
    "M": P.AMBER,
    "S": P.LABEL_DIM,
}


def _draw_carrier_bay(pad: int, panel_w: int) -> tuple[RenderableType, str]:
    """Rectangular bay diagram for Drake-class fleet carriers.

    FRONT header (green ▲) at the top, COCKPIT footer (amber ═) at the bottom.
    Assigned pad shown as [NN] in bold white; others dimmed and colour-coded by size.
    """
    CELL = 4          # chars per cell: "[16]" or " 16 "
    COLS = 6
    W    = CELL * COLS  # 24

    h_pad = " " * max(0, (panel_w - W) // 2)
    lines: list[RenderableType] = []

    # ── FRONT header — green ▲ marks, open-bay feel ───────────────────────────
    front_label = "▲  FRONT  ▲"
    fl_left  = (W - len(front_label)) // 2
    fl_right = W - len(front_label) - fl_left
    t = Text()
    t.append(h_pad + " " * fl_left)
    t.append(front_label, style="bold rgb(60,210,100)")
    t.append(" " * fl_right + "\n")
    lines.append(t)

    # ── Pad rows ──────────────────────────────────────────────────────────────
    for row in _CARRIER_GRID:
        t = Text()
        t.append(h_pad)
        for cell in row:
            if cell is None:
                t.append("    ")               # empty slot — 4 spaces
            else:
                p_num, size = cell
                lbl = f"{p_num:2}"
                if p_num == pad:
                    t.append(f"[{lbl}]", style="bold white")
                else:
                    t.append(f" {lbl} ", style=_CARRIER_SIZE_STYLE[size])
        t.append("\n")
        lines.append(t)

    # ── COCKPIT footer — heavy ═ bar, sealed-wall feel ────────────────────────
    inner = " COCKPIT "
    bar_w = (W - len(inner)) // 2
    bar_r = W - bar_w - len(inner)
    t = Text()
    t.append(h_pad)
    t.append("═" * bar_w,       style=P.AMBER)
    t.append(inner,              style=f"bold {P.AMBER}")
    t.append("═" * bar_r + "\n", style=P.AMBER)
    lines.append(t)

    # ── Hint ──────────────────────────────────────────────────────────────────
    hint = ""
    if pad in _CARRIER_PAD_INFO:
        row_i, size = _CARRIER_PAD_INFO[pad]
        hint = f"{_CARRIER_ROW_NAMES[row_i]} — {_CARRIER_SIZE_NAMES[size]}"

    return Group(*lines), hint


# ── Main renderer ─────────────────────────────────────────────────────────────

def _render_docking(s: AppState, panel_w: int = 60, panel_h: int = 24) -> RenderableType:
    """Docking pad diagram — front view of the station.

    Coriolis / Orbis / Ocellus:
        Circular ring diagram (mailslot centre, 4 concentric rings, 40 pads).
        Inner  (1–12):  large pads, nearest mailslot.
        Mid-1  (13–24): large pads.
        Mid-2  (25–36): medium pads.
        Outer  (37–40): small pads, back wall.

    AsteroidBase:
        2-ring circular diagram (cave interior, no mailslot).
        Inner  (1–4):   large pads.
        Outer  (5–8):   small pads.

    FleetCarrier (Drake-class):
        Rectangular bay grid, FRONT at top, COCKPIT at bottom.
        See _CARRIER_GRID above for the full pad layout.
    """
    pad   = s.docked_pad
    stn   = s.docked_station_name or s.station or "Unknown Station"
    stype = s.docked_station_type or s.station_type or ""

    _CIRCULAR_TYPES = frozenset({"Coriolis", "Orbis", "Ocellus", "AsteroidBase"})
    _ALL_KNOWN      = _CIRCULAR_TYPES | {"FleetCarrier"}

    parts: list[RenderableType] = []

    # ── Header ────────────────────────────────────────────────────────────────
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

    if stype not in _ALL_KNOWN:
        fallback = Text()
        fallback.append(f"  Pad diagram not available for {stype}.\n", style=P.LABEL)
        parts.append(fallback)
        return Group(*parts)

    # ── Fleet Carrier ─────────────────────────────────────────────────────────
    if stype == "FleetCarrier":
        diag, hint_text = _draw_carrier_bay(pad, panel_w)
        parts.append(diag)
        if hint_text:
            parts.append(Text(f"{hint_text}\n", style=P.LABEL))
        return Group(*parts)

    # ── Circular diagram (Coriolis / Orbis / Ocellus / AsteroidBase) ──────────
    header_lines = 2 + (1 if stype else 0) + (1 if pad > 0 else 0)
    avail_h = max(13, panel_h - header_lines - 2)
    avail_w = max(38, panel_w)
    scale   = min(avail_w / 38, avail_h / 13)
    scale   = max(scale, 2.0)
    scale   = min(scale, 2.5)

    base_w, base_h = 38, 13
    W = int(base_w * scale)
    H = int(base_h * scale)
    if W % 2 == 0: W -= 1
    if H % 2 == 0: H -= 1
    cx, cy = W // 2, H // 2

    BLANK = (" ", "")
    grid: list[list[tuple]] = [[BLANK] * W for _ in range(H)]

    def place(gx: int, gy: int, label: str, style: str) -> None:
        sx = gx - len(label) // 2
        for j, ch in enumerate(label):
            x = sx + j
            if 0 <= gy < H and 0 <= x < W:
                grid[gy][x] = (ch, style)

    # Ring geometry differs by type
    if stype == "AsteroidBase":
        # 2 rings: 4 large (inner) + 4 small (outer)
        base_rings = [(4, 2, 1, 4), (7, 3, 5, 4)]
    else:
        # Coriolis / Orbis / Ocellus: 4 rings, 40 pads total
        base_rings = [(4, 2, 1, 12), (6, 3, 13, 12), (8, 4, 25, 12), (10, 5, 37, 4)]

    ring_defs = [
        (max(3, int(rx * scale)), max(2, int(ry * scale)), start, count)
        for rx, ry, start, count in base_rings
    ]

    # Find which ring the assigned pad lives on
    active_idx = -1
    for idx, (_, _, start, count) in enumerate(ring_defs):
        if start <= pad < start + count:
            active_idx = idx
            break

    # Hint text
    if stype == "AsteroidBase":
        hint_map = {0: "Inner ring — large pad", 1: "Outer ring — small pad"}
    else:
        hint_map = {
            0: "Front ring (large pad) — nearest mailslot",
            1: "Mid-front ring (large pad)",
            2: "Mid-rear ring (medium pad)",
            3: "Rear ring (small pad) — back wall",
        }
    hint_text = hint_map.get(active_idx, "")

    # Draw concentric ring outlines — active ring brighter, others dim
    for idx, (rx, ry, _, _) in enumerate(ring_defs):
        steps     = max(rx, ry) * 6
        dot_style = "rgb(150,150,150)" if idx == active_idx else P.DIM
        for i in range(steps):
            angle = _math.pi + i * 2 * _math.pi / steps
            gx    = int(round(cx + rx * _math.sin(angle)))
            gy    = int(round(cy - ry * _math.cos(angle)))
            if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] == BLANK:
                grid[gy][gx] = ("·", dot_style)

    # Place only the assigned pad on its ring
    if active_idx >= 0:
        rx, ry, start, count = ring_defs[active_idx]
        i     = pad - start
        angle = _math.pi + i * 2 * _math.pi / count
        gx    = int(round(cx + rx * _math.sin(angle)))
        gy    = int(round(cy - ry * _math.cos(angle)))
        place(gx, gy, f"[{pad}]", "bold white")

    # Centre marker — mailslot (Coriolis-type) or cave centre (AsteroidBase)
    if stype == "AsteroidBase":
        place(cx, cy, "╳", P.LABEL_DIM)
    else:
        place(cx - 2, cy, "●", "bold rgb(255,60,60)")   # red  — port nav light
        place(cx,     cy, "▼", "bold white")             # mailslot
        place(cx + 2, cy, "●", "bold rgb(0,255,100)")   # green — starboard nav light

    # Build diagram text and centre horizontally
    diag  = Text()
    h_off = max(0, (panel_w - W) // 2)
    for row in grid:
        if h_off:
            diag.append(" " * h_off)
        for ch, sty in row:
            diag.append(ch, style=sty) if sty else diag.append(ch)
        diag.append("\n")
    parts.append(diag)

    # Centre vertically — add blank lines above diagram if there's spare room
    v_pad = max(0, panel_h - header_lines - H - (1 if hint_text else 0))
    if v_pad > 1:
        parts.insert(1, Text("\n" * (v_pad // 2)))

    if hint_text:
        parts.append(Text(f"{hint_text}\n", style=P.LABEL))

    return Group(*parts)
