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


def _render_stats(s: AppState) -> RenderableType:
    st = s.stats  # {stat_key: {today, week, month, year, total}}

    def _g(key: str, period: str) -> float:
        return st.get(key, {}).get(period, 0.0)

    def _fmt_count(v: float) -> str:
        n = int(v)
        if n == 0:               return "—"
        if n >= 1_000_000_000:   return f"{n/1_000_000_000:.1f}B"
        if n >= 1_000_000:       return f"{n/1_000_000:.1f}M"
        if n >= 1_000:           return f"{n/1_000:.1f}k"
        return str(n)

    def _fmt_ly(v: float) -> str:
        if v == 0:          return "—"
        if v >= 1_000_000:  return f"{v/1_000_000:.1f}M"
        if v >= 1_000:      return f"{v/1_000:.1f}k"
        return f"{v:.0f}"

    def _fmt_cr(v: float) -> str:
        n = int(v)
        if n == 0:             return "—"
        if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
        if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
        if n >= 1_000:         return f"{n/1_000:.1f}k"
        return str(n)

    HDR  = "bold " + P.HEADER
    MAIN = "white"
    SUB  = P.LABEL

    tbl = _data_table()
    tbl.add_column("",      width=12)
    tbl.add_column("Today", width=7,  justify="right")
    tbl.add_column("Week",  width=7,  justify="right")
    tbl.add_column("Month", width=7,  justify="right")
    tbl.add_column("Year",  width=8,  justify="right")
    tbl.add_column("Total", width=8,  justify="right")

    PERIODS = ("today", "week", "month", "year", "total")

    def row(label: str, key: str, fmt_fn, indent: bool = False) -> None:
        lbl       = f" {label}" if indent else label
        lbl_style = SUB if indent else MAIN
        val_style = SUB if indent else MAIN
        tbl.add_row(
            Text(lbl, style=lbl_style),
            *[Text(fmt_fn(_g(key, p)), style=val_style) for p in PERIODS],
        )

    row("Jumps",         "jump_count",         _fmt_count)
    row("Distance ly",   "jump_dist_ly",        _fmt_ly,    indent=True)
    row("Credits +",  "credits_earned",      _fmt_cr)
    row("Credits −",  "credits_spent",       _fmt_cr)
    row("FSS Bodies", "fss_count",           _fmt_count)
    row("Undiscov.",  "fss_undiscovered",    _fmt_count, indent=True)
    row("Value",      "fss_value",           _fmt_cr,    indent=True)
    row("DSS Bodies", "dss_count",           _fmt_count)
    row("Undiscov.",  "dss_undiscovered",    _fmt_count, indent=True)
    row("Value",      "dss_value",           _fmt_cr,    indent=True)
    row("Bio Scanned","bio_count",           _fmt_count)
    row("1st Ffall.", "bio_first_footfall",  _fmt_count, indent=True)
    row("Value",      "bio_value",           _fmt_cr,    indent=True)
    row("Enemies",    "enemies_destroyed",   _fmt_count)
    row("Ships Lost", "ships_lost",          _fmt_count)

    disclaimer = Text(
        "* Estimated payouts incl. bonuses. Unsold data is retained if killed.",
        style=P.DIM,
    )
    return Group(_section_header("STATISTICS"), tbl, disclaimer)


