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


def _render_bgs(s: AppState, scroll: int = 0, mp: dict | None = None) -> RenderableType:
    """BGS activity log: per-system per-faction activity counts (today's tick)."""
    mp = mp or P.mp("ship")
    if not s.bgs_log:
        t = Text()
        t.append("No BGS activity recorded today.", style=P.LABEL)
        return t

    parts: list[RenderableType] = []
    parts.append(_section_header("BGS ACTIVITY", mp["h1"], mp["bg"]))
    date_txt = Text(f"({s.bgs_log_date})\n", style=P.LABEL)
    parts.append(date_txt)

    # Flatten into rows with system headers interspersed
    flat_rows: list[tuple] = []  # (kind, ...)
    for sys_name in sorted(s.bgs_log.keys(), key=lambda n: (0 if n == s.system else 1, n)):
        fac_map = s.bgs_log[sys_name]
        fac_rows = []
        for faction, acts in fac_map.items():
            total   = sum(acts.values())
            act_items = sorted(acts.items(), key=lambda x: -x[1])
            act_str = "  ".join(f"{v}×{k}" for k, v in act_items)
            fac_rows.append((faction, act_str, total))
        fac_rows.sort(key=lambda r: -r[2])
        flat_rows.append(("header", sys_name))
        for faction, act_str, total in fac_rows:
            flat_rows.append(("row", faction, act_str, total))

    effective_scroll = min(scroll, max(0, len(flat_rows) - 1))
    visible = flat_rows[effective_scroll:]

    tbl = _data_table(mp["h2"])
    tbl.add_column("System/Faction", no_wrap=True)
    tbl.add_column("Activity",       no_wrap=True)
    tbl.add_column("Total", width=5, justify="right", no_wrap=True)

    for row in visible:
        if row[0] == "header":
            sys_name = row[1]
            sys_str = sys_name if sys_name != s.system else f"● {sys_name}"
            hdr_style = f"bold {mp['h1']}" if sys_name == s.system else P.LABEL
            tbl.add_row(
                Text(f"{sys_str}", style=hdr_style),
                Text("", style=""),
                Text("", style=""),
            )
        else:
            _, faction, act_str, total = row
            fac_short = faction[:28]
            # Truncate activity string to avoid overflow
            if len(act_str) > 50:
                act_str = act_str[:47] + "…"
            tbl.add_row(
                Text(f"  {fac_short}", style="white"),
                Text(act_str, style=P.LABEL),
                Text(str(total), style=P.AMBER),
            )
    parts.append(tbl)
    return Group(*parts)


