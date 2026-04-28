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


def _render_route(s: AppState, scroll: int = 0, panel_height: int = 40) -> RenderableType:
    """Nav route panel: jump#, system, star class+scoopable, body count, dist, jump dist, EDSM."""
    import math as _math

    route = s.route_list
    if not route:
        t = Text()
        t.append("No nav route active.\n", style=P.LABEL)
        t.append("Set a route in-game to populate this view.", style=f"dim {P.LABEL_DIM}")
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
    hdr.append(f"  {hops} {word} remaining", style=f"bold {P.HEADER}")
    if total_ly > 0:
        hdr.append(f" ({_fmt_ly(total_ly)} ly)", style=P.LABEL)
    if s.route_destination:
        hdr.append(" → ", style=P.LABEL)
        hdr.append(s.route_destination, style="bold white")
    hdr.append("\n")

    parts: list[RenderableType] = [hdr]

    effective_scroll = min(scroll, max(0, len(display_route) - 1))

    tbl = _data_table()
    tbl.add_column("#",      width=3,  justify="right",  no_wrap=True)
    tbl.add_column("System", width=28)
    tbl.add_column("★",      width=5,  no_wrap=True)
    tbl.add_column("Bd",     width=2,  justify="right",  no_wrap=True)
    tbl.add_column("Dist",   width=7,  justify="right",  no_wrap=True)
    tbl.add_column("Jump",   width=6,  justify="right",  no_wrap=True)
    tbl.add_column("EDSM",   width=4,  justify="center", no_wrap=True)

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

        body_entry   = bodies.get(name)
        body_in_edsm = body_entry is not None and body_entry.get("bodies", 0) > 0

        edsm_entry = edsm.get(name)
        if (edsm_entry is None) and not body_in_edsm:
            edsm_text = Text("?", style=P.LABEL)
        elif not body_in_edsm and edsm_entry is not None and edsm_entry.get("live_known") is False and not edsm_entry.get("x"):
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

        if body_entry is None:
            bd_text = Text("…", style=P.LABEL)
        else:
            bd = body_entry.get("bodies", 0)
            bd_text = Text(str(bd) if bd else "·", style=P.WHITE if bd else "dim")

        tbl.add_row(
            Text(str(i), style=P.LABEL),
            Text(name, style=name_style),
            star_cell,
            bd_text,
            Text(_fmt_ly(dist_cur), style=P.WHITE),
            Text(_fmt_ly(jump_d),   style=P.LABEL),
            edsm_text,
        )

        if pos_list:
            prev_pos = (pos_list[0], pos_list[1], pos_list[2])

    parts.append(tbl)

    return Group(*parts)


# ── Shared log-line renderer ──────────────────────────────────────────────────

