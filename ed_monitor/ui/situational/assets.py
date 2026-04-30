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


def _render_assets(s: AppState, scroll: int = 0, mp: dict | None = None) -> RenderableType:
    """Unified assets panel: balance, fleet, cargo, suit, materials, Odyssey items."""
    mp = mp or P.mp("ship")
    _ody_sort = lambda x: (x.get("Name_Localised") or x.get("Name", "")).lower()

    # Build a flat list of renderable entries for unified scrolling
    all_rows: list[tuple] = []

    # ── Balance ──────────────────────────────────────────────────────────────
    all_rows.append(("section_header", "BALANCE"))
    if s.credits > 0:
        all_rows.append(("text", f"  {_de(s.credits)} Cr", "bold white"))
    else:
        all_rows.append(("text", "  Unknown", P.LABEL))

    # ── Fleet ────────────────────────────────────────────────────────────────
    all_rows.append(("section_header", "FLEET"))
    if s.ship_type or s.ship_name:
        label = s.ship_name or s.ship_type
        ident = f"  [{s.ship_ident}]" if s.ship_ident else ""
        all_rows.append(("text", f"  {label}{ident}  ◀ HERE", "bold white"))
    if s.stored_ships:
        for ship in s.stored_ships:
            name   = ship.get("name") or ship.get("type") or "Unknown"
            ident  = ship.get("ident") or ""
            system = ship.get("system") or ""
            here   = ship.get("here", False)
            all_rows.append(("ship", name, ident, system, here))
    else:
        all_rows.append(("text", "  Open ship transfer screen to load fleet", P.LABEL))

    # ── Cargo ────────────────────────────────────────────────────────────────
    if s.cargo_items:
        all_rows.append(("section_header", f"CARGO  {s.cargo}/{s.cargo_capacity}t"))
        for item in s.cargo_items:
            all_rows.append(("cargo", item))

    # ── Suit loadout ─────────────────────────────────────────────────────────
    if s.suit_loadout:
        all_rows.append(("section_header", "SUIT LOADOUT"))
        suit_name = s.suit_loadout.get("suit") or "Unknown Suit"
        all_rows.append(("text", f"  {suit_name}", "white"))
        weapons = s.suit_loadout.get("weapons") or []
        for w in weapons:
            wname = (w.get("SuitModuleName_Localised") or w.get("SuitModuleName") or "")
            if wname:
                all_rows.append(("text", f"  ▸ {wname}", P.LABEL))

    # ── Materials ────────────────────────────────────────────────────────────
    for label, mdict in (
        ("RAW",          s.materials_raw),
        ("MANUFACTURED", s.materials_mfg),
        ("ENCODED",      s.materials_enc),
    ):
        if mdict:
            all_rows.append(("section_header", label))
            for name in sorted(mdict):
                all_rows.append(("mat", name, mdict[name], label))

    # ── Odyssey materials ────────────────────────────────────────────────────
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
        t.append("No assets data yet.\n", style=P.LABEL)
        t.append("Dock at a station or open outfitting/shipyard.", style=P.LABEL)
        return t

    effective_scroll = min(scroll, max(0, len(all_rows) - 1))
    visible_rows = all_rows[effective_scroll:]

    parts: list[RenderableType] = []
    current_tbl: Optional[Table] = None

    def _flush_tbl() -> None:
        nonlocal current_tbl
        if current_tbl is not None:
            parts.append(current_tbl)
            current_tbl = None

    for row in visible_rows:
        kind = row[0]
        if kind == "section_header":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            parts.append(_section_header(row[1], mp["h1"], mp["bg"]))
        elif kind == "text":
            _flush_tbl()
            parts.append(Text(row[1], style=row[2]))
        elif kind == "ship":
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                    row_styles=["", f"on {P.ROW_ALT}"])
                current_tbl.add_column("name",    style="white")
                current_tbl.add_column("ident",   style=P.LABEL,    width=8)
                current_tbl.add_column("system",  style=P.HUD_CYAN,  width=20)
            _, name, ident, system, here = row
            current_tbl.add_row(
                Text(name, style="bold white" if here else "white"),
                Text(ident, style=P.LABEL),
                Text(system + (" [HERE]" if here else ""), style=P.HUD_GREEN if here else P.HUD_CYAN),
            )
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
            _, name, cnt, mat_label = row
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                                    row_styles=["", f"on {P.ROW_ALT}"])
                current_tbl.add_column("name",  style="white")
                current_tbl.add_column("count", justify="right")
            _mat_cap = 100 if mat_label != "RAW" else 150
            cnt_col = P.HUD_WARN if cnt >= _mat_cap else ("white" if cnt >= _mat_cap // 3 else P.LABEL)
            current_tbl.add_row(name, Text(str(cnt), style=f"bold {cnt_col}"))
        elif kind == "ody_divider":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            div = Text()
            div.append("── ODYSSEY ──────────────────────\n", style=f"bold {mp['h1']}")
            parts.append(div)
        elif kind == "ody_header":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            parts.append(_section_header(row[1], mp["h1"], mp["bg"]))
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
