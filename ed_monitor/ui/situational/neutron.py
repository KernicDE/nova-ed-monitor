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


def _render_neutron(s: AppState, scroll: int = 0) -> RenderableType:
    parts: list[RenderableType] = []

    # Status header
    status = s.neutron_route_status
    target = s.neutron_route_to
    route  = s.neutron_route

    hdr = Text()
    hdr.append("NEUTRON ROUTE PLOTTER  ", style="bold " + P.HEADER)
    hdr.append("via Spansh API\n", style=P.LABEL)
    if s.jump_range > 0:
        hdr.append(f"  Unladen max: ", style=P.LABEL)
        hdr.append(f"{s.jump_range:.1f} ly", style="white")
        hdr.append(f"  →  boosted {s.jump_range * 4:.0f} ly\n", style=P.LABEL)
        if s.jump_range_last > 0:
            diff = s.jump_range - s.jump_range_last
            diff_str = f"  ({diff:+.1f} ly vs unladen)" if abs(diff) > 0.5 else ""
            hdr.append(f"  Last jump:  ", style=P.LABEL)
            hdr.append(f"{s.jump_range_last:.1f} ly", style="white")
            hdr.append(f"{diff_str}\n", style=P.LABEL)
        else:
            hdr.append("  Last jump:  unknown — make a jump first for accurate routing\n", style=P.LABEL)
    else:
        hdr.append("  Jump range: unknown — fly your ship first\n", style=P.LABEL)
    parts.append(hdr)

    if status == "plotting":
        t = Text()
        t.append(f"\n  Plotting route to {target}…\n", style=P.AMBER)
        parts.append(t)
    elif status == "error":
        t = Text()
        t.append(f"\n  Could not plot route to '{target}'.\n", style=P.HUD_CRIT)
        t.append("  Check that the system name is spelled exactly as in-game.\n", style=P.LABEL)
        parts.append(t)
    elif status == "done" and route:
        # Skip the starting-system entry (distance=0, jumps=0) — it's just the origin
        display_route = [j for j in route if j.get("distance", 0) > 0 or j.get("jumps", 0) > 0]
        total_ly      = sum(j.get("distance", 0) for j in display_route)
        neutron_count = sum(1 for j in display_route if j.get("neutron"))
        regular_hops  = sum(j.get("jumps", 0) for j in display_route)
        summary = Text()
        summary.append(f"\n  → {target}\n", style="bold white")
        summary.append(
            f"  {len(display_route)} waypoints  |  {regular_hops} regular + {neutron_count} boosted jumps"
            f"  |  {total_ly:,.0f} ly\n",
            style=P.AMBER,
        )
        parts.append(summary)

        max_rows = max(5, panel_h - 5)
        scroll = max(0, min(scroll, max(0, len(display_route) - max_rows)))
        visible = display_route[scroll:scroll + max_rows]

        tbl = _data_table()
        tbl.add_column("#",    width=4, justify="right")
        tbl.add_column("System")
        tbl.add_column("Boost", width=9, justify="right")
        tbl.add_column("",     width=5)

        for i, jump in enumerate(visible, scroll + 1):
            sys_name  = jump.get("system") or "—"
            dist      = jump.get("distance", 0.0)
            pre_jumps = jump.get("jumps", 0)
            is_n      = jump.get("neutron", False)
            is_last   = (i == len(display_route))

            dist_str = Text(
                f"{dist:.1f} ly",
                style=P.HUD_GREEN if is_n else ("bold white" if is_last else "white"),
            )

            # Marker col: ⚡ Nj for neutron (Nj = regular hops to reach this star)
            #             Nj → for non-neutron with pre-hops  (e.g. final destination)
            #             (empty) for non-neutron without pre-hops
            marker = Text()
            if is_n:
                marker.append("⚡", style=f"bold {P.HUD_GREEN}")
                if pre_jumps > 0:
                    marker.append(f" {pre_jumps}j", style=P.LABEL)
            elif pre_jumps > 0:
                marker.append(f"{pre_jumps}j", style=P.LABEL)

            tbl.add_row(
                Text(str(i), style=P.LABEL),
                Text(sys_name, style="bold white" if is_last else "white"),
                dist_str,
                marker,
            )

        if scroll > 0:
            tbl.add_row(Text("↑", style=P.LABEL), Text(f"{scroll} above", style=P.LABEL), Text(""), Text(""))
        remaining_below = len(display_route) - scroll - len(visible)
        if remaining_below > 0:
            tbl.add_row(Text("↓", style=P.LABEL), Text(f"{remaining_below} more  (↓/↑)", style=P.LABEL), Text(""), Text(""))
        parts.append(tbl)
    else:
        hint = Text()
        hint.append("\n  Press  n  to enter a destination system.\n", style=P.LABEL)
        hint.append("  Uses local neutron star data (Spansh dump, refreshed daily).\n", style=P.LABEL)
        parts.append(hint)

    return Group(*parts)


