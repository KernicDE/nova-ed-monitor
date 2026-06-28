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


def _render_bio(s: AppState, scroll: int = 0, mp: dict | None = None) -> RenderableType:
    mp = mp or P.mp("ship")
    from ...events import _BIO_GENUS_VALUE_RANGE, _BIO_SPECIES_VALUES, bio_variant

    # Group by body
    from collections import defaultdict as _dd
    by_body: dict = _dd(list)
    for sc in s.bio_scans:
        by_body[sc.body or "Unknown"].append(sc)

    # Bodies DSS'd with bio_genuses but no scan started yet (pre-scan)
    scanned_bodies = set(by_body.keys())
    prescan_bodies = [
        b for b in s.bodies
        if b.bio_genuses and b.name not in scanned_bodies
    ]
    dss_bodies = {b.name for b in prescan_bodies}

    # Bodies with bio signals detected by FSS but not yet DSS'd — show predictions
    # (even if no prediction is possible, show as ?unknown? so the body is visible)
    predicted_bodies = [
        b for b in s.bodies
        if b.bio_signals > 0
        and not b.bio_genuses
        and b.name not in scanned_bodies
        and b.name not in dss_bodies
    ]

    # Sort predicted/prescan bodies the same way as the Bodies panel: by natural key on short name
    _sys = s.system
    predicted_bodies.sort(key=lambda b: _natural_key(_short_name(b.name, _sys)))
    prescan_bodies.sort(   key=lambda b: _natural_key(_short_name(b.name, _sys)))

    total_known = sum(sc.value for sc in s.bio_scans if sc.complete and sc.value > 0)

    # Build flat list of body groups for scrolling
    # Sort scanned bodies by natural key on body name (same order as Bodies panel)
    groups: list[tuple[str, object]] = []
    for b in predicted_bodies:
        groups.append(("predicted", b))
    for b in prescan_bodies:
        groups.append(("prescan", b))
    for body_name in sorted(by_body, key=lambda n: _natural_key(_short_name(n, _sys))):
        groups.append(("scan", (body_name, by_body[body_name])))

    if not groups:
        t = Text()
        t.append("No biological scans active.", style=P.LABEL)
        return t

    parts: list[RenderableType] = [Text("\n")]

    effective_scroll = min(scroll, max(0, len(groups) - 1))

    for _gi, (gtype, gdata) in enumerate(groups[effective_scroll:]):
        if _gi > 0 or effective_scroll > 0:
            parts.append(Text("\n"))
        if gtype == "predicted":
            b = gdata
            short = _short_name(b.name, s.system) if b.name and s.system else b.name
            _ff_pred = getattr(b, "first_footfall", False)
            subtitle = f"FSS · {b.bio_signals} bio"
            if _ff_pred:
                subtitle += " · ✦ FF"
            parts.append(_section_header(f"{short}  ({subtitle})", mp["h1"], mp["bg"]))

            if b.bio_genuses_predicted:
                _variant = bio_variant(s.primary_star_class)
                tbl = _data_table(mp["h2"])
                tbl.add_column("Predicted Species", width=24)
                tbl.add_column("Est. Value",        width=20)

                _rng_lo: list[int] = []
                _rng_hi: list[int] = []
                for sp in b.bio_genuses_predicted:
                    key = sp.lower().split()[0] if sp else ""
                    # Use exact species value when known, else genus range
                    exact = _BIO_SPECIES_VALUES.get(sp, 0)
                    if exact > 0:
                        lo = hi = exact
                    else:
                        lo, hi = _BIO_GENUS_VALUE_RANGE.get(key, (0, 0))
                    if _ff_pred and lo > 0:
                        lo *= 5
                        hi *= 5
                    if exact > 0:
                        val_s = _fmt_cr_compact(exact * 5 if _ff_pred else exact)
                    else:
                        val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
                    _rng_lo.append(lo)
                    _rng_hi.append(hi)
                    label = f"? {sp}"
                    if _variant:
                        label += f" [{_variant}]"
                    tbl.add_row(
                        Text(label, style=P.LABEL),
                        Text(val_s, style=P.AMBER),
                    )
                parts.append(tbl)
                hint_t = Text()
                hint_t.append("  DSS to confirm", style=P.LABEL)
                if b.bio_signals > 0:
                    hint_t.append(f"  ·  {b.bio_signals} bio signal{'s' if b.bio_signals != 1 else ''}", style=P.LABEL)
                if _rng_hi:
                    _n = max(1, b.bio_signals)
                    _total_lo = sum(sorted(_rng_lo)[:_n])
                    _total_hi = sum(sorted(_rng_hi, reverse=True)[:_n])
                    _est = f"~{_fmt_cr_compact(_total_lo)}–{_fmt_cr_compact(_total_hi)}"
                    hint_t.append(f"  ·  pot. {_est}", style=P.LABEL)
                hint_t.append("\n")
                parts.append(hint_t)
            else:
                unk_t = Text()
                unk_t.append(f"  ? unknown  ", style=P.LABEL)
                unk_t.append(f"({b.bio_signals} bio signal{'s' if b.bio_signals != 1 else ''})", style=P.LABEL)
                unk_t.append("  DSS to identify\n", style=P.LABEL)
                parts.append(unk_t)

        elif gtype == "prescan":
            b = gdata
            short = _short_name(b.name, s.system) if b.name and s.system else b.name
            _ff = getattr(b, "first_footfall", False)
            subtitle = "DSS"
            if _ff:
                subtitle += " · ✦ FF"
            parts.append(_section_header(f"{short}  ({subtitle})", mp["h1"], mp["bg"]))

            _dss_variant = bio_variant(s.primary_star_class)
            tbl = _data_table(mp["h2"])
            tbl.add_column("Genus (DSS)",  width=24)
            tbl.add_column("Est. Value",   width=20)

            for g in b.bio_genuses:
                key = g.lower().split()[0] if g else ""
                lo, hi = _BIO_GENUS_VALUE_RANGE.get(key, (0, 0))
                if _ff and lo > 0:
                    lo, hi = lo * 5, hi * 5
                val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
                label = g
                if _dss_variant:
                    label += f" [{_dss_variant}]"
                tbl.add_row(
                    Text(label, style=P.HUD_CYAN),
                    Text(val_s, style=P.AMBER),
                )
            parts.append(tbl)

            if b.bio_value_min > 0:
                est_t = Text()
                est_t.append("Est. total  ", style=P.LABEL)
                _vmin = b.bio_value_min * 5 if _ff else b.bio_value_min
                _vmax = b.bio_value_max * 5 if _ff else b.bio_value_max
                est_t.append(
                    f"~{_fmt_cr_compact(_vmin)}–{_fmt_cr_compact(_vmax)}",
                    style=f"bold {P.GOLD}",
                )
                parts.append(est_t)

        else:
            body_name, scans = gdata
            short = _short_name(body_name, s.system) if body_name and s.system else body_name
            _scan_ff = any(sc.first_footfall for sc in scans)
            subtitle = f"{len(scans)} sample{'s' if len(scans) != 1 else ''}"
            if _scan_ff:
                subtitle += " · ✦ FF"
            parts.append(_section_header(f"{short}  ({subtitle})", mp["h1"], mp["bg"]))

            tbl = _data_table(mp["h2"])
            tbl.add_column("Species",  width=21)
            tbl.add_column("Genus",    width=13)
            tbl.add_column("Smp",      width=5)
            tbl.add_column("MinDist",  width=8)
            tbl.add_column("Travel",   width=22)
            tbl.add_column("Value",    width=14)

            for sc in scans:
                samples_col = {3: P.HUD_GREEN, 2: P.HUD_WARN, 1: P.BIO_SAMPLE_1}.get(sc.samples, P.LABEL)
                if sc.first_footfall:
                    species_str = f"✦ {sc.species_localised}"
                elif sc.first_discovered:
                    species_str = f"★ {sc.species_localised}"
                else:
                    species_str = sc.species_localised
                samples_str = f"{sc.samples}/3"
                min_str     = _fmt_metres(sc.min_dist)

                if sc.value > 0:
                    value_str = _fmt_value(sc.value)
                elif sc.complete:
                    value_str = "—"
                else:
                    value_str = "?"

                name_style = (
                    f"bold {P.FIRST_FOOTFALL}" if sc.first_footfall
                    else (f"bold {P.GOLD}" if sc.first_discovered
                    else (f"{P.DIM} strike" if sc.complete else "white"))
                )

                if sc.current_dist is not None:
                    ratio      = min(sc.current_dist / sc.min_dist, 1.0) if sc.min_dist > 0 else 1.0
                    filled     = int(ratio * 10)
                    bar        = "█" * filled + "░" * (10 - filled)
                    arrows     = " ".join(sc.sample_bearings) if sc.sample_bearings else (sc.current_bearing or "")
                    arrow_str  = f" {arrows}" if arrows else ""
                    travel_str = f"{bar} {sc.current_dist:.0f}m{arrow_str}"
                    travel_col = P.HUD_GREEN if ratio >= 1.0 else P.HUD_WARN
                elif sc.samples == 0 or sc.complete:
                    travel_str, travel_col = "—", P.DIM
                else:
                    travel_str, travel_col = "No position", P.LABEL

                if sc.value > 0 and sc.first_footfall:
                    val_style = f"bold {P.FIRST_FOOTFALL_VALUE}"  # bright teal — first footfall bonus
                elif sc.value > 0:
                    val_style = f"bold {P.GOLD}"
                else:
                    val_style = P.LABEL
                tbl.add_row(
                    Text(species_str, style=name_style),
                    Text(sc.genus_localised, style=P.HUD_CYAN),
                    Text(samples_str, style=f"bold {samples_col}"),
                    Text(min_str),
                    Text(travel_str, style=travel_col),
                    Text(value_str, style=val_style),
                )

            # Show any genuses from the DSS that haven't been scanned yet
            _bidx2 = s._bodies_by_name.get(body_name, -1)
            _binfo = s.bodies[_bidx2] if 0 <= _bidx2 < len(s.bodies) else None
            if _binfo and _binfo.bio_genuses:
                scanned_genera = {sc.genus_localised.lower() for sc in scans}
                for g in _binfo.bio_genuses:
                    if g.lower() not in scanned_genera:
                        _key = g.lower().split()[0] if g else ""
                        lo, hi = _BIO_GENUS_VALUE_RANGE.get(_key, (0, 0))
                        val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
                        tbl.add_row(
                            Text("?", style=P.DIM),
                            Text(g, style=P.HUD_CYAN),
                            Text("—", style=P.DIM),
                            Text("—", style=P.DIM),
                            Text("—", style=P.DIM),
                            Text(val_s, style=P.AMBER),
                        )

            parts.append(tbl)

    if total_known > 0:
        parts.append(Text("\n"))
        footer = Text()
        footer.append("Total confirmed: ", style=P.LABEL)
        footer.append(_fmt_value(total_known), style=f"bold {P.GOLD}")
        parts.append(footer)

    return Group(*parts)


