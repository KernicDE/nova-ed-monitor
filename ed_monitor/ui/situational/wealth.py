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


def _render_wealth(s: AppState, scroll: int = 0) -> RenderableType:
    # Build sections as a list so we can scroll by section
    sections: list[list[RenderableType]] = []

    # ── Balance ──────────────────────────────────────────────────────────────
    bal_text = Text()
    if s.credits > 0:
        bal_text.append(f"  {_de(s.credits)} Cr\n", style="bold white")
    else:
        bal_text.append("  Unknown\n", style=P.LABEL)
    sections.append([_section_header("BALANCE"), bal_text])

    # ── Fleet ────────────────────────────────────────────────────────────────
    fleet_parts: list[RenderableType] = []
    cur_ship = Text()
    if s.ship_type or s.ship_name:
        label = s.ship_name or s.ship_type
        cur_ship.append(f"  {label}", style="bold white")
        if s.ship_ident:
            cur_ship.append(f"  [{s.ship_ident}]", style=P.LABEL)
        cur_ship.append("  ◀ HERE\n", style=P.HUD_GREEN)
    fleet_parts.append(_section_header("FLEET"))
    fleet_parts.append(cur_ship)

    if s.stored_ships:
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                    row_styles=["", f"on {P.ROW_ALT}"])
        tbl.add_column("name",    style="white")
        tbl.add_column("ident",   style=P.LABEL,    width=8)
        tbl.add_column("system",  style=P.HUD_CYAN,  width=20)
        for ship in s.stored_ships:
            name   = ship.get("name") or ship.get("type") or "Unknown"
            ident  = ship.get("ident") or ""
            system = ship.get("system") or ""
            here   = ship.get("here", False)
            tbl.add_row(
                Text(name, style="bold white" if here else "white"),
                Text(ident, style=P.LABEL),
                Text(system + (" [HERE]" if here else ""), style=P.HUD_GREEN if here else P.HUD_CYAN),
            )
        fleet_parts.append(tbl)
    else:
        no_fleet = Text()
        no_fleet.append("  Open the ship transfer screen at any station\n", style=P.LABEL)
        no_fleet.append("  to load your full fleet.\n", style=P.LABEL)
        fleet_parts.append(no_fleet)
    sections.append(fleet_parts)

    # ── Cargo ────────────────────────────────────────────────────────────────
    if s.cargo_items:
        cargo_parts: list[RenderableType] = [
            _section_header(f"CARGO  {s.cargo}/{s.cargo_capacity}t"),
        ]
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1),
                    row_styles=["", f"on {P.ROW_ALT}"])
        tbl.add_column("name",  style="white")
        tbl.add_column("count", justify="right", style=P.AMBER)
        for item in s.cargo_items:
            style = P.HUD_CRIT if item.get("stolen") else "white"
            tbl.add_row(Text(item["name"], style=style), Text(str(item["count"]), style=f"bold {P.AMBER}"))
        cargo_parts.append(tbl)
        sections.append(cargo_parts)

    # ── Suit / backpack ──────────────────────────────────────────────────────
    if s.suit_loadout:
        suit_parts: list[RenderableType] = []
        suit_text = Text()
        suit_name = s.suit_loadout.get("suit") or "Unknown Suit"
        suit_text.append(f"  {suit_name}\n", style="white")
        weapons = s.suit_loadout.get("weapons") or []
        for w in weapons:
            wname = (w.get("SuitModuleName_Localised") or w.get("SuitModuleName") or "")
            if wname:
                suit_text.append(f"  ▸ {wname}\n", style=P.LABEL)
        suit_parts.append(_section_header("SUIT LOADOUT"))
        suit_parts.append(suit_text)
        sections.append(suit_parts)

    if not sections:
        t = Text()
        t.append("No wealth data yet.\n", style=P.LABEL)
        t.append("Dock at a station or open the in-game outfitting/shipyard menu.", style=P.LABEL)
        return t

    effective_scroll = min(scroll, max(0, len(sections) - 1))
    visible = []
    for sec in sections[effective_scroll:]:
        visible.extend(sec)
    return Group(*visible)


