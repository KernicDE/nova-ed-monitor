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
from ...materials_catalog import (
    RAW_CATEGORIES, MANUFACTURED_CATEGORIES, ENCODED_CATEGORIES,
    lookup,
)
from ..panels import (
    _data_table, _section_header, _kv_row, _kv_line, _two_column_table,
    _short_name, _natural_key,
    _body_color, _abbrev_type, _body_value, _body_value_color,
    _fmt_cr_compact, _fmt_value, _fmt_ls_compact, _fmt_metres,
    _fmt_notable_val, _de,
)


def _calc_mat_col_widths(panel_w: int) -> dict[str, int]:
    """Compute shared column widths for all material tables.

    The bar gets most of the extra space.  Names expand next.  Category
    labels get a small boost.  The widths are identical across RAW,
    MANUFACTURED and ENCODED so every column lines up vertically.
    """
    gaps = 5                     # 1 space between each pair of 6 columns
    margins = 2                  # 1 space left + right edge padding
    available = max(30, panel_w - gaps - margins)

    cat_min, cat_max = 5, 13
    grade_w = 2
    name_min, name_max = 6, 38
    count_w = 7
    pct_w = 4
    bar_min = 5

    base = cat_min + grade_w + name_min + count_w + pct_w + bar_min
    extra = available - base

    if extra <= 0:
        return {
            "cat": cat_min, "grade": grade_w, "name": name_min,
            "count": count_w, "bar": bar_min, "pct": pct_w,
        }

    # Distribute extra: bar gets the lion's share, then name, then cat
    name_extra = min(name_max - name_min, int(extra * 0.35))
    cat_extra = min(cat_max - cat_min, int(extra * 0.15))
    bar_extra = extra - name_extra - cat_extra

    return {
        "cat": cat_min + cat_extra,
        "grade": grade_w,
        "name": name_min + name_extra,
        "count": count_w,
        "bar": bar_min + bar_extra,
        "pct": pct_w,
    }


def _build_mat_row(
    cat: str,
    grade: int,
    name: str,
    cnt: int,
    cap: int,
    col_widths: dict[str, int],
) -> Text:
    """Return one aligned material row as a Rich Text object."""
    cw = col_widths
    pct = min(100, int(cnt * 100 / cap)) if cap else 0

    # Scale bar to the allocated width
    bar_w = cw["bar"]
    filled = int(pct * bar_w / 100)
    bar = "█" * filled + "░" * (bar_w - filled)

    # Truncate category and name to fit
    cat_w = cw["cat"]
    if len(cat) > cat_w:
        display_cat = cat[: cat_w - 1] + "…"
    else:
        display_cat = cat

    name_w = cw["name"]
    if len(name) > name_w:
        display_name = name[: name_w - 1] + "…"
    else:
        display_name = name

    # Colour coding
    name_style = "white" if cnt > 0 else P.LABEL_DIM
    cnt_style = (
        P.HUD_WARN
        if cnt >= cap
        else ("white" if cnt >= cap // 3 else P.LABEL)
    )
    bar_style = (
        P.HUD_GREEN
        if pct >= 80
        else (
            P.HUD_WARN
            if pct >= 50
            else ("white" if pct > 0 else P.DIM)
        )
    )

    t = Text()
    t.append(" ", style=P.LABEL)                          # left margin
    t.append(f"{display_cat:{cat_w}} ", style=f"bold {P.LABEL}")
    t.append(f"G{grade:<{cw['grade'] - 1}} ", style=P.LABEL)
    t.append(f"{display_name:{name_w}} ", style=name_style)
    t.append(f"{cnt:>3}/{cap:<3} ", style=cnt_style)
    t.append(f"{bar} ", style=bar_style)
    t.append(f"{pct:>3}%", style=P.LABEL)
    t.append(" ", style=P.LABEL)                          # right margin
    return t


def _render_assets(
    s: AppState,
    scroll: int = 0,
    panel_w: int = 80,
    mp: dict | None = None,
) -> RenderableType:
    """Unified assets panel: balance, fleet, cargo, suit, materials, Odyssey items."""
    mp = mp or P.mp("ship")
    _ody_sort = lambda x: (x.get("Name_Localised") or x.get("Name", "")).lower()

    # ── Shared column widths for all material rows ───────────────────────────
    _col_widths = _calc_mat_col_widths(panel_w)

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

    # ── Materials Tracker ────────────────────────────────────────────────────
    _CATEGORY_MAP = {
        "RAW": (s.materials_raw, RAW_CATEGORIES),
        "MANUFACTURED": (s.materials_mfg, MANUFACTURED_CATEGORIES),
        "ENCODED": (s.materials_enc, ENCODED_CATEGORIES),
    }
    for label, (mdict, categories) in _CATEGORY_MAP.items():
        if not mdict:
            continue
        all_rows.append(("section_header", label))
        for cat_name, mats in categories:
            for i, info in enumerate(mats):
                cnt = mdict.get(info.name, 0)
                cat_display = cat_name if i == 0 else ""
                display_name = s.material_names.get(info.name, info.name)
                all_rows.append(("mat_row", cat_display, info.grade, display_name, cnt, info.cap, _col_widths))

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
        elif kind == "mat_row":
            _flush_tbl()
            _, cat_display, grade, name, cnt, cap, col_widths = row
            parts.append(_build_mat_row(cat_display, grade, name, cnt, cap, col_widths))
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
