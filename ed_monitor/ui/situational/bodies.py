"""Scanned bodies renderer for the situational panel (portrait mode)."""
from __future__ import annotations

import re
from collections import defaultdict

from rich.text import Text

from ...state import AppState
from .. import palette as P
from ..panels import (
    _data_table, _short_name, _abbrev_type, _body_value, _body_value_color,
    _body_color, _fmt_ls_compact, _fmt_value_short,
)


def _render_bodies(
    s: AppState,
    scroll: int,
    panel_h: int,
    sort_cache: list,
    mp: dict,
):
    """Render the scanned bodies table.

    sort_cache is a mutable list used as a sort deduplication cache.
    Pass an empty list [] on first call; it is updated in-place.
    Format: [sorted_bodies, bodies_version, system, star_short_names]

    Returns (renderable, above_count, below_count).
    """
    if not s.bodies:
        t = Text()
        t.append("No bodies scanned yet.", style=P.LABEL)
        return t, 0, 0

    system = s.system

    if (not sort_cache
            or sort_cache[1] != s.bodies_version
            or sort_cache[2] != system):
        visible = [b for b in s.bodies if b.planet_class or b.star_type]
        _star_short_names: set = set()
        for _sb in visible:
            if _sb.star_type:
                _sn = _short_name(_sb.name, system).strip() or "A"
                _star_short_names.add(_sn)

        def _body_sort_key(b):
            short = _short_name(b.name, system).strip()
            if not short and b.star_type and " " in b.name:
                m = re.search(r"\s+([A-Z0-9]{1,2})$", b.name)
                if m:
                    short = m.group(1)
            if not short:
                return (0, "")
            parts = short.split()
            if (not b.star_type and parts[0].isalpha()
                    and len(parts[0]) > 1 and parts[0].isupper()):
                root_parent = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]
                bucket = 0 if root_parent in _star_short_names else 1
            else:
                bucket = 0
            key_parts = [f"{int(p):04d}" if p.isdigit() else p.lower() for p in parts]
            return (bucket, " ".join(key_parts))

        visible.sort(key=_body_sort_key)
        sort_cache[:] = [visible, s.bodies_version, system, _star_short_names]
    else:
        visible = sort_cache[0]
        _star_short_names = sort_cache[3]

    total_bodies = len(visible)
    effective_scroll = min(scroll, max(0, total_bodies - 1))
    above = effective_scroll
    below = max(0, total_bodies - effective_scroll - max(1, panel_h - 2))
    visible = visible[effective_scroll:]

    tbl = _data_table(mp["h2"])
    tbl.add_column("Body",    style="white", width=14, no_wrap=True)
    tbl.add_column("Type",    width=8)
    tbl.add_column("Est Val", width=11, justify="right")
    tbl.add_column("Dist",    width=11, justify="right")
    tbl.add_column("B",       width=4)
    tbl.add_column("G",       width=2)
    tbl.add_column("LTA",     width=5)
    tbl.add_column("F",       width=2)
    tbl.add_column("D",       width=2)

    bio_done: set = set()
    complete_by_body: dict = defaultdict(int)
    for sc in s.bio_scans:
        if sc.complete:
            complete_by_body[sc.body] += 1
    for b in s.bodies:
        if b.bio_signals > 0 and complete_by_body.get(b.name, 0) >= b.bio_signals:
            bio_done.add(b.name)

    for b in visible:
        short = _short_name(b.name, system).strip()
        display_name = short or ("A" if b.star_type else b.name)
        parts = display_name.split()

        is_barycentric_prefix = (
            not b.star_type and parts[0].isalpha()
            and len(parts[0]) > 1 and parts[0].isupper()
        )
        if is_barycentric_prefix:
            root_parent = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]
            is_barycentre_body = root_parent not in _star_short_names
        else:
            is_barycentre_body = False

        if b.star_type:
            level = 0
        elif is_barycentre_body:
            level = max(0, b.level - 1)
        else:
            level = b.level

        indent = " " * max(0, level)
        g_val = b.surface_gravity / 9.80665 if b.surface_gravity > 0 and b.landable else 0.0
        if g_val >= 3.0:
            name_style = f"bold {P.HIGH_G_CRIT}"
        elif g_val >= 1.5:
            name_style = f"bold {P.HIGH_G_WARN}"
        else:
            name_style = "white"
        name     = Text(indent + display_name, style=name_style)
        btype    = _abbrev_type(b.planet_class, b.star_type)
        bv       = _body_value(b)
        val      = _fmt_value_short(bv)
        val_col  = _body_value_color(b)
        dist     = _fmt_ls_compact(b.dist_ls)
        dist_col = P.DIM if b.dist_ls == 0.0 else "white"
        geo      = str(b.geo_signals) if b.geo_signals else "—"
        geo_col  = P.PURPLE if b.geo_signals > 0 else P.DIM
        fss_str  = "●" if b.fss_scanned else "—"
        fss_col  = P.AMBER      if b.fss_scanned else P.DIM
        map_str  = "●" if b.mapped else "—"
        map_col  = P.HUD_GREEN  if b.mapped      else P.DIM
        needs_dss = b.bio_signals > 0 and not b.mapped
        type_col  = _body_color(b.planet_class, b.star_type)

        if b.name in bio_done:
            bio     = f"{b.bio_signals}✓"
            bio_col = f"bold {P.GOLD}"
        elif needs_dss:
            bio     = str(b.bio_signals)
            bio_col = f"bold {P.BIO_DSS}"
        elif b.bio_signals > 0:
            bio     = str(b.bio_signals)
            bio_col = P.HUD_GREEN
        else:
            bio     = "—"
            bio_col = P.DIM

        atm_present = bool(b.atmosphere and "No atmo" not in b.atmosphere)
        flags       = (
            ("L" if b.landable  else " ") +
            ("T" if b.terraform else " ") +
            ("A" if atm_present else " ")
        )
        flags_style = f"bold {P.FLAGS_GOOD}" if flags.strip() else P.DIM

        tbl.add_row(
            name,
            Text(btype,   style=f"bold {type_col}"),
            Text(val,     style=val_col),
            Text(dist,    style=dist_col),
            Text(bio,     style=bio_col),
            Text(geo,     style=geo_col),
            Text(flags,   style=flags_style),
            Text(fss_str, style=f"bold {fss_col}"),
            Text(map_str, style=f"bold {map_col}"),
        )

    return tbl, above, below
