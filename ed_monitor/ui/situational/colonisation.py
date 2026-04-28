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


def _render_colonisation(s: AppState, scroll: int = 0) -> RenderableType:
    """Colonisation construction sites with commodity progress."""
    if not s.colonisation_sites:
        t = Text()
        t.append("No colonisation sites tracked.\n", style=P.LABEL)
        t.append("Approach a construction depot to populate this view.", style=f"dim {P.LABEL_DIM}")
        return t

    import math as _math
    parts: list[RenderableType] = []
    parts.append(_section_header("COLONISATION SITES"))

    # Sort sites: current system first, then by name
    sites = sorted(
        s.colonisation_sites.values(),
        key=lambda x: (0 if x.get("system", "") == s.system else 1, x.get("system", "")),
    )
    visible = sites[scroll:]

    for site in visible:
        sys_name = site.get("system", "?")
        mkt_id   = site.get("market_id", 0)
        in_cur   = sys_name == s.system

        site_head = Text()
        site_head.append(f"  {sys_name}", style="bold white" if in_cur else "white")
        if mkt_id:
            site_head.append(f"  #{mkt_id}\n", style=f"dim {P.LABEL_DIM}")
        else:
            site_head.append("\n", style="")
        parts.append(site_head)

        commodities = site.get("commodities", [])
        if commodities:
            for com in commodities[:10]:
                name     = com.get("name", "?")
                required = com.get("required", 0)
                provided = com.get("provided", 0)
                if required > 0:
                    pct    = min(1.0, provided / required)
                    filled = int(8 * pct)
                    bar    = "█" * filled + "░" * (8 - filled)
                    pct_s  = f"{pct*100:.0f}%"
                    bar_col = P.HUD_GREEN if pct >= 1.0 else P.AMBER
                    row_t  = Text()
                    row_t.append(f"    [{bar}] ", style=bar_col)
                    row_t.append(f"{provided}/{required}", style="white")
                    row_t.append(f"  {name}\n", style=P.LABEL)
                    parts.append(row_t)
                else:
                    row_t = Text()
                    row_t.append(f"    {name}: ", style=P.LABEL)
                    row_t.append(f"{provided} t delivered\n", style="white")
                    parts.append(row_t)
        else:
            t = Text()
            t.append("    Approach depot for commodity details\n", style=f"dim {P.LABEL_DIM}")
            parts.append(t)

    return Group(*parts)


