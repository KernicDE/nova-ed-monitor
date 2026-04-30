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


def _render_missions(s: AppState, scroll: int = 0, mp: dict | None = None) -> RenderableType:
    mp = mp or P.mp("ship")
    if not s.missions:
        t = Text()
        t.append("No active missions.", style=P.LABEL)
        return t

    parts: list[RenderableType] = []

    # Massacre kill progress (grouped by faction)
    if s.massacre_kills:
        # Group by faction
        fac_kills: dict = {}
        for mid, mk in s.massacre_kills.items():
            fac = mk["faction"]
            if fac not in fac_kills:
                fac_kills[fac] = {"needed": 0, "done": 0}
            fac_kills[fac]["needed"] += mk["needed"]
            fac_kills[fac]["done"]   += mk["done"]

        parts.append(_section_header("MASSACRE PROGRESS", mp["h1"], mp["bg"]))

        for fac, kd in fac_kills.items():
            done   = kd["done"]
            needed = kd["needed"]
            filled = int(10 * done / needed) if needed > 0 else 0
            bar    = "█" * filled + "░" * (10 - filled)
            pct_t  = Text()
            pct_t.append(f"  [{bar}] ", style=P.HUD_CRIT)
            pct_t.append(f"{done}/{needed}", style="white")
            pct_t.append(f"  {fac}\n", style=P.LABEL)
            parts.append(pct_t)

    missions = s.missions
    effective_scroll = min(scroll, max(0, len(missions) - 1))
    visible_missions = missions[effective_scroll:]

    tbl = _data_table(mp["h2"])
    tbl.add_column("Mission")
    tbl.add_column("Destination", width=20)
    tbl.add_column("Time left",   width=9, justify="right")

    for m in visible_missions:
        remaining = _mission_time_remaining(m.expiry)
        if remaining == "Expired":
            time_col = P.HUD_CRIT
        elif remaining and remaining[0].isdigit() and remaining.endswith("m"):
            time_col = P.HUD_WARN
        else:
            time_col = P.LABEL

        tbl.add_row(
            Text(m.name, style="white"),
            Text(m.destination, style=P.LABEL),
            Text(remaining, style=f"bold {time_col}"),
        )
    parts.append(tbl)

    return Group(*parts)


# Odyssey (on-foot) engineers — they don't use the 1–5 grade system.

def _mission_time_remaining(expiry: str) -> str:
    if not expiry:
        return ""
    try:
        # ED timestamps: "2025-03-08T12:34:56Z" or without Z
        ts = expiry.rstrip("Z")
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        secs  = int(delta.total_seconds())
        if secs < 0:
            return "Expired"
        days  = secs // 86400
        hours = (secs % 86400) // 3600
        mins  = (secs % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return ""


# ── Shared rendering helpers ──────────────────────────────────────────────────

