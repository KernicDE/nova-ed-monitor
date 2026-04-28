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

from .docking import _render_docking


def _render_overview(s: AppState, panel_h: int = 20, panel_w: int = 40) -> RenderableType:
    """Dashboard overview: session stats, wallet, navigation, notable bodies, activity."""
    import math
    from collections import defaultdict as _dd2

    parts: list[RenderableType] = []

    # ── Row budget ─────────────────────────────────────────────────────────────
    fixed_rows = 1 + 1 + 1 + 1 + 1  # session + wallet + nav + body_hdr + body_tbl_hdr
    separators = 2
    extra = panel_h - fixed_rows - separators
    max_body_rows = max(3, min(extra, 8))
    remaining = extra - max_body_rows

    show_scan_prog = remaining >= 1
    show_activity = remaining >= 2
    show_carrier = remaining >= 3
    show_neutron = remaining >= 4

    HDR = "bold " + P.HEADER

    # ── Session strip (always) ─────────────────────────────────────────────────
    session_txt = Text()
    session_txt.append("SESSION  ", style=HDR)
    if s.session_jumps or s.session_first_disc or s.session_mapped or s.session_value:
        chunks: list[tuple[str, str]] = []
        chunks.append((f"{s.session_jumps} jumps", "white"))
        if s.session_first_disc:
            chunks.append((f"{s.session_first_disc} FD", P.GOLD))
        if s.session_mapped:
            chunks.append((f"{s.session_mapped} mapped", P.HUD_GREEN))
        if s.session_value:
            chunks.append((f"{_fmt_cr_compact(s.session_value)}", "white"))
        if s.session_start_ts:
            mins = int((time.time() - s.session_start_ts) / 60)
            if mins >= 60:
                dur = f"{mins//60}h {mins%60}m"
            else:
                dur = f"{mins}m"
            chunks.append((dur, P.LABEL))
        for i, (txt, col) in enumerate(chunks):
            if i:
                session_txt.append("  ·  ", style=P.LABEL)
            session_txt.append(txt, style=col)
    else:
        session_txt.append("—", style=P.DIM)
    parts.append(session_txt)

    # ── Wallet strip (always) ──────────────────────────────────────────────────
    wallet_txt = Text()
    wallet_txt.append("WALLET   ", style=HDR)
    if s.credits:
        wallet_txt.append(f"{_fmt_cr_compact(s.credits)} Cr", style="white")
    else:
        wallet_txt.append("—", style=P.DIM)
    if s.cargo_capacity > 0:
        wallet_txt.append("  ·  ", style=P.LABEL)
        wallet_txt.append(f"Cargo {s.cargo}/{s.cargo_capacity} t", style="white")
    missions_active = len(s.missions)
    if missions_active:
        wallet_txt.append("  ·  ", style=P.LABEL)
        word = "mission" if missions_active == 1 else "missions"
        wallet_txt.append(f"{missions_active} {word}", style=P.HUD_CYAN)
    parts.append(wallet_txt)

    # ── Navigation + Position (1–2 rows) ───────────────────────────────────────
    nav_parts: list[RenderableType] = []

    route_txt = Text()
    route_txt.append("NAV      ", style=HDR)
    if s.route_destination:
        route_txt.append("→ ", style=P.LABEL)
        route_txt.append(s.route_destination, style="bold white")
        route_txt.append(f"  {s.route_hops}j", style=P.AMBER)
        if s.route_next:
            route_txt.append("  ·  Next ", style=P.LABEL)
            route_txt.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                mark = " ⛽" if s.route_next_scoopable else " ✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                route_txt.append(f" {s.route_next_star}{mark}", style=f"bold {star_col}")
    else:
        route_txt.append("No route", style=P.AMBER_DIM)

    pos_txt = Text()
    pos_txt.append("POS      ", style=HDR)
    if s.star_pos:
        x, y, z = s.star_pos
        dist_sol = math.sqrt(x**2 + y**2 + z**2)
        core_x, core_y, core_z = 25.21875, -20.90625, 25899.96875
        dist_core = math.sqrt((x - core_x)**2 + (y - core_y)**2 + (z - core_z)**2)
        pos_txt.append(f"Sol {dist_sol/1000:.1f}k ly", style="white")
        pos_txt.append("  ·  ", style=P.LABEL)
        pos_txt.append(f"Core {dist_core/1000:.1f}k ly", style="white")
    else:
        pos_txt.append("—", style=P.DIM)

    if panel_w >= 50:
        nav_grid = Table.grid(padding=(0, 1), expand=True)
        nav_grid.add_column(ratio=1)
        nav_grid.add_column(ratio=1)
        nav_grid.add_row(route_txt, pos_txt)
        nav_parts.append(nav_grid)
    else:
        nav_parts.append(route_txt)
        nav_parts.append(pos_txt)

    parts.append(Text(""))  # separator
    parts.extend(nav_parts)
    parts.append(Text(""))  # separator

    # ── Notable bodies ─────────────────────────────────────────────────────────
    def _is_notable(b: BodyInfo) -> bool:
        if b.planet_class in ("Earthlike body", "Water world", "Ammonia world"):
            return True
        if b.terraform or b.bio_signals > 0:
            return True
        if _body_value(b) > s.notable_value_threshold:
            return True
        if b.unusual_body:
            return True
        return False

    notable = [b for b in s.bodies if _is_notable(b)]
    notable.sort(key=lambda b: _natural_key(_short_name(b.name, s.system)))

    bodies_hdr = Text()
    bodies_hdr.append("NOTABLE BODIES", style=HDR)
    parts.append(bodies_hdr)

    if notable:
        # Pre-compute actual bio values and completion per body
        _bio_done_cnt: dict = _dd2(int)
        _bio_actual_cr: dict = _dd2(int)
        for _sc in s.bio_scans:
            if _sc.complete:
                _bio_done_cnt[_sc.body] += 1
                _bio_actual_cr[_sc.body] += _sc.value

        tbl = _data_table()
        tbl.add_column("Body", style="white", width=8, no_wrap=True)
        tbl.add_column("Type", width=9, no_wrap=True)
        tbl.add_column("Val", width=7, justify="right", no_wrap=True)
        tbl.add_column("G", width=5, justify="right", no_wrap=True)
        tbl.add_column("Bio", width=6, justify="right", no_wrap=True)
        tbl.add_column("Why", width=8, no_wrap=True)

        for b in notable[:max_body_rows]:
            short = _short_name(b.name, s.system)
            btype = _abbrev_type(b.planet_class, b.star_type)
            body_col = _body_color(b.planet_class, b.star_type)
            is_unusual = bool(b.unusual_body)

            has_bio = b.bio_signals > 0
            bio_done_cnt = _bio_done_cnt.get(b.name, 0)
            bio_all_done = has_bio and bio_done_cnt >= b.bio_signals
            actual_bio = _bio_actual_cr.get(b.name, 0) if bio_all_done else 0

            scan_done = b.mapped
            bio_done = bio_all_done or not has_bio
            all_done = scan_done and bio_done
            body_v = _body_value(b)

            if all_done:
                val_s = _fmt_notable_val(body_v)
                vcol = P.GOLD
                bio_s = _fmt_notable_val(actual_bio) if actual_bio > 0 else ("✓" if has_bio else "—")
                bio_c = P.HUD_GREEN
            elif bio_all_done:
                val_s = _fmt_notable_val(body_v)
                vcol = P.AMBER if body_v == 0 else P.GOLD
                bio_s = _fmt_notable_val(actual_bio) if actual_bio > 0 else "✓"
                bio_c = P.GOLD
            else:
                val_s = _fmt_notable_val(body_v)
                vcol = _body_value_color(b)
                if has_bio:
                    if b.bio_value_max > 0:
                        bio_s = f"~{_fmt_cr_compact(b.bio_value_min)}–{_fmt_cr_compact(b.bio_value_max)}"
                        bio_c = P.AMBER
                    elif b.bio_genuses:
                        bio_s = f"{len(b.bio_genuses)}×✓"
                        bio_c = P.AMBER
                    elif b.bio_genuses_predicted:
                        from ..events import _BIO_GENUS_VALUE_RANGE as _BGVR
                        _pred_lo: list[int] = []
                        _pred_hi: list[int] = []
                        for _pg in b.bio_genuses_predicted:
                            _pk = _pg.lower().split()[0] if _pg else ""
                            _lo, _hi = _BGVR.get(_pk, (0, 0))
                            if _lo > 0: _pred_lo.append(_lo)
                            if _hi > 0: _pred_hi.append(_hi)
                        if _pred_hi:
                            _n = max(1, b.bio_signals)
                            _total_lo = sum(sorted(_pred_lo)[:_n])
                            _total_hi = sum(sorted(_pred_hi, reverse=True)[:_n])
                            bio_s = f"?~{_fmt_cr_compact(_total_lo)}–{_fmt_cr_compact(_total_hi)}"
                            bio_c = "rgb(140,130,60)"
                        else:
                            bio_s = f"{b.bio_signals}×?"
                            bio_c = P.LABEL
                    else:
                        bio_s = f"{b.bio_signals}×"
                        bio_c = P.HUD_GREEN
                else:
                    bio_s = "—"
                    bio_c = P.DIM

            if b.landable and b.surface_gravity > 0:
                g_val = b.surface_gravity / 9.80665
                g_s = f"{g_val:.1f}G"
                g_col = (f"bold {P.HIGH_G_CRIT}" if g_val >= 3.0
                         else f"bold {P.HIGH_G_WARN}" if g_val >= 1.5
                         else P.LABEL_LIGHT)
            else:
                g_s = "—"
                g_col = P.DIM

            dim_done = all_done
            name_style = P.LABEL_DIM if dim_done else P.WHITE
            type_prefix = "! " if is_unusual else ""
            type_style = P.LABEL_DIM if dim_done else (
                f"bold {P.HIGH_G_WARN}" if is_unusual else f"bold {body_col}"
            )

            why_parts = []
            if b.planet_class == "Earthlike body": why_parts.append("ELW")
            if b.planet_class == "Water world": why_parts.append("WW")
            if b.planet_class == "Ammonia world": why_parts.append("AW")
            if b.terraform: why_parts.append("TF")
            if b.bio_signals > 0: why_parts.append(f"{b.bio_signals}B")
            if body_v > s.notable_value_threshold: why_parts.append("HV")
            if b.unusual_body: why_parts.append(b.unusual_body)
            why_str = ", ".join(why_parts)

            tbl.add_row(
                Text(short, style=name_style),
                Text(type_prefix + btype, style=type_style),
                Text(val_s, style=vcol),
                Text(g_s, style=g_col),
                Text(bio_s, style=bio_c),
                Text(why_str, style=P.LABEL),
            )
        parts.append(tbl)
        if len(notable) > max_body_rows:
            more = Text(f"+{len(notable) - max_body_rows} more", style=f"dim {P.DIM}")
            parts.append(more)
    else:
        parts.append(Text("No notable bodies.", style=P.DIM))

    # ── Activity summary (conditional) ─────────────────────────────────────────
    if show_activity:
        activity_parts: list[RenderableType] = []

        # BGS
        if s.bgs_log:
            bgs_txt = Text()
            bgs_txt.append("BGS  ", style=HDR)
            first_sys = next(iter(s.bgs_log))
            first_fac = next(iter(s.bgs_log[first_sys]))
            acts = s.bgs_log[first_sys][first_fac]
            act_str = ", ".join(f"{v}×{k}" for k, v in sorted(acts.items(), key=lambda x: -x[1])[:3])
            bgs_txt.append(f"{first_fac[:18]}  ", style="white")
            bgs_txt.append(act_str, style=P.LABEL)
            activity_parts.append(bgs_txt)

        # PowerPlay
        if s.pp_power:
            pp_txt = Text()
            pp_txt.append("PP   ", style=HDR)
            rank_str = f" R{s.pp_rank}" if s.pp_rank > 0 else ""
            pp_txt.append(f"{s.pp_power}{rank_str}", style="white")
            if s.pp_total_merits > 0:
                pp_txt.append(f"  ·  {_de(s.pp_total_merits)}", style="rgb(180,130,255)")
                if s.pp_session_merits > 0:
                    pp_txt.append(f" (+{_de(s.pp_session_merits)})", style=P.LABEL)
            activity_parts.append(pp_txt)

        # Nearest inhabited
        if s.nearest_populated_name and s.population == 0:
            inh_txt = Text()
            inh_txt.append("Near ", style=HDR)
            inh_txt.append(s.nearest_populated_name, style=P.HUD_CYAN)
            if s.nearest_populated_dist > 0:
                inh_txt.append(f"  {s.nearest_populated_dist:.0f} ly", style="white")
            jrange = s.jump_range_last or s.jump_range
            if jrange > 0 and s.nearest_populated_dist > 0:
                jumps_est = math.ceil(s.nearest_populated_dist / jrange)
                inh_txt.append(f"  ~{jumps_est}j", style=P.LABEL)
            activity_parts.append(inh_txt)

        if activity_parts:
            parts.append(Text(""))  # separator
            for ap in activity_parts:
                parts.append(ap)

    # ── System scan progress (conditional) ─────────────────────────────────────
    if show_scan_prog and s.bodies:
        mapped_count = sum(1 for b in s.bodies if b.mapped)
        from collections import defaultdict as _dd3
        complete_by_body = _dd3(int)
        for _sc in s.bio_scans:
            if _sc.complete:
                complete_by_body[_sc.body] += 1
        bio_done_count = sum(
            min(complete_by_body.get(b.name, 0), b.bio_signals)
            for b in s.bodies if b.bio_signals > 0
        )
        bio_total = sum(b.bio_signals for b in s.bodies if b.bio_signals > 0)
        fss_done = len({b.name for b in s.bodies if b.fss_scanned and (b.planet_class or b.star_type)})

        scan_txt = Text()
        scan_txt.append("Scan  ", style=HDR)
        if s.fss_body_count:
            scan_txt.append(f"FSS {fss_done}/{s.fss_body_count}  ", style="white")
        else:
            scan_txt.append(f"FSS {fss_done}  ", style="white")
        scan_txt.append(f"Mapped {mapped_count}  ", style="white")
        if bio_total:
            scan_txt.append(f"Bio {bio_done_count}/{bio_total}", style=P.HUD_GREEN if bio_done_count >= bio_total else "white")
        parts.append(scan_txt)

    # ── Fleet carrier (conditional) ────────────────────────────────────────────
    if show_carrier and s.carriers_current_system:
        nearest = min(s.carriers_current_system, key=lambda c: c.get("dist_ls", float("inf")))
        c = nearest
        c_name = c.get("name", "")
        c_dist_ls = c.get("dist_ls", 0.0)
        c_system = c.get("system_name", "")
        in_current = c_system and c_system.lower() == s.system.lower()
        if in_current and c_dist_ls > 0:
            c_dist_str = _fmt_ls_compact(c_dist_ls)
        else:
            c_dist_str = ""
            if s.star_pos:
                c_x, c_y, c_z = c.get("sys_x", 0.0), c.get("sys_y", 0.0), c.get("sys_z", 0.0)
                if c_x or c_y or c_z:
                    px, py, pz = s.star_pos
                    ly_dist = math.sqrt((px-c_x)**2 + (py-c_y)**2 + (pz-c_z)**2)
                    c_dist_str = f"{ly_dist:.0f} ly"

        svc_icons = ""
        if c.get("market"): svc_icons += "M"
        if c.get("shipyard"): svc_icons += "S"
        if c.get("outfitting"): svc_icons += "O"
        if c.get("rearm"): svc_icons += "R"
        if c.get("refuel"): svc_icons += "F"
        if c.get("repair"): svc_icons += "r"

        car_txt = Text()
        car_txt.append("Carrier  ", style=HDR)
        car_txt.append(c_name, style=f"bold {P.AMBER}")
        if c_dist_str:
            car_txt.append(f"  {c_dist_str}", style=P.LABEL)
        if svc_icons:
            car_txt.append(f"  [{svc_icons}]", style=P.LABEL_LIGHT)
        parts.append(car_txt)

    # ── Neutron route (conditional) ────────────────────────────────────────────
    if show_neutron and s.neutron_route:
        ntr_txt = Text()
        ntr_txt.append("Neutron  ", style=HDR)
        ntr_txt.append(f"→ {s.neutron_route_to or '?'}", style=P.HUD_CYAN)
        ntr_txt.append(f"  {len(s.neutron_route)} jumps", style="white")
        if s.neutron_route_status and s.neutron_route_status != "done":
            ntr_txt.append(f"  ({s.neutron_route_status})", style=P.AMBER)
        parts.append(ntr_txt)

    # ── Docking diagram (transient, only when landing) ───────────────────────
    if s.docked_pad > 0:
        parts.append(Text(""))  # separator
        dock = _render_docking(s, panel_w=panel_w, panel_h=max(12, panel_h // 3))
        parts.append(dock)

    if not parts:
        return Text("No data.", style=P.LABEL)
    return Group(*parts)


