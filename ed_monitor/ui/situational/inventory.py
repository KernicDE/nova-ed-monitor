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


def _render_inventory(s: AppState, scroll: int = 0) -> RenderableType:
    _ody_sort = lambda x: (x.get("Name_Localised") or x.get("Name", "")).lower()

    # Build flat list of ALL rows for scrolling (incl. Odyssey)
    all_rows: list[tuple] = []

    # ── Regular inventory ─────────────────────────────────────────────────────
    if s.cargo_items:
        all_rows.append(("header", "CARGO"))
        for item in s.cargo_items:
            all_rows.append(("cargo", item))
    for label, mdict in (
        ("RAW",          s.materials_raw),
        ("MANUFACTURED", s.materials_mfg),
        ("ENCODED",      s.materials_enc),
    ):
        if mdict:
            all_rows.append(("header", label))
            for name in sorted(mdict):
                all_rows.append(("mat", name, mdict[name]))

    # ── Odyssey materials (backpack + ship locker) ────────────────────────────
    has_backpack = any(s.backpack.get(k) for k in ("items", "components", "consumables", "data"))
    has_locker   = any(s.ship_locker.get(k) for k in ("items", "components", "consumables", "data"))
    if has_backpack or has_locker:
        all_rows.append(("ody_divider",))
        for sublabel, src_items in (
            ("BACKPACK — Items",       sorted(s.backpack.get("items",       []), key=_ody_sort)),
            ("BACKPACK — Components",  sorted(s.backpack.get("components",  []), key=_ody_sort)),
            ("BACKPACK — Consumables", sorted(s.backpack.get("consumables", []), key=_ody_sort)),
            ("BACKPACK — Data",        sorted(s.backpack.get("data",        []), key=_ody_sort)),
            ("LOCKER — Items",         sorted(s.ship_locker.get("items",       []), key=_ody_sort)),
            ("LOCKER — Components",    sorted(s.ship_locker.get("components",  []), key=_ody_sort)),
            ("LOCKER — Consumables",   sorted(s.ship_locker.get("consumables", []), key=_ody_sort)),
            ("LOCKER — Data",          sorted(s.ship_locker.get("data",        []), key=_ody_sort)),
        ):
            if src_items:
                all_rows.append(("ody_header", sublabel))
                for item in src_items:
                    all_rows.append(("ody_item", item))

    if not all_rows:
        t = Text()
        t.append("No inventory data yet.", style=P.LABEL)
        return t

    effective_scroll = min(scroll, max(0, len(all_rows) - 1))
    parts: list[RenderableType] = []
    visible_rows = all_rows[effective_scroll:]

    current_tbl: Optional[Table] = None

    def _flush_tbl() -> None:
        nonlocal current_tbl
        if current_tbl is not None:
            parts.append(current_tbl)
            current_tbl = None

    for row in visible_rows:
        kind = row[0]
        if kind == "header":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            parts.append(_section_header(row[1]))
            current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                row_styles=["", f"on {P.ROW_ALT}"])
            current_tbl.add_column("name",  style="white")
            current_tbl.add_column("count", justify="right")
        elif kind == "cargo":
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                    row_styles=["", f"on {P.ROW_ALT}"])
                current_tbl.add_column("name",  style="white")
                current_tbl.add_column("count", justify="right", style=P.AMBER)
            item = row[1]
            style = P.HUD_CRIT if item.get("stolen") else "white"
            current_tbl.add_row(
                Text(item["name"], style=style),
                Text(str(item["count"]), style=f"bold {P.AMBER}"),
            )
        elif kind == "mat":
            _, name, cnt = row
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                    row_styles=["", f"on {P.ROW_ALT}"])
                current_tbl.add_column("name",  style="white")
                current_tbl.add_column("count", justify="right")
            # Material caps: raw=150, manufactured=100, encoded=100
            _mat_cap = 150  # default for RAW
            for _hl, _md in (("RAW", s.materials_raw), ("MANUFACTURED", s.materials_mfg), ("ENCODED", s.materials_enc)):
                if name in _md:
                    _mat_cap = 100 if _hl != "RAW" else 150
                    break
            cnt_col = P.HUD_WARN if cnt >= _mat_cap else ("white" if cnt >= _mat_cap // 3 else P.LABEL)
            current_tbl.add_row(name, Text(str(cnt), style=f"bold {cnt_col}"))
        elif kind == "ody_divider":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            div = Text()
            div.append("── ODYSSEY ──────────────────────\n", style=f"bold {P.HEADER}")
            parts.append(div)
        elif kind == "ody_header":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            parts.append(_section_header(row[1]))
            current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                row_styles=["", f"on {P.ROW_ALT}"])
            current_tbl.add_column("name",  style=P.HUD_CYAN)
            current_tbl.add_column("count", justify="right")
        elif kind == "ody_item":
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                    row_styles=["", f"on {P.ROW_ALT}"])
                current_tbl.add_column("name",  style=P.HUD_CYAN)
                current_tbl.add_column("count", justify="right")
            item = row[1]
            name  = item.get("Name_Localised") or item.get("Name", "?")
            count = item.get("Count", 0)
            cnt_col = P.HUD_WARN if count >= 100 else ("white" if count >= 30 else P.LABEL)
            current_tbl.add_row(name, Text(str(count), style=f"bold {cnt_col}"))
    _flush_tbl()

    return Group(*parts)


