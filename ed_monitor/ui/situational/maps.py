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


_BRAILLE_BIT = [
    [1,   8],   # row 0: left=bit0, right=bit3
    [2,   16],  # row 1: left=bit1, right=bit4
    [4,   32],  # row 2: left=bit2, right=bit5
    [64,  128], # row 3: left=bit6, right=bit7
]

# Color priority — higher number wins when two elements share a cell

_BRAILLE_PRIO: dict[str, int] = {
    P.DIM:       1,
    P.LABEL:     2,
    P.HUD_CYAN:  3,
    P.ANALYSIS:  4,
    P.AMBER:     5,
    P.PURPLE:    5,
    P.HUD_GREEN: 6,
    P.GOLD:      8,
    "white":     9,
}



def _bc_new(W: int, H: int) -> tuple[list[list[bool]], list[list[str]]]:
    """Allocate a (dots, colors) braille canvas of W×H terminal characters."""
    dots   = [[False] * (W * 2) for _ in range(H * 4)]
    colors = [[""] * W for _ in range(H)]
    return dots, colors



def _bc_set(
    dots:   list[list[bool]],
    colors: list[list[str]],
    px: int, py: int,
    color: str, prio: int,
) -> None:
    """Set a dot at pixel (px, py) with the given color/priority."""
    h4 = len(dots)
    w2 = len(dots[0]) if dots else 0
    if 0 <= py < h4 and 0 <= px < w2:
        dots[py][px] = True
        cx, cy = px // 2, py // 4
        if prio > _BRAILLE_PRIO.get(colors[cy][cx], 0):
            colors[cy][cx] = color



def _bc_cross(
    dots: list[list[bool]], colors: list[list[str]],
    px: int, py: int, color: str, prio: int, size: int = 1,
) -> None:
    """Draw a cross (horizontal + vertical arms) at pixel (px, py)."""
    for d in range(-size, size + 1):
        _bc_set(dots, colors, px + d, py, color, prio)
        _bc_set(dots, colors, px, py + d, color, prio)



def _bc_circle(
    dots: list[list[bool]], colors: list[list[str]],
    cx: int, cy: int, r: int, color: str, prio: int, steps: int = 80,
) -> None:
    """Draw a circle of radius r at center (cx, cy)."""
    import math
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        _bc_set(dots, colors, cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle)), color, prio)



def _bc_render(dots: list[list[bool]], colors: list[list[str]], W: int, H: int) -> Text:
    """Encode the colored braille canvas to a Rich Text object."""
    t = Text()
    for row in range(H):
        for col in range(W):
            bits = 0
            for dr in range(4):
                for dc in range(2):
                    if dots[row * 4 + dr][col * 2 + dc]:
                        bits |= _BRAILLE_BIT[dr][dc]
            if bits:
                t.append(chr(0x2800 + bits), style=colors[row][col] or "white")
            else:
                t.append(" ")
        if row < H - 1:
            t.append("\n")
    return t


# ── Galaxy map renderer ────────────────────────────────────────────────────────

# Correct ED galaxy coordinates (x, z in ly; y is galactic height)

_GALAXY_LANDMARKS = [
    # (x_ly, z_ly, label, color, priority)
    (25.22,    25899.97, "Sgr A*",  P.AMBER,  5),
    (-9530.5,  19808.0,  "Colonia", P.PURPLE, 5),
]



