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
_CARRIER_PAD_DIM = P.LABEL_DIM   # all unassigned pads — readable but recessive


def _draw_carrier_bay(pad: int, panel_w: int) -> tuple[RenderableType, str]:
    """Rectangular bay diagram for Drake-class fleet carriers.

    FRONT header (green ▲) at the top, COCKPIT footer (amber ═) at the bottom.
    Assigned pad shown as [NN] in bright green; others uniformly dimmed.
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
                    t.append(f"[{lbl}]", style="bold rgb(0,255,150)")
                else:
                    t.append(f" {lbl} ", style=_CARRIER_PAD_DIM)
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


# ── Coriolis / Orbis / Ocellus pad layout ────────────────────────────────────
#
# 45 pads, 12 radial segments × 5 concentric offsets.
# Segment 1 = 6 o'clock (bottom), counterclockwise.
# Offset 0 = innermost, 4 = outermost.
# Source: https://github.com/rdnt/ed-landing-pads (pad,segment,offset,size)

_CORIOLIS_PADS: dict[int, tuple[int, int, str]] = {
     1: (1,0,"S"),  2: (1,1,"S"),  3: (1,2,"M"),  4: (1,4,"S"),
     5: (2,0,"S"),  6: (2,1,"S"),  7: (2,2,"M"),  8: (2,4,"S"),
     9: (3,0,"M"), 10: (3,2,"L"), 11: (4,0,"S"), 12: (4,1,"S"),
    13: (4,2,"S"), 14: (4,3,"S"), 15: (4,4,"S"), 16: (5,0,"S"),
    17: (5,1,"S"), 18: (5,2,"M"), 19: (5,4,"S"), 20: (6,0,"S"),
    21: (6,1,"S"), 22: (6,2,"M"), 23: (6,4,"S"), 24: (7,0,"M"),
    25: (7,2,"L"), 26: (8,0,"S"), 27: (8,1,"S"), 28: (8,2,"S"),
    29: (8,3,"S"), 30: (8,4,"S"), 31: (9,0,"S"), 32: (9,1,"S"),
    33: (9,2,"M"), 34: (9,4,"S"), 35:(10,0,"S"), 36:(10,1,"S"),
    37:(10,2,"M"), 38:(10,4,"S"), 39:(11,0,"M"), 40:(11,2,"L"),
    41:(12,0,"S"), 42:(12,1,"S"), 43:(12,2,"S"), 44:(12,3,"S"),
    45:(12,4,"S"),
}
# Base (rx, ry) per offset index 0–4, scaled by diagram scale factor
_CORIOLIS_RING_R: list[tuple[int, int]] = [(3,1),(5,2),(7,3),(9,4),(11,5)]
_CORIOLIS_CLOCK: dict[int, str] = {
    1:"6",2:"7",3:"8",4:"9",5:"10",6:"11",7:"12",8:"1",9:"2",10:"3",11:"4",12:"5",
}
_CORIOLIS_OFFSET_NAME: list[str] = ["Front","Front-Mid","Mid","Back-Mid","Back"]
_CORIOLIS_SIZE_NAME:   dict[str, str] = {"S":"small","M":"medium","L":"large"}


# ── Main renderer ─────────────────────────────────────────────────────────────

def _render_docking(s: AppState, panel_w: int = 60, panel_h: int = 24) -> RenderableType:
    """Docking pad diagram — front view of the station.

    Coriolis / Orbis / Ocellus:
        Circular ring diagram (mailslot centre, 5 concentric rings, 45 pads).
        12 radial segments × 5 offsets; segment 1 = 6 o'clock, counterclockwise.

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
    scale   = max(scale, 1.0)
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

    # ── Ring geometry and pad placement ──────────────────────────────────────
    active_idx = -1  # used by AsteroidBase centre-marker fallback
    if stype == "AsteroidBase":
        # 3 rings: 6 large (inner) + 8 medium (mid) + 4 small (outer) = 18 pads
        base_rings = [(4, 2, 1, 6), (6, 3, 7, 8), (8, 4, 15, 4)]
        ring_defs  = [
            (max(3, int(rx * scale)), max(2, int(ry * scale)), start, count)
            for rx, ry, start, count in base_rings
        ]
        active_idx = -1
        for idx, (_, _, start, count) in enumerate(ring_defs):
            if start <= pad < start + count:
                active_idx = idx
                break
        hint_text = {
            0: "Front — large pad",
            1: "Mid — medium pad",
            2: "Back — small pad",
        }.get(active_idx, "")

        for idx, (rx, ry, _, _) in enumerate(ring_defs):
            steps     = max(rx, ry) * 6
            dot_style = "rgb(150,150,150)" if idx == active_idx else P.DIM
            for i in range(steps):
                angle = _math.pi + i * 2 * _math.pi / steps
                gx    = int(round(cx + rx * _math.sin(angle)))
                gy    = int(round(cy - ry * _math.cos(angle)))
                if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] == BLANK:
                    grid[gy][gx] = ("·", dot_style)

        if active_idx >= 0:
            rx, ry, start, count = ring_defs[active_idx]
            i     = pad - start
            angle = _math.pi + i * 2 * _math.pi / count
            gx    = int(round(cx + rx * _math.sin(angle)))
            gy    = int(round(cy - ry * _math.cos(angle)))
            place(gx, gy, f"[{pad}]", "bold white")
        else:
            # Pad number unknown for this layout — show it in the centre
            place(cx, cy, f"[{pad}]", "bold white")
            hint_text = f"Pad {pad}"

    else:
        # Coriolis / Orbis / Ocellus — 45 pads, 12 segments × 5 offsets
        pad_info = _CORIOLIS_PADS.get(pad)          # (segment, offset, size) or None
        seg, off = (pad_info[0], pad_info[1]) if pad_info else (-1, -1)

        for idx, (rx_b, ry_b) in enumerate(_CORIOLIS_RING_R):
            rx        = max(3, int(rx_b * scale))
            ry        = max(2, int(ry_b * scale))
            steps     = max(rx, ry) * 6
            dot_style = "rgb(150,150,150)" if idx == off else P.DIM
            for i in range(steps):
                angle = _math.pi + i * 2 * _math.pi / steps
                gx    = int(round(cx + rx * _math.sin(angle)))
                gy    = int(round(cy - ry * _math.cos(angle)))
                if 0 <= gy < H and 0 <= gx < W and grid[gy][gx] == BLANK:
                    grid[gy][gx] = ("·", dot_style)

        if seg > 0 and off >= 0:
            rx_b, ry_b = _CORIOLIS_RING_R[off]
            rx    = max(3, int(rx_b * scale))
            ry    = max(2, int(ry_b * scale))
            angle = _math.pi + (seg - 1) * 2 * _math.pi / 12
            gx    = int(round(cx + rx * _math.sin(angle)))
            gy    = int(round(cy - ry * _math.cos(angle)))
            place(gx, gy, f"[{pad}]", "bold white")

        hint_text = ""
        if pad_info:
            hint_text = (
                f"{_CORIOLIS_OFFSET_NAME[off]} ring"
                f" — {_CORIOLIS_SIZE_NAME[pad_info[2]]} pad"
                f" — {_CORIOLIS_CLOCK[seg]} o'clock"
            )

    # Centre marker — mailslot (Coriolis-type) or cave centre (AsteroidBase)
    if stype == "AsteroidBase":
        # Skip centre mark when an out-of-range pad is shown in the centre
        if active_idx >= 0:
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