def _render_system_map(s: AppState, standalone: bool = False) -> RenderableType | None:
    """System bodies diagram: *---O-o-o---O-o---O---*---O---
    Returns None if no bodies are available yet.
    standalone=True adds a system name header for the MAP sub-screen."""
    _sys     = s.system
    # Single-pass categorisation + short-name cache (avoids 3 separate list comprehensions)
    _sn_cache: dict[str, str] = {}
    def _sn(b: BodyInfo) -> str:
        n = _sn_cache.get(b.name)
        if n is None:
            _sn_cache[b.name] = n = _short_name(b.name, _sys)
        return n

    _raw_stars:   list[BodyInfo] = []
    _raw_planets: list[BodyInfo] = []
    _raw_moons:   list[BodyInfo] = []
    for _b in s.bodies:
        if _b.star_type:
            _raw_stars.append(_b)
        elif _b.planet_class:
            if _b.level <= 1:
                _raw_planets.append(_b)
            else:
                _raw_moons.append(_b)

    _s_stars   = sorted(_raw_stars,   key=lambda b: (0 if not _sn(b).strip() else 1, _natural_key(_sn(b).strip())))
    _s_planets = sorted(_raw_planets, key=lambda b: _natural_key(_sn(b)))
    _s_moons   = sorted(_raw_moons,   key=lambda b: _natural_key(_sn(b)))

    if not (_s_stars or _s_planets):
        if standalone:
            t = Text()
            t.append("No bodies scanned yet.\n", style=P.LABEL)
            t.append("Use FSS to scan the system.", style=f"dim {P.LABEL_DIM}")
            return t
        return None

    diag = Text()
    if standalone:
        diag.append(f"{_sys}\n", style=f"bold {P.HEADER}")
        diag.append("\nSYSTEM DIAGRAM\n", style="bold " + P.HEADER)
    else:
        diag.append("\nSYSTEM\n", style="bold " + P.HEADER)

    # Map star short-name key → BodyInfo (reuse _sn cache)
    star_index: dict[str, BodyInfo] = {
        _sn(b).strip(): b for b in _s_stars
    }
    # Primary star key is "" (system name == body name); sort primary first
    sorted_star_keys = sorted(star_index.keys(),
                              key=lambda k: (1 if k else 0, _natural_key(k)))

    # Which star does each planet belong to?  Match longest alpha prefix.
    # Barycentre planets (multi-letter prefix like AB) are collected separately.
    star_planets: dict[str, list[BodyInfo]] = {k: [] for k in star_index}
    primary_key  = sorted_star_keys[0] if sorted_star_keys else ""
    barycentre_planets: list[BodyInfo] = []
    for p in _s_planets:
        p_short = _sn(p).strip()
        tok     = p_short.split()
        if tok and tok[0].isalpha() and len(tok[0]) > 1:
            barycentre_planets.append(p)
            continue
        assigned = False
        for length in range(len(tok) - 1, 0, -1):
            candidate = " ".join(tok[:length])
            if candidate in star_index:
                star_planets[candidate].append(p)
                assigned = True
                break
        if not assigned:
            star_planets.setdefault(primary_key, []).append(p)
    barycentre_planets.sort(key=lambda b: _natural_key(_sn(b)))

    # Which planet does each moon belong to?  Remove last token.
    planet_moons: dict[str, list[BodyInfo]] = {}
    for m in _s_moons:
        m_short = _sn(m).strip()
        mtok    = m_short.split()
        pk      = " ".join(mtok[:-1]) if len(mtok) > 1 else primary_key
        planet_moons.setdefault(pk, []).append(m)

    # ── Build ruler ─────────────────────────────────────────────────────
    ruler_chars: list[tuple[str, str]] = []
    body_pos:    list[tuple[int, BodyInfo]] = []

    def _emit(ch: str, style: str, body: BodyInfo | None = None) -> None:
        idx = len(ruler_chars)
        ruler_chars.append((ch, style))
        if body is not None:
            body_pos.append((idx, body))

    def _sep(n: int) -> None:
        for _ in range(n):
            _emit("-", "rgb(55,55,55)")

    def _planet_col(body: BodyInfo) -> str:
        if body.landable and body.surface_gravity > 0:
            g = body.surface_gravity / 9.80665
            if g >= 3.0:
                return f"bold {P.HIGH_G_CRIT}"
            if g >= 1.5:
                return f"bold {P.HIGH_G_WARN}"
        return f"bold {_body_color(body.planet_class, body.star_type)}"

    first_star = True
    for sk in sorted_star_keys:
        sb  = star_index[sk]
        col = _body_color(sb.planet_class, sb.star_type)
        if not first_star:
            _sep(3)
        first_star = False
        _emit("*", f"bold {col}", sb)

        sp = sorted(star_planets.get(sk, []),
                    key=lambda b: _natural_key(_short_name(b.name, _sys)))
        for planet in sp:
            _sep(3)
            p_short = _short_name(planet.name, _sys).strip()
            _emit("O", _planet_col(planet), planet)
            for moon in sorted(planet_moons.get(p_short, []),
                               key=lambda b: _natural_key(_short_name(b.name, _sys))):
                _sep(1)
                _emit("o", _planet_col(moon), moon)

    for planet in barycentre_planets:
        _sep(3)
        p_short = _short_name(planet.name, _sys).strip()
        _emit("O", _planet_col(planet), planet)
        for moon in sorted(planet_moons.get(p_short, []),
                           key=lambda b: _natural_key(_short_name(b.name, _sys))):
            _sep(1)
            _emit("o", _planet_col(moon), moon)

    W = len(ruler_chars)
    if W:
        from collections import defaultdict as _dd_diag
        _diag_bio_done: dict = _dd_diag(int)
        for _dsc in s.bio_scans:
            if _dsc.complete:
                _diag_bio_done[_dsc.body] += 1
        _bio_complete_bodies: set = {
            b.name for b in s.bodies
            if b.bio_signals > 0 and _diag_bio_done.get(b.name, 0) >= b.bio_signals
        }

        max_width = 60
        num_parts = max(1, (W + max_width - 1) // max_width)

        def _last_label(b: BodyInfo) -> str:
            short = _short_name(b.name, _sys).strip()
            return short.split()[-1] if short else "A"

        for part_idx in range(num_parts):
            start = part_idx * max_width
            end = min((part_idx + 1) * max_width, W)

            row1 = Text("  ")
            for i in range(start, end):
                ch, style = ruler_chars[i]
                row1.append(ch, style=style)
            row1.append("\n")

            name_arr  = [" "] * (end - start)
            name_body = [None] * (end - start)
            for pos, b in body_pos:
                if start <= pos < end:
                    lbl = _last_label(b)
                    rel_pos = pos - start
                    placed = False
                    # Try shifting left/right to avoid collisions
                    for shift in (0, -1, 1, -2, 2):
                        rp = rel_pos + shift
                        if rp < 0 or rp + len(lbl) > len(name_arr):
                            continue
                        if all(name_arr[rp + i] == " " for i in range(len(lbl))):
                            for i, ch in enumerate(lbl):
                                name_arr[rp + i] = ch
                                name_body[rp + i] = b
                            placed = True
                            break
                    if not placed:
                        # Collision — place what we can and mark with +
                        for i, ch in enumerate(lbl):
                            if rel_pos + i < len(name_arr) and name_arr[rel_pos + i] == " ":
                                name_arr[rel_pos + i] = ch
                                name_body[rel_pos + i] = b
                        if rel_pos < len(name_arr) and name_arr[rel_pos] == " ":
                            name_arr[rel_pos] = "+"
                            name_body[rel_pos] = b
            row2 = Text("  ")
            for ch, b in zip(name_arr, name_body):
                style = (f"bold {P.HUD_GREEN}") if (b and b.mapped) else P.LABEL_LIGHT
                row2.append(ch, style=style)
            row2.append("\n")

            notable_arr = [" "] * (end - start)
            for pos, b in body_pos:
                if start <= pos < end:
                    if (b.planet_class in ("Earthlike body", "Water world", "Ammonia world")
                            or b.terraform or b.value > 1_000_000):
                        notable_arr[pos - start] = "+"
            has_notable = any(c != " " for c in notable_arr)

            bio_cells: list[tuple[str, bool]] = [(" ", False)] * (end - start)
            has_bio = False
            for pos, b in body_pos:
                if start <= pos < end and b.bio_signals > 0:
                    complete = b.name in _bio_complete_bodies
                    bio_cells[pos - start] = ("✓" if complete else str(b.bio_signals), complete)
                    has_bio = True

            diag.append_text(row1)
            diag.append_text(row2)
            if has_notable:
                row3 = Text("  ")
                row3.append("".join(notable_arr) + "\n", style=f"bold {P.GOLD}")
                diag.append_text(row3)
            if has_bio:
                row4 = Text("  ")
                for ch, complete in bio_cells:
                    if ch == " ":
                        row4.append(ch)
                    elif complete:
                        row4.append(ch, style=f"bold {P.HUD_GREEN}")
                    else:
                        row4.append(ch, style="rgb(0,200,80)")
                row4.append("\n")
                diag.append_text(row4)

            if part_idx < num_parts - 1:
                diag.append("\n")

    if standalone:
        # Legend
        legend = Text()
        legend.append("\n  * star   O planet   o moon\n", style=f"dim {P.LABEL_DIM}")
        legend.append("  + notable body   ✓/N bio signals\n", style=f"dim {P.LABEL_DIM}")
        legend.append("  green = DSS mapped   orange/red = high-G\n", style=f"dim {P.LABEL_DIM}")
        diag.append_text(legend)

    return diag



def _render_galaxy(s: AppState, regional: bool = False,
                   panel_w: int = 60, panel_h: int = 30) -> RenderableType:
    """Top-down galactic map rendered in Braille Unicode with per-cell coloring."""
    import math
    from rich.panel import Panel

    # Reserve rows for: Panel title border (1) + bottom border (1) + legend (1) + route (1) = 4
    # Panel border chars per side = 1 → canvas width = panel_w - 2
    W = max(24, panel_w - 2)
    H = max(10, panel_h - 4)
    DW, DH = W * 2, H * 4
    dots, cg = _bc_new(W, H)

    px_ly, _, pz_ly = s.star_pos if s.star_pos else (0.0, 0.0, 0.0)

    # Galactic center (Sgr A*) — center the galactic view here so the full disk is visible
    _GC_X, _GC_Z = 25.22, 25899.97

    if regional:
        half_range = 1_000.0
        cx, cz = px_ly, pz_ly
    else:
        half_range = 65_000.0
        cx, cz = _GC_X, _GC_Z   # center on galactic core, not Sol

    def to_px(x_ly: float, z_ly: float) -> tuple[int, int]:
        nx = (x_ly - cx + half_range) / (2 * half_range)
        nz = (z_ly - cz + half_range) / (2 * half_range)
        return int(nx * (DW - 1)), int((1.0 - nz) * (DH - 1))

    legend: list[tuple[str, str]] = []

    # ── Galactic scale: galaxy disk outline + Sol + landmarks ─────────────────
    if not regional:
        # Draw galactic disk outline (~52,000 ly radius from galactic center)
        gc_r = 52_000.0
        steps = 400
        for i in range(steps):
            angle = 2 * math.pi * i / steps
            lx = _GC_X + gc_r * math.cos(angle)
            lz = _GC_Z + gc_r * math.sin(angle)
            dx, dz = to_px(lx, lz)
            if 0 <= dx < DW and 0 <= dz < DH:
                _bc_set(dots, cg, dx, dz, P.DIM, 1)

        _bc_cross(dots, cg, *to_px(0.0, 0.0), P.HUD_CYAN, 4, size=2)
        legend.append((P.HUD_CYAN, "⊕ Sol"))
        for lx, lz, name, color, prio in _GALAXY_LANDMARKS:
            _bc_cross(dots, cg, *to_px(lx, lz), color, prio, size=1)
            legend.append((color, f"● {name}"))

    # ── Route waypoints ────────────────────────────────────────────────────────
    for wp in (s.route_list or []):
        sp = wp.get("StarPos")
        if isinstance(sp, list) and len(sp) >= 3:
            wp_px = to_px(sp[0], sp[2])
            _bc_set(dots, cg, wp_px[0], wp_px[1], P.HUD_CYAN, 3)

    # Destination (last waypoint highlighted)
    if s.route_destination and s.route_list:
        dest_sp = s.route_list[-1].get("StarPos")
        if isinstance(dest_sp, list) and len(dest_sp) >= 3:
            _bc_cross(dots, cg, *to_px(dest_sp[0], dest_sp[2]), P.HUD_GREEN, 6, size=1)
            legend.append((P.HUD_GREEN, f"★ {s.route_destination}"))

    # ── Player position ────────────────────────────────────────────────────────
    _bc_cross(dots, cg, *to_px(px_ly, pz_ly), P.GOLD, 8, size=2)
    legend.append((P.GOLD, "◈ You"))

    # ── Build canvas text and wrap in Panel ────────────────────────────────────
    canvas_text = _bc_render(dots, cg, W, H)

    scale_str = f"±{int(half_range/1000)}k ly" if half_range >= 1000 else f"±{int(half_range)} ly"
    mode_str  = "regional" if regional else "galactic"
    title_str = f"GALAXY  {scale_str} ({mode_str})"

    title_line = Text()
    title_line.append(f"  {title_str}\n", style=f"bold {P.HEADER}")
    framed = Group(title_line, canvas_text)

    # ── Legend and route info ─────────────────────────────────────────────────
    leg_text = Text()
    for i, (col, lbl) in enumerate(legend):
        if i:
            leg_text.append("  ")
        leg_text.append(lbl, style=col)

    parts: list[RenderableType] = [framed]
    if leg_text.plain:
        parts.append(leg_text)
    if s.route_hops > 0:
        route_text = Text()
        word = "jump" if s.route_hops == 1 else "jumps"
        route_text.append(f"{s.route_hops} {word} remaining", style=P.LABEL)
        if s.route_destination:
            route_text.append(f" → {s.route_destination}", style=P.HUD_GREEN)
        parts.append(route_text)

    return Group(*parts)


# ── Situational panel ─────────────────────────────────────────────────────────

