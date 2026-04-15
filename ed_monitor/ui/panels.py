from __future__ import annotations

import re
import textwrap
import time
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version
from typing import Optional

try:
    _NOVA_VERSION = _pkg_version("nova-ed-monitor")
except Exception:
    _NOVA_VERSION = "?"

from rich.align import Align
from rich.columns import Columns
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widget import Widget

from ..state import AppState, BioScan, BodyInfo, EngineerInfo, EventCategory
from . import palette as P


# ── Shared helpers ────────────────────────────────────────────────────────────

def _short_name(body: str, system: str) -> str:
    if body.lower().startswith(system.lower()):
        short = body[len(system):].strip()
        return short
    return body


def _natural_key(s: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


_NNBSP = "\u202F"  # narrow no-break space — German ISO 80000-1 thousands separator


def _de(n: int) -> str:
    return f"{n:,}".replace(",", _NNBSP)


def _fmt_value(v: int) -> str:
    if v == 0: return "—"
    return f"{_de(v)} Cr"


def _fmt_ls(ls: float) -> str:
    if ls <= 0.0: return "0 ls"
    return f"{_de(int(ls))} ls"


def _fmt_metres(m: float) -> str:
    if m >= 1_000.0: return f"{m/1_000:.1f} km"
    return f"{m:.0f} m"


def _fmt_value_short(v: int) -> str:
    if v == 0: return "—"
    return f"{v:,}".replace(",", _NNBSP)


def _fmt_cr_compact(v: int) -> str:
    """Abbreviated credit value for tight columns (e.g. '3.4M', '500K')."""
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)


def _fmt_notable_val(v: int) -> str:
    """Credit value for notable bodies table: compact only above 1M, full number below."""
    if v <= 0:           return "—"
    if v >= 1_000_000:   return _fmt_cr_compact(v)
    return _de(v)


def _fmt_ls_compact(ls: float) -> str:
    if ls <= 0: return "—"
    if ls >= 100:            return f"{int(ls):,}".replace(",", _NNBSP) + " ls"
    return f"{ls:.0f} ls"


def _fmt_ago(iso: str) -> str:
    """Return human-readable 'X ago' string from an ISO-8601 timestamp."""
    if not iso:
        return ""
    try:
        from datetime import timezone as _tz
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(_tz.utc) - dt
        secs = int(diff.total_seconds())
        if secs < 0:     return ""
        if secs < 3600:  return f"{secs//60}m ago"
        if secs < 86400: return f"{secs//3600}h ago"
        return f"{secs//86400}d ago"
    except Exception:
        return ""


def _fmt_pop(n: int) -> str:
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
    if n >= 1_000:         return f"{n/1_000:.1f}K"
    return str(n)


def _pl(n: int) -> str:
    return "" if n == 1 else "s"


def _pip_bar(value: float, col: str) -> Text:
    """Render a pip bar for power distribution (0.0–4.0, 0.5 steps).
    Uses ● full, ◑ half, ○ empty; always 4 pips wide."""
    import math
    t     = Text()
    full  = int(value)
    half  = 1 if (value - full) >= 0.5 else 0
    empty = 4 - full - half
    t.append("●" * full,  style=f"bold {col}")
    if half:
        t.append("◑", style=f"bold {col}")
    t.append("○" * empty, style="rgb(60,60,60)")
    return t


def _power_state_color(state: str) -> str:
    return {
        "Control":    P.HUD_CYAN,
        "Exploited":  P.AMBER,
        "Fortified":  P.HUD_GREEN,
        "Stronghold": P.HUD_GREEN,
        "Contested":  P.HUD_WARN,
        "Turmoil":    P.HUD_CRIT,
        "HomeSystem": "bold white",
    }.get(state, P.WHITE)


def _abbrev_type(planet: str, star: str) -> str:
    if star:
        return {
            "N": "Neutron Star",
            "H": "Black Hole",
        }.get(star) or ("White Dwarf" if star.startswith("D") else f"{star} Star")
    return {
        "Earthlike body":                    "Earthlike",
        "Water world":                       "Water",
        "Ammonia world":                     "Ammonia",
        "High metal content body":           "HMC",
        "Metal rich body":                   "M-Rich",
        "Rocky body":                        "Rocky",
        "Rocky ice body":                    "Rky Ice",
        "Icy body":                          "Icy",
        "Class I gas giant":                 "Gas-I",
        "Sudarsky class I gas giant":        "Gas-I",
        "Class II gas giant":                "Gas-II",
        "Sudarsky class II gas giant":       "Gas-II",
        "Class III gas giant":               "Gas-III",
        "Sudarsky class III gas giant":      "Gas-III",
        "Class IV gas giant":                "Gas-IV",
        "Sudarsky class IV gas giant":       "Gas-IV",
        "Class V gas giant":                 "Gas-V",
        "Sudarsky class V gas giant":        "Gas-V",
        "Helium-rich gas giant":             "Gas-He",
        "Helium rich gas giant":             "Gas-He",
        "Gas giant with water-based life":   "Gas-H2O",
        "Gas giant with water based life":   "Gas-H2O",
        "Gas giant with ammonia-based life": "Gas-NH3",
        "Gas giant with ammonia based life": "Gas-NH3",
        "Water giant":                       "Water Giant",
    }.get(planet, planet)


def _planet_char(planet: str) -> str:
    """Single-char type indicator for SYSTEM ruler."""
    if planet == "Earthlike body":           return "E"
    if planet == "Water world":              return "W"
    if planet == "Ammonia world":            return "A"
    if planet == "High metal content body":  return "H"
    if planet == "Metal rich body":          return "M"
    if planet == "Rocky body":               return "R"
    if planet == "Rocky ice body":           return "r"
    if planet == "Icy body":                 return "I"
    if "gas" in planet.lower():              return "G"
    return "●"


def _body_color(planet: str, star: str) -> str:
    if star:
        if star == "N":                return P.HUD_CYAN
        if star == "H":                return "rgb(180,50,180)"
        if star.startswith("D"):       return "rgb(190,190,190)"
        if star in ("O", "B"):         return "rgb(130,160,235)"
        if star in ("A", "F"):         return P.WHITE
        if star in ("G", "K"):         return "rgb(235,185,60)"
        if star == "M":                return "rgb(235,90,50)"
        return "rgb(220,185,60)"
    if planet == "Earthlike body":           return "rgb(70,195,90)"
    if planet == "Water world":              return "rgb(70,165,235)"
    if planet == "Ammonia world":            return "rgb(205,185,50)"
    if planet == "Metal rich body":          return "rgb(200,90,235)"
    if planet == "High metal content body":  return "rgb(90,145,235)"
    if "gas" in planet.lower():              return "rgb(90,120,185)"
    return P.LABEL


def _gauge_bar(ratio: float, width: int, col_full: str, col_empty: str = P.DIM) -> Text:
    ratio  = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    empty  = width - filled
    t = Text()
    t.append("█" * filled, style=col_full)
    t.append("░" * empty,  style=col_empty)
    return t


# Estimated base values (Cr) by planet class
_BODY_EST_VALUES: dict[str, int] = {
    "Earthlike body":                    2_500_000,
    "Water world":                         170_000,
    "Ammonia world":                       235_000,
    "Metal rich body":                     100_000,
    "High metal content body":              22_000,
    "Rocky body":                            3_500,
    "Rocky ice body":                        4_000,
    "Icy body":                              2_500,
    "Sudarsky class I gas giant":            3_500,
    "Sudarsky class II gas giant":          15_000,
    "Sudarsky class III gas giant":          4_500,
    "Sudarsky class IV gas giant":           5_500,
    "Sudarsky class V gas giant":            6_000,
    "Helium rich gas giant":                 3_500,
    "Gas giant with water-based life":      19_000,
    "Gas giant with water based life":      19_000,
    "Gas giant with ammonia-based life":    22_000,
    "Gas giant with ammonia based life":    22_000,
    "Water giant":                           4_000,
}


def _estimated_value(b: BodyInfo) -> int:
    """Base estimated value without bonuses (used as fallback when no scan data)."""
    base = _BODY_EST_VALUES.get(b.planet_class, 0)
    if base > 0 and b.terraform:
        base = int(base * 2.5)
    return base


def _body_value(b: BodyInfo) -> int:
    """Body value including first-discovery (2.6×) and first-mapping (3.3×) bonuses."""
    v = b.value if b.value > 0 else _estimated_value(b)
    if v > 0:
        if b.first_discovered:
            v = int(v * 2.6)
        if b.first_mapped and not b.mapped:
            v = int(v * 3.3)
    return v


def _mission_time_remaining(expiry: str) -> str:
    if not expiry:
        return ""
    try:
        # ED timestamps: "2025-03-08T12:34:56Z" or without Z
        ts = expiry.rstrip("Z")
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        secs  = int(delta.total_seconds())
        if secs < 0:
            return "Expired"
        days  = secs // 86400
        hours = (secs % 86400) // 3600
        mins  = (secs % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return ""


# ── Base class ────────────────────────────────────────────────────────────────

class _Panel(Widget):
    _snap: Optional[AppState] = None

    def update(self, snap: AppState) -> None:
        self._snap = snap
        self.refresh()


# ── System panel ──────────────────────────────────────────────────────────────

class SystemPanel(_Panel):
    BORDER_TITLE = "◈ System"

    DEFAULT_CSS = """
    SystemPanel {
        border: solid rgb(0,175,185);
        border-title-color: rgb(0,175,185);
        border-title-style: bold;
        height: auto;
        min-height: 11;
        width: 1fr;
    }
    """

    _scroll: int = 0

    def scroll_system(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        parts: list[RenderableType] = []

        # System name header
        hdr = Text(justify="center")
        hdr.append(s.system, style="bold white")
        parts.append(hdr)

        # FSS / body counts
        stars   = sum(1 for b in s.bodies if b.star_type)
        planets = sum(1 for b in s.bodies if b.planet_class and b.level <= 1)
        moons   = sum(1 for b in s.bodies if b.planet_class and b.level == 2)
        # Count all bodies that the player has received a Scan event for.
        # Only count bodies with a known type (planet_class or star_type) — this
        # matches FSSDiscoveryScan.BodyCount which excludes asteroid belt clusters.
        # Belt clusters have no planet_class/star_type but can produce Scan events,
        # which would otherwise inflate fss_done above fss_total.
        # Set comprehension on name deduplicates any edge-case double entries.
        fss_done = len({
            b.name for b in s.bodies
            if b.fss_scanned and (b.planet_class or b.star_type)
        })
        fss_total = s.fss_body_count

        # Build two column lists: left = natural/exploration, right = human/BGS
        def _cell(label: str, value: str, vstyle: str = P.WHITE) -> Text:
            t = Text()
            t.append(f"{label} ", style=P.LABEL)
            t.append(value, style=vstyle)
            return t

        left_cells: list[Text]  = []
        right_cells: list[Text] = []

        # Left column — exploration / natural data
        if stars or planets:
            body_parts = [f"{stars}★"]
            if planets: body_parts.append(f"{planets}P")
            if moons:   body_parts.append(f"{moons}M")
            left_cells.append(_cell("Bodies", " ".join(body_parts)))

        if fss_total > 0:
            fss_col = P.HUD_GREEN if fss_done >= fss_total else P.AMBER
            left_cells.append(_cell("FSS", f"{fss_done}/{fss_total}", fss_col))

        if s.system_power:
            pp     = s.system_power
            pp_col = _power_state_color(s.system_power_state)
            if s.system_power_state:
                pp += f" [{s.system_power_state}]"
            left_cells.append(_cell("Power", pp, pp_col))


        # Right column — human/BGS data
        if s.population > 0:
            right_cells.append(_cell("Pop", _fmt_pop(s.population)))
        if s.economy:
            right_cells.append(_cell("Economy", s.economy))
        if s.security:
            sec_col = (P.HUD_GREEN if "High" in s.security
                       else P.HUD_WARN if "Medium" in s.security
                       else P.HUD_CRIT)
            right_cells.append(_cell("Security", s.security, f"bold {sec_col}"))
        if s.government:
            right_cells.append(_cell("Gov", s.government))
        if s.allegiance:
            right_cells.append(_cell("Alleg", s.allegiance))
        if s.controlling_faction:
            faction_str = (
                f"{s.controlling_faction} [{s.controlling_state}]"
                if s.controlling_state and s.controlling_state != "None"
                else s.controlling_faction
            )
            right_cells.append(_cell("Faction", faction_str))
        if s.station_count > 0:
            right_cells.append(_cell("Stations", str(s.station_count)))

        # Build two-column table
        if left_cells or right_cells:
            tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True)
            tbl.add_column("left",  ratio=1)
            tbl.add_column("right", ratio=1)
            rows = max(len(left_cells), len(right_cells))
            for i in range(rows):
                lc = left_cells[i]  if i < len(left_cells)  else Text("")
                rc = right_cells[i] if i < len(right_cells) else Text("")
                tbl.add_row(lc, rc)
            parts.append(tbl)

        # Position footer — single line below the table:
        # [At nearest_body]     [Pos x, y]     [Alt n m]
        pos_parts: list[Text] = []
        if s.nearest_body:
            pos_parts.append(_cell("At", _short_name(s.nearest_body, s.system)))
        if s.lat is not None and s.lon is not None:
            pos_parts.append(_cell("Pos", f"{s.lat:.2f}, {s.lon:.2f}"))
            if s.altitude is not None:
                pos_parts.append(_cell("Alt", f"{s.altitude:,.0f} m"))
        if pos_parts:
            pos_line = Text()
            pos_line.append("\n ")   # blank line + 1-space left margin matching table padding
            for i, p in enumerate(pos_parts):
                if i > 0:
                    pos_line.append("     ")
                pos_line.append_text(p)
            parts.append(pos_line)

        return Group(*parts) if len(parts) > 1 else (parts[0] if parts else Text(""))


# ── Ship panel ────────────────────────────────────────────────────────────────

class ShipPanel(_Panel):
    BORDER_TITLE = "◈ Ship"

    DEFAULT_CSS = """
    ShipPanel {
        border: solid rgb(210,115,0);
        border-title-color: rgb(210,115,0);
        border-title-style: bold;
        height: auto;
        min-height: 11;
        width: 2fr;
    }
    """

    _scroll: int = 0

    def scroll_ship(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()

    def update(self, snap: AppState) -> None:
        self._snap = snap
        on_foot = snap.client_online and not snap.in_main_ship and not snap.in_srv
        if not snap.client_online:
            self.border_title = "◈ Ship — Offline"
        elif on_foot:
            self.border_title = "◈ On Foot"
        elif snap.in_srv:
            self.border_title = "◈ SRV"
        elif snap.in_main_ship:
            if snap.supercruise:
                self.border_title = "◈ Ship — Supercruise"
            elif snap.orbital_cruise:
                self.border_title = "◈ Ship — Glide"
            elif snap.docked:
                self.border_title = "◈ Ship — Docked"
            elif snap.landed:
                self.border_title = "◈ Ship — Landed"
            else:
                self.border_title = "◈ Ship — Flying"
        else:
            self.border_title = "◈ Ship"
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        on_foot = s.client_online and not s.in_main_ship and not s.in_srv
        in_ship = s.in_main_ship
        in_srv  = s.in_srv

        if on_foot:
            return self._render_on_foot(s)
        if in_srv:
            return self._render_srv(s)
        return self._render_ship(s)

    def _render_ship(self, s: AppState) -> RenderableType:
        panel_w = max(10, self.size.width // 3)
        bar_w   = max(4, panel_w - 6)

        header = Text(justify="center")
        if s.ship_type:
            ident     = f" [{s.ship_ident}]" if s.ship_ident else ""
            name_part = f' "{s.ship_name}"'  if s.ship_name  else ""
            header.append(s.ship_type, style=f"bold {P.AMBER}")
            header.append(f"{name_part}{ident}", style=P.LABEL)
        else:
            header.append("Unknown ship", style=P.LABEL)

        hull_pct = int(round(s.hull * 100.0))
        hull_col = P.HUD_GREEN if s.hull > 0.75 else (P.HUD_WARN if s.hull > 0.5 else P.HUD_CRIT)
        hull_txt = Text(justify="center")
        hull_txt.append(f"{hull_pct}%\n", style=f"bold {hull_col}")
        hull_txt.append_text(_gauge_bar(s.hull, bar_w, hull_col))
        hull_panel = Panel(Align.center(hull_txt), title="HULL",
                           border_style=hull_col, padding=(0, 1))

        sh_col   = P.BLUE_SH if s.shields_up else P.HUD_CRIT
        sh_label = "UP" if s.shields_up else "DOWN"
        sh_txt   = Text(justify="center")
        sh_txt.append(f"{sh_label}\n", style=f"bold {sh_col}")
        sh_txt.append_text(_gauge_bar(1.0 if s.shields_up else 0.0, bar_w, sh_col))
        sh_panel = Panel(Align.center(sh_txt), title="SHIELD",
                         border_style=sh_col, padding=(0, 1))

        fuel_max   = s.fuel_max if s.fuel_max > 0.0 else 32.0
        fuel_ratio = min(s.fuel / fuel_max, 1.0)
        fuel_col   = P.HUD_CRIT if s.low_fuel else (P.HUD_WARN if fuel_ratio < 0.5 else P.HUD_GREEN)
        fuel_txt   = Text(justify="center")
        fuel_txt.append(f"{fuel_ratio*100:.0f}%\n", style=f"bold {fuel_col}")
        fuel_txt.append_text(_gauge_bar(fuel_ratio, bar_w, fuel_col))
        fuel_panel = Panel(Align.center(fuel_txt), title="FUEL",
                           border_style=fuel_col, padding=(0, 1))

        parts: list[RenderableType] = [Align.center(header)]

        if s.in_main_ship:
            gauges = Columns([hull_panel, sh_panel, fuel_panel], expand=True, equal=True)
            parts.append(gauges)

            if s.cargo_capacity > 0:
                cargo_w     = max(4, self.size.width - 16)
                cargo_ratio = min(s.cargo / s.cargo_capacity, 1.0)
                cargo_txt   = Text(justify="center")
                cargo_txt.append(f"CARGO {s.cargo}/{s.cargo_capacity}  ", style="bold white")
                cargo_txt.append_text(_gauge_bar(cargo_ratio, cargo_w, "rgb(150,60,180)"))
                parts.append(Align.center(cargo_txt))

            pip_txt = Text(justify="center")
            pip_txt.append("SYS ", style="bold rgb(60,100,200)")
            pip_txt.append_text(_pip_bar(s.pips_sys, "rgb(60,100,200)"))
            pip_txt.append("  ENG ", style="bold rgb(160,200,60)")
            pip_txt.append_text(_pip_bar(s.pips_eng, "rgb(160,200,60)"))
            pip_txt.append("  WEP ", style="bold rgb(200,60,60)")
            pip_txt.append_text(_pip_bar(s.pips_wep, "rgb(200,60,60)"))
            parts.append(Align.center(pip_txt))

        parts.append(Text(""))  # spacer

        if s.in_main_ship:
            if s.analysis_mode:
                mode_label, mode_col = "Analysis", "rgb(200,255,200)"
            else:
                mode_label, mode_col = "Combat", P.HUD_CRIT

            btn_row: list[tuple[str, bool, str]] = []
            if s.docked:
                btn_row = [(mode_label, True, mode_col), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN)]
            elif s.landed:
                btn_row = [(mode_label, True, mode_col), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN), ("Silent", s.silent_running, P.HUD_CRIT)]
            elif s.supercruise:
                btn_row = [(mode_label, True, mode_col), ("Manual", s.flight_assist_off, P.HUD_CRIT), ("Lights", s.lights_on, P.AMBER), ("Silent", s.silent_running, P.HUD_CRIT)]
            else:
                btn_row = [(mode_label, True, mode_col), ("Gear", s.landing_gear, P.AMBER), ("Manual", s.flight_assist_off, P.HUD_CRIT), ("Scoop", s.cargo_scoop, P.AMBER), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN), ("Silent", s.silent_running, P.HUD_CRIT)]

            btn_txt = Text()
            _append_buttons(btn_txt, btn_row)
            parts.append(Align.center(btn_txt))

        warns_txt = Text()
        warns = []
        if s.overheating: warns.append(("⚠ OVERHEAT",   P.HUD_CRIT))
        if s.scooping:    warns.append(("⛽ SCOOPING",  P.HUD_WARN))
        if s.hardpoints:  warns.append(("⚔ HARDPOINTS", P.HUD_CRIT))
        if s.low_fuel:    warns.append(("⚠ LOW FUEL",   P.HUD_CRIT))
        for i, (label, col) in enumerate(warns):
            if i: warns_txt.append("   ")
            warns_txt.append(label, style=f"bold {col}")
        if warns:
            parts.append(Align.center(warns_txt))

        return Group(*parts)

    def _render_on_foot(self, s: AppState) -> RenderableType:
        panel_w = max(10, self.size.width // 3)
        bar_w   = max(4, panel_w - 6)

        hp_col  = P.HUD_GREEN if s.suit_health > 0.75 else (P.HUD_WARN if s.suit_health > 0.5 else P.HUD_CRIT)
        hp_txt  = Text(justify="center")
        hp_txt.append(f"{s.suit_health*100:.0f}%\n", style=f"bold {hp_col}")
        hp_txt.append_text(_gauge_bar(s.suit_health, bar_w, hp_col))
        hp_panel = Panel(Align.center(hp_txt), title="HEALTH",
                         border_style=hp_col, padding=(0, 1))

        sh_col   = P.BLUE_SH if s.shields_up else P.HUD_CRIT
        sh_label = "UP" if s.shields_up else "DOWN"
        sh_txt   = Text(justify="center")
        sh_txt.append(f"{sh_label}\n", style=f"bold {sh_col}")
        sh_txt.append_text(_gauge_bar(1.0 if s.shields_up else 0.0, bar_w, sh_col))
        sh_panel = Panel(Align.center(sh_txt), title="SHIELD",
                         border_style=sh_col, padding=(0, 1))

        ox_col  = P.HUD_CRIT if s.low_oxygen else (P.HUD_WARN if s.suit_oxygen < 0.5 else P.HUD_GREEN)
        ox_txt  = Text(justify="center")
        ox_txt.append(f"{s.suit_oxygen*100:.0f}%\n", style=f"bold {ox_col}")
        ox_txt.append_text(_gauge_bar(s.suit_oxygen, bar_w, ox_col))
        ox_panel = Panel(Align.center(ox_txt), title="OXYGEN",
                         border_style=ox_col, padding=(0, 1))

        parts: list[RenderableType] = []
        parts.append(Columns([hp_panel, sh_panel, ox_panel], expand=True, equal=True))

        info_txt = Text(justify="center")
        if s.selected_weapon:
            # Strip internal path prefix (e.g. "$humanoid_compactlaser_name;" → "Laser")
            weapon = s.selected_weapon
            if weapon.startswith("$") and ";" in weapon:
                weapon = weapon.split(";")[0].split("_name")[0].rsplit("_", 1)[-1].title()
            info_txt.append("Weapon  ", style=P.LABEL)
            info_txt.append(weapon, style=f"bold {P.AMBER}")
        if s.on_foot_gravity > 0.0:
            if s.selected_weapon:
                info_txt.append("   ")
            info_txt.append("Gravity  ", style=P.LABEL)
            info_txt.append(f"{s.on_foot_gravity:.2f}g", style=f"bold {P.HUD_CYAN}")
        if len(info_txt) > 0:
            parts.append(Align.center(info_txt))

        warns_txt = Text()
        warns = []
        if s.low_health_suit: warns.append(("⚠ LOW HEALTH", P.HUD_CRIT))
        if s.low_oxygen:      warns.append(("⚠ LOW O2",     P.HUD_CRIT))
        if s.suit_cold:       warns.append(("❄ COLD",        "rgb(120,180,255)"))
        if s.suit_hot:        warns.append(("🔥 HOT",         P.HUD_WARN))
        for i, (label, col) in enumerate(warns):
            if i: warns_txt.append("   ")
            warns_txt.append(label, style=f"bold {col}")
        if warns:
            parts.append(Align.center(warns_txt))

        return Group(*parts)

    def _render_srv(self, s: AppState) -> RenderableType:
        panel_w = max(10, self.size.width // 3)
        bar_w   = max(4, panel_w - 6)

        hull_pct = int(round(s.hull * 100.0))
        hull_col = P.HUD_GREEN if s.hull > 0.75 else (P.HUD_WARN if s.hull > 0.5 else P.HUD_CRIT)
        hull_txt = Text(justify="center")
        hull_txt.append(f"{hull_pct}%\n", style=f"bold {hull_col}")
        hull_txt.append_text(_gauge_bar(s.hull, bar_w, hull_col))
        hull_panel = Panel(Align.center(hull_txt), title="HULL",
                           border_style=hull_col, padding=(0, 1))

        sh_col   = P.BLUE_SH if s.shields_up else P.HUD_CRIT
        sh_label = "UP" if s.shields_up else "DOWN"
        sh_txt   = Text(justify="center")
        sh_txt.append(f"{sh_label}\n", style=f"bold {sh_col}")
        sh_txt.append_text(_gauge_bar(1.0 if s.shields_up else 0.0, bar_w, sh_col))
        sh_panel = Panel(Align.center(sh_txt), title="SHIELD",
                         border_style=sh_col, padding=(0, 1))

        parts: list[RenderableType] = []
        parts.append(Columns([hull_panel, sh_panel], expand=True, equal=True))
        parts.append(Text(""))

        # Mode + toggles
        if s.analysis_mode:
            mode_label, mode_col = "Analysis", "rgb(200,255,200)"
        else:
            mode_label, mode_col = "Combat", P.HUD_CRIT

        # Drive assist = SRV equivalent of flight assist (active = normal, off = manual)
        btn_row: list[tuple[str, bool, str]] = [
            (mode_label,  True,                   mode_col),
            ("Assist",    s.srv_drive_assist,      P.HUD_GREEN),
            ("Lights",    s.lights_on,             P.AMBER),
            ("Night",     s.night_vision,          P.HUD_GREEN),
        ]
        # Turret only relevant when turret view is active or retracted state differs
        if s.srv_turret_view or not s.srv_turret_retracted:
            btn_row.append(("Turret", s.srv_turret_view, P.HUD_CYAN))

        btn_txt = Text()
        _append_buttons(btn_txt, btn_row)
        parts.append(Align.center(btn_txt))

        warns_txt = Text()
        warns = []
        if s.srv_handbrake: warns.append(("⏸ HANDBRAKE",  P.HUD_WARN))
        if s.overheating:   warns.append(("⚠ OVERHEAT",   P.HUD_CRIT))
        if s.low_fuel:      warns.append(("⚠ LOW FUEL",   P.HUD_CRIT))
        for i, (label, col) in enumerate(warns):
            if i: warns_txt.append("   ")
            warns_txt.append(label, style=f"bold {col}")
        if warns:
            parts.append(Align.center(warns_txt))

        return Group(*parts)


def _append_buttons(t: Text, items: list[tuple[str, bool, str]]) -> None:
    INACTIVE = "rgb(160,160,160)"
    for i, (label, active, col) in enumerate(items):
        if i:
            t.append(" ")
        if active:
            t.append("◀ ", style=f"bold {col}")
            t.append(label, style=f"bold reverse {col}")
            t.append(" ▶", style=f"bold {col}")
        else:
            t.append(f"[ {label} ]", style=INACTIVE)


# ── Route panel ───────────────────────────────────────────────────────────────

# Station service labels (human-readable)
_SERVICE_LABELS: dict[str, Optional[str]] = {
    "commodities":       "Market",
    "blackmarket":       "Black Market",
    "refuel":            "Refuel",
    "repair":            "Repair",
    "rearm":             "Rearm",
    "outfitting":        "Outfitting",
    "shipyard":          "Shipyard",
    "workshop":          "Engg Workshop",
    "missions":          "Missions",
    "contacts":          "Contacts",
    "exploration":       "Universal Cart",
    "tuning":            "Tuning",
    "crewlounge":        "Crew Lounge",
    "socialspace":       "Social Space",
    "bartender":         "Bartender",
    "vistagenomics":     "Vista Genomics",
    "pioneersupplies":   "Pioneer Supplies",
    "apexinterstellar":  "Apex Interstellar",
    "fleetcarrier":      "Fleet Carrier Admin",
    # suppress these
    "dock": None,
    "autodock": None,
    "livery": None,
    "modulestorage": None,
}


def _strip_economy_label(s: str) -> str:
    """Remove $economy_… prefix/suffix, title-case the label."""
    s = s.strip()
    if s.startswith("$"):
        s = s.split(";")[0].split("_", 1)[-1]
    return s.replace("_", " ").title()


class RoutePanel(_Panel):
    BORDER_TITLE = "◈ Target"

    DEFAULT_CSS = """
    RoutePanel {
        border: solid rgb(210,115,0);
        border-title-color: rgb(210,115,0);
        border-title-style: bold;
        height: auto;
        min-height: 11;
        width: 1fr;
    }
    """

    _scroll: int = 0

    def scroll_route_panel(self, delta: int) -> None:
        self._scroll = max(0, self._scroll + delta)
        self.refresh()

    def update(self, snap: AppState) -> None:
        self._snap = snap
        if snap.docked:
            self.border_title = f"◈ Docked: {snap.station}" if snap.station else "◈ Station"
        elif snap.target_ship:
            self.border_title = f"◈ Target: {snap.target_ship}"
        elif snap.target_body:
            short = _short_name(snap.target_body, snap.system)
            self.border_title = f"◈ Target: {short}"
        elif snap.approach_body:
            short = _short_name(snap.approach_body, snap.system)
            self.border_title = f"◈ Approaching: {short}"
        elif snap.nearest_body:
            short = _short_name(snap.nearest_body, snap.system)
            self.border_title = f"◈ Nearby: {short}"
        elif getattr(snap, "nearest_populated_stations", []):
            self.border_title = "◈ Nearby"
        else:
            self.border_title = "◈ Target"
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        if s.docked:
            return self._render_station(s)
        if s.target_ship:
            return self._render_ship_target(s)
        if s.target_body:
            result = self._render_target(s)
            if result is not None:
                return result
        return self._render_nearby(s)

    def _render_station(self, s: AppState) -> RenderableType:
        t = Text()

        def row(label: str, value: str, vstyle: str = "white") -> None:
            t.append(f"{label:<8}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        t.append("DOCKED\n", style=f"bold {P.HUD_GREEN}")
        row("Station", s.station, "bold white")
        row("System",  s.system)
        if s.station_type:
            row("Type", s.station_type)
        if s.station_economy:
            econ = _strip_economy_label(s.station_economy)
            row("Economy", econ)
        if s.station_allegiance:
            row("Alleg", s.station_allegiance)
        if s.station_dist_ls > 0.0:
            row("Dist", _fmt_ls(s.station_dist_ls), P.LABEL)

        if s.station_services:
            services = [
                _SERVICE_LABELS.get(svc, svc.title())
                for svc in s.station_services
                if _SERVICE_LABELS.get(svc, svc) is not None
            ]
            if services:
                t.append("\n")
                t.append("Services\n", style=P.LABEL)
                for i in range(0, len(services), 2):
                    pair = services[i:i+2]
                    t.append("  " + "  ·  ".join(pair) + "\n", style="rgb(160,160,160)")

        return t

    def _render_ship_target(self, s: AppState) -> RenderableType:
        """Show info for currently targeted ship (ShipTargeted event)."""
        t = Text()

        def row(label: str, value: str, vstyle: str = "white") -> None:
            t.append(f"{label:<8}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        # Legal status colour
        _legal_col = {
            "Clean":      P.HUD_GREEN,
            "Lawless":    P.AMBER,
            "Wanted":     P.HUD_CRIT,
            "Enemy":      P.HUD_CRIT,
            "Hostile":    P.HUD_CRIT,
        }
        legal_c = _legal_col.get(s.target_ship_legal, "white")

        header_style = P.HUD_CRIT if s.target_ship_legal in ("Wanted", "Hostile", "Enemy") else P.HUD_CYAN
        t.append("TARGETING\n", style=f"bold {header_style}")
        t.append(s.target_ship + "\n", style="bold white")

        if s.target_ship_pilot:
            pilot_s = s.target_ship_pilot
            if s.target_ship_rank:
                pilot_s += f"  ({s.target_ship_rank})"
            row("Pilot", pilot_s)

        if s.target_ship_faction:
            row("Faction", s.target_ship_faction, P.LABEL)

        if s.target_ship_legal:
            row("Legal", s.target_ship_legal, legal_c)

        if s.target_ship_bounty > 0:
            from ..events import _fmt_credits as _fmtcr
            row("Bounty", _fmtcr(s.target_ship_bounty), P.HUD_CRIT)

        if s.target_ship_shield >= 0:
            sh_pct = s.target_ship_shield
            sh_col = P.HUD_GREEN if sh_pct > 50 else (P.AMBER if sh_pct > 0 else P.HUD_CRIT)
            row("Shield", f"{sh_pct:.0f}%", sh_col)

        if s.target_ship_hull >= 0:
            hu_pct = s.target_ship_hull
            hu_col = P.HUD_GREEN if hu_pct > 50 else (P.AMBER if hu_pct > 25 else P.HUD_CRIT)
            row("Hull", f"{hu_pct:.0f}%", hu_col)

        stage_label = ("basic", "shields/hull", "modules", "full scan")
        stage_s = stage_label[min(s.target_ship_stage, 3)]
        t.append(f"\n  scan: {stage_s}", style=P.LABEL)
        if s.target_ship_stage < 3:
            t.append("  (target to advance)", style="dim rgb(80,80,80)")
        t.append("\n")

        return t

    def _render_target(self, s: AppState) -> Optional[RenderableType]:
        """Show body details for currently targeted body.
        When the target is a system (next route hop), shows route info instead."""
        body_name = s.target_body
        body = next((b for b in s.bodies if b.name == body_name), None)
        if body is None:
            # System target (e.g. next route hop) — not a scanned body in this system
            t = Text()

            def _row(label: str, value: str, vstyle: str = "white") -> None:
                t.append(f"{label:<8}", style=P.LABEL)
                t.append(value + "\n", style=vstyle)

            t.append(f"{body_name}\n", style="bold white")
            if body_name == s.route_next:
                if s.route_next_dist > 0:
                    _row("Jump", f"{s.route_next_dist:.1f} ly")
                if s.route_next_star:
                    scoopable = s.route_next_scoopable
                    mark = "⛽" if scoopable else "✗"
                    col  = P.HUD_GREEN if scoopable else P.HUD_CRIT
                    _row("Star", f"{s.route_next_star}  {mark}", col)
                word = "jump" if s.route_hops == 1 else "jumps"
                _row("Hops", f"{s.route_hops} {word} remaining")
                if s.route_destination and s.route_destination != body_name:
                    _row("Dest", s.route_destination)
            return t

        t = Text()

        def row(label: str, value: str, vstyle: str = "white") -> None:
            t.append(f"{label:<8}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        short = _short_name(body_name, s.system)
        btype = _abbrev_type(body.planet_class, body.star_type)
        col   = _body_color(body.planet_class, body.star_type)

        t.append(f"{short}\n", style=f"bold {col}")

        row("Type", btype, f"bold {col}")
        if body.dist_ls > 0.0:
            row("Arrival", _fmt_ls(body.dist_ls), P.LABEL)  # distance from system entry star
        if s.altitude is not None and s.altitude > 0 and s.nearest_body == body_name:
            row("Alt", f"{s.altitude:,.0f} m", "white")

        atm = body.atmosphere
        if atm and "No atmo" not in atm:
            row("Atm", atm)

        if body.landable:
            if body.surface_gravity > 0.0:
                g_val = body.surface_gravity / 9.80665
                row("Land", f"Yes  ({g_val:.2f}g)", P.HUD_GREEN)
            else:
                row("Land", "Yes", P.HUD_GREEN)

        if body.bio_signals > 0:
            # Check how many are done
            complete_count = sum(
                1 for sc in s.bio_scans
                if sc.body == body_name and sc.complete
            )
            bio_str = f"{body.bio_signals} signals"
            if complete_count > 0:
                bio_str += f"  ({complete_count} done)"
            bio_col = P.GOLD if complete_count >= body.bio_signals else "bold rgb(0,220,80)"
            row("Bio", bio_str, bio_col)
            if body.bio_genuses:
                for g in body.bio_genuses[:4]:
                    t.append(f"  · {g}\n", style="rgb(0,160,60)")

        if body.geo_signals > 0:
            row("Geo", f"{body.geo_signals} signals", P.PURPLE)

        if body.terraform:
            row("Terr", "Candidate", P.HUD_CYAN)

        if body.first_discovered:
            t.append("★ First discovered!\n", style=f"bold {P.GOLD}")

        return t

    def _render_nearby(self, s: AppState) -> RenderableType:
        """Show nearest body (approach_body or nearest_body) or nearest station when nothing is targeted."""
        t = Text()

        def row(label: str, value: str, vstyle: str = "white") -> None:
            t.append(f"{label:<8}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        # Prefer the body the player is actively approaching, then the nearest tracked body
        near_name = s.approach_body or s.nearest_body
        body = next((b for b in s.bodies if b.name == near_name), None) if near_name else None

        if body:
            short = _short_name(body.name, s.system) if body.name and s.system else body.name
            btype = _abbrev_type(body.planet_class, body.star_type)
            col   = _body_color(body.planet_class, body.star_type)

            t.append(f"{short}\n", style=f"bold {col}")

            row("Type", btype, f"bold {col}")
            if body.dist_ls > 0.0:
                row("Arrival", _fmt_ls(body.dist_ls), P.LABEL)
            if s.altitude is not None and s.altitude > 0:
                row("Alt", f"{s.altitude:,.0f} m", "white")

            atm = body.atmosphere
            if atm and "No atmo" not in atm:
                row("Atm", atm)

            if body.landable:
                if body.surface_gravity > 0.0:
                    g_val = body.surface_gravity / 9.80665
                    g_col = P.HUD_CRIT if g_val >= 3.0 else (P.AMBER if g_val >= 1.5 else P.HUD_GREEN)
                    row("Land", f"Yes  ({g_val:.2f}g)", g_col)
                else:
                    row("Land", "Yes", P.HUD_GREEN)

            if body.bio_signals > 0:
                complete_count = sum(
                    1 for sc in s.bio_scans
                    if sc.body == body.name and sc.complete
                )
                bio_str = f"{body.bio_signals} signals"
                if complete_count > 0:
                    bio_str += f"  ({complete_count} done)"
                bio_col = P.GOLD if complete_count >= body.bio_signals else "bold rgb(0,220,80)"
                row("Bio", bio_str, bio_col)
                if body.bio_genuses:
                    for g in body.bio_genuses[:4]:
                        t.append(f"  · {g}\n", style="rgb(0,160,60)")

            if body.geo_signals > 0:
                row("Geo", f"{body.geo_signals} signals", P.PURPLE)

            if body.terraform:
                row("Terr", "Candidate", P.HUD_CYAN)

            if body.first_discovered:
                t.append("★ First discovered!\n", style=f"bold {P.GOLD}")

            return t

        # No nearby body — show nearest station in the current system from EDSM data
        stations = getattr(s, "nearest_populated_stations", [])
        if stations:
            stn = stations[0]
            stn_name = stn.get("name", "?")
            if len(stn_name) > 22:
                stn_name = stn_name[:21] + "…"
            t.append(f"{stn_name}\n", style="bold white")
            dist_ls = stn.get("dist_ls", 0)
            if dist_ls > 0:
                row("Dist", _fmt_ls(dist_ls), P.LABEL)
            stn_type = stn.get("type", "")
            if stn_type:
                row("Type", stn_type)
            icons = ""
            if stn.get("market"):     icons += "M"
            if stn.get("shipyard"):   icons += "S"
            if stn.get("outfitting"): icons += "O"
            svcs = stn.get("other_services") or stn.get("services") or []
            if "Repair" in svcs:      icons += "R"
            if icons:
                row("Svcs", f"[{icons}]", P.AMBER)
            return t

        # Nothing nearby at all
        t.append("No target\n", style=P.LABEL)
        if s.system:
            t.append(s.system + "\n", style="white")
        if s.jump_dist > 0.0:
            t.append("Last jump  ", style=P.LABEL)
            t.append(f"{s.jump_dist:.1f} ly\n", style="white")
        return t


# ── Bodies panel ──────────────────────────────────────────────────────────────

class BodiesPanel(_Panel):
    BORDER_TITLE = "◈ Scanned Bodies"

    DEFAULT_CSS = """
    BodiesPanel {
        border: solid rgb(0,175,185);
        border-title-color: rgb(0,175,185);
        border-title-style: bold;
    }
    """

    _scroll: int = 0

    def scroll_bodies(self, delta: int) -> None:
        """Scroll the bodies list up (delta<0) or down (delta>0)."""
        self._scroll = max(0, self._scroll + delta)
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None or not s.bodies:
            t = Text()
            t.append("No bodies scanned yet.", style=P.LABEL)
            return t

        tbl = Table(
            show_header=True, show_edge=False, show_lines=False,
            padding=(0, 1), box=None,
            row_styles=["", "on rgb(38,38,38)"],
        )
        HDR = "bold rgb(195,160,55)"
        tbl.add_column("Body", style="white", width=11, header_style=HDR, no_wrap=True)
        tbl.add_column("Type", width=8,  header_style=HDR)
        tbl.add_column("Val",  width=11, header_style=HDR, justify="right")
        tbl.add_column("Dist", width=11, header_style=HDR, justify="right")
        tbl.add_column("B",    width=4,  header_style=HDR)
        tbl.add_column("G",    width=2,  header_style=HDR)
        tbl.add_column("LTA",  width=5,  header_style=HDR)
        tbl.add_column("F",    width=2,  header_style=HDR)
        tbl.add_column("D",    width=2,  header_style=HDR)

        system  = s.system
        visible = [b for b in s.bodies if b.planet_class or b.star_type]
        
        # Sort bodies: single-star children first (A, B...), barycentre PLANETS last (AB 4...)
        # Exception: if "AB 1" is itself a star, its children "AB 1 a" sort directly after it.
        _star_short_names: set[str] = set()
        for _sb in visible:
            if _sb.star_type:
                _sn = _short_name(_sb.name, system).strip() or "A"
                _star_short_names.add(_sn)

        def _body_sort_key(b: BodyInfo) -> tuple:
            short = _short_name(b.name, system).strip()
            if not short and b.star_type and " " in b.name:
                m = re.search(r"\s+([A-Z0-9]{1,2})$", b.name)
                if m: short = m.group(1)

            if not short:
                return (0, "")  # Primary star always first

            parts = short.split()
            # A body is a barycentre-orbit body (bucket 1) when its short name starts with
            # a multi-char alpha prefix (like "AB") AND its root parent is NOT a star.
            # e.g. "AB 4" → root_parent="AB 4" (not a star) → bucket 1
            #      "AB 1 a" where AB 1 is a star → root_parent="AB 1" (IS a star) → bucket 0
            if not b.star_type and parts[0].isalpha() and len(parts[0]) > 1:
                root_parent = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]
                bucket = 0 if root_parent in _star_short_names else 1
            else:
                bucket = 0

            # Zero-pad numbers for correct lexicographic ordering
            key_parts = [f"{int(p):04d}" if p.isdigit() else p.lower() for p in parts]
            return (bucket, " ".join(key_parts))

        visible.sort(key=_body_sort_key)

        # Apply scroll offset (w/s keys)
        total_bodies = len(visible)
        effective_scroll = min(self._scroll, max(0, total_bodies - 1))

        above = effective_scroll
        panel_h = self.size.height or 0
        below = max(0, total_bodies - effective_scroll - max(1, panel_h - 2))

        _base_bodies = "◈ Scanned Bodies"
        if above > 0:
            _ind  = f" ▲{above}"
            _avail = (self.size.width or 20) - 4
            _pad  = max(1, _avail - Text.from_markup(_base_bodies).cell_len - len(_ind))
            self.border_title = _base_bodies + " " * _pad + _ind
        else:
            self.border_title = _base_bodies
        self.border_subtitle = (f"▼{below}" if below > 0 else "")
        visible = visible[effective_scroll:]

        # Pre-compute bodies with all bio signals scanned
        bio_done: set[str] = set()
        from collections import defaultdict as _dd
        complete_by_body: dict = _dd(int)
        for sc in s.bio_scans:
            if sc.complete:
                complete_by_body[sc.body] += 1
        for b in s.bodies:
            if b.bio_signals > 0 and complete_by_body.get(b.name, 0) >= b.bio_signals:
                bio_done.add(b.name)

        for b in visible:
            short = _short_name(b.name, system).strip()

            # Display logic: If it's a star and name matches system precisely, call it 'A'
            display_name = short
            if not display_name:
                display_name = "A" if b.star_type else b.name

            parts = display_name.split()

            # Hierarchical indentation:
            # Stars / primary bodies:         level 0 (no indent)
            # Single-star planets:            level 1  (A 1, B 2, 1...)
            # Single-star moons:              level 2+ (A 1 a, 1 a...)
            # Barycentre planets:             level 0  (AB 4 — orbits the binary, not A)
            # Barycentre planet moons:        level 1  (AB 4 a)
            # Children of barycentre STARS:   like normal children (AB 1 a → level 2)
            is_barycentric_prefix = not b.star_type and parts[0].isalpha() and len(parts[0]) > 1
            if is_barycentric_prefix:
                root_parent = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]
                is_barycentre_body = root_parent not in _star_short_names
            else:
                is_barycentre_body = False
            if b.star_type:
                level = 0
            elif parts[0][0].isdigit():
                level = len(parts)
            elif is_barycentre_body:
                level = max(0, len(parts) - 2)
            else:
                level = len(parts) - 1

            indent = " " * max(0, level)
            # High-G coloring: orange ≥1.5G, red-orange ≥3.0G (landable planets only)
            g_val = b.surface_gravity / 9.80665 if b.surface_gravity > 0 and b.landable else 0.0
            if g_val >= 3.0:
                name_style = "bold rgb(220,60,0)"
            elif g_val >= 1.5:
                name_style = "bold rgb(220,140,0)"
            else:
                name_style = "white"
            name  = Text(indent + display_name, style=name_style)
            btype = _abbrev_type(b.planet_class, b.star_type)

            val     = _fmt_value_short(_body_value(b))
            bv      = _body_value(b)
            val_col = (P.GOLD if bv > 1_000_000
                       else ("white" if b.value > 0
                             else (P.AMBER if _estimated_value(b) > 0 else P.DIM)))

            dist     = _fmt_ls_compact(b.dist_ls)
            dist_col = "rgb(80,80,80)" if b.dist_ls == 0.0 else "white"

            geo     = str(b.geo_signals) if b.geo_signals else "—"
            geo_col = P.PURPLE if b.geo_signals > 0 else P.DIM

            fss_str = "●" if b.fss_scanned else "—"
            fss_col = P.AMBER     if b.fss_scanned else P.DIM
            map_str = "●" if b.mapped else "—"
            map_col = P.HUD_GREEN if b.mapped      else P.DIM

            # DSS priority highlight: bio signals present but not yet mapped
            needs_dss = b.bio_signals > 0 and not b.mapped
            type_col  = _body_color(b.planet_class, b.star_type)

            # Bio signals + done marking
            if b.name in bio_done:
                bio     = f"{b.bio_signals}✓"
                bio_col = f"bold {P.GOLD}"
            elif needs_dss:
                bio     = str(b.bio_signals)
                bio_col = "bold rgb(0,220,80)"
            elif b.bio_signals > 0:
                bio     = str(b.bio_signals)
                bio_col = P.HUD_GREEN
            else:
                bio     = "—"
                bio_col = P.DIM

            atm_present = bool(b.atmosphere and "No atmo" not in b.atmosphere)
            flags = (
                ("L" if b.landable  else " ") +
                ("T" if b.terraform else " ") +
                ("A" if atm_present else " ")
            )
            flags_style = "bold rgb(130,200,130)" if flags != "───" else P.DIM

            tbl.add_row(
                name,
                Text(btype,    style=f"bold {type_col}"),
                Text(val,      style=val_col),
                Text(dist,     style=dist_col),
                Text(bio,      style=bio_col),
                Text(geo,      style=geo_col),
                Text(flags,    style=flags_style),
                Text(fss_str,  style=f"bold {fss_col}"),
                Text(map_str,  style=f"bold {map_col}"),
            )

        return tbl


# ── Content render helpers ────────────────────────────────────────────────────

def _render_bio(s: AppState, scroll: int = 0) -> RenderableType:
    from ..events import _BIO_GENUS_VALUE_RANGE

    HDR = "bold rgb(195,160,55)"

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
            hdr_t = Text()
            hdr_t.append("─" * 3, style="rgb(60,80,100)")
            hdr_t.append(f" {short} ", style="bold rgb(80,200,240)")
            hdr_t.append(f"(FSS · {b.bio_signals} bio) ", style="rgb(120,120,80)")
            hdr_t.append("─" * 8, style="rgb(60,80,100)")
            parts.append(hdr_t)

            if b.bio_genuses_predicted:
                tbl = Table(
                    show_header=True, show_edge=False, show_lines=False,
                    padding=(0, 0), box=None,
                )
                tbl.add_column("Predicted Genus",  width=22, header_style=HDR)
                tbl.add_column("Est. Value Range", width=22, header_style=HDR)

                _rng_lo: list[int] = []
                _rng_hi: list[int] = []
                for g in b.bio_genuses_predicted:
                    key = g.lower().split()[0] if g else ""
                    lo, hi = _BIO_GENUS_VALUE_RANGE.get(key, (0, 0))
                    val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
                    if lo > 0: _rng_lo.append(lo)
                    if hi > 0: _rng_hi.append(hi)
                    tbl.add_row(
                        Text(f"? {g}", style="rgb(160,160,80)"),
                        Text(val_s, style="rgb(160,130,60)"),
                    )
                parts.append(tbl)
                hint_t = Text()
                hint_t.append("  DSS to confirm genera", style=P.LABEL)
                if b.bio_signals > 0:
                    hint_t.append(f"  ·  {b.bio_signals} species", style=P.LABEL)
                if _rng_hi:
                    _n = max(1, b.bio_signals)
                    _total_lo = sum(sorted(_rng_lo)[:_n])
                    _total_hi = sum(sorted(_rng_hi, reverse=True)[:_n])
                    _est = f"~{_fmt_cr_compact(_total_lo)}–{_fmt_cr_compact(_total_hi)}"
                    hint_t.append(f"  ·  pot. {_est}", style="rgb(140,130,60)")
                hint_t.append("\n")
                parts.append(hint_t)
            else:
                unk_t = Text()
                unk_t.append(f"  ? unknown  ", style="rgb(120,120,80)")
                unk_t.append(f"({b.bio_signals} bio signal{'s' if b.bio_signals != 1 else ''})", style=P.LABEL)
                unk_t.append("  DSS to identify\n", style=P.LABEL)
                parts.append(unk_t)

        elif gtype == "prescan":
            b = gdata
            short = _short_name(b.name, s.system) if b.name and s.system else b.name
            _ff = getattr(b, "first_footfall", False)
            hdr_t = Text()
            hdr_t.append("─" * 3, style="rgb(60,80,100)")
            hdr_t.append(f" {short} ", style="bold rgb(80,200,240)")
            hdr_t.append("(DSS) ", style="rgb(100,140,180)")
            if _ff:
                hdr_t.append("✦ FF ", style=P.HUD_GREEN)
            hdr_t.append("─" * 14, style="rgb(60,80,100)")
            parts.append(hdr_t)

            tbl = Table(
                show_header=True, show_edge=False, show_lines=False,
                padding=(0, 0), box=None,
            )
            tbl.add_column("Genus",       width=22, header_style=HDR)
            tbl.add_column("Est. Value",  width=22, header_style=HDR)

            for g in b.bio_genuses:
                key = g.lower().split()[0] if g else ""
                lo, hi = _BIO_GENUS_VALUE_RANGE.get(key, (0, 0))
                if _ff and lo > 0:
                    lo, hi = lo * 5, hi * 5
                val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
                tbl.add_row(
                    Text(g, style=P.HUD_CYAN),
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
            hdr_t = Text()
            hdr_t.append("─" * 3, style="rgb(60,80,100)")
            hdr_t.append(f" {short} ", style="bold rgb(80,200,240)")
            if _scan_ff:
                hdr_t.append("✦ FF ", style=P.HUD_GREEN)
            hdr_t.append("─" * 20, style="rgb(60,80,100)")
            parts.append(hdr_t)

            tbl = Table(
                show_header=True, show_edge=False, show_lines=False,
                padding=(0, 0), box=None,
            )
            tbl.add_column("Species",  width=21, header_style=HDR)
            tbl.add_column("Genus",    width=13, header_style=HDR)
            tbl.add_column("Smp",      width=5,  header_style=HDR)
            tbl.add_column("MinDist",  width=8,  header_style=HDR)
            tbl.add_column("Travel",   width=22, header_style=HDR)
            tbl.add_column("Value",    width=14, header_style=HDR)

            for sc in scans:
                samples_col = {3: P.HUD_GREEN, 2: P.HUD_WARN, 1: "rgb(210,210,0)"}.get(sc.samples, P.LABEL)
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
                    f"bold rgb(80,240,160)" if sc.first_footfall
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
                    val_style = "bold rgb(0,255,180)"  # bright teal — first footfall bonus
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


def _section_header(title: str) -> Text:
    t = Text()
    t.append(f" {title} ", style="bold rgb(180,140,50) on rgb(45,35,10)")
    t.append("\n")
    return t


def _render_inventory(s: AppState, scroll: int = 0) -> RenderableType:
    # Build flat list of all rows for scrolling: ("header", label) | ("cargo", item) | ("mat", name, cnt)
    all_rows: list[tuple] = []
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

    if not all_rows:
        t = Text()
        t.append("No inventory data yet.", style=P.LABEL)
        return t

    effective_scroll = min(scroll, max(0, len(all_rows) - 1))
    parts: list[RenderableType] = []
    visible_rows = all_rows[effective_scroll:]

    # Group consecutive rows into sections for rendering
    current_header: Optional[str] = None
    current_tbl: Optional[Table] = None

    def _flush_tbl() -> None:
        nonlocal current_tbl
        if current_tbl is not None:
            parts.append(current_tbl)
            current_tbl = None

    for row in visible_rows:
        if row[0] == "header":
            _flush_tbl()
            if parts:
                parts.append(Text("\n"))
            parts.append(_section_header(row[1]))
            current_header = row[1]
            current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
            current_tbl.add_column("name",  style="white")
            current_tbl.add_column("count", justify="right")
        elif row[0] == "cargo":
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
                current_tbl.add_column("name",  style="white")
                current_tbl.add_column("count", justify="right", style=P.AMBER)
            item = row[1]
            style = "rgb(255,80,80)" if item.get("stolen") else "white"
            current_tbl.add_row(
                Text(item["name"], style=style),
                Text(str(item["count"]), style=f"bold {P.AMBER}"),
            )
        elif row[0] == "mat":
            _, name, cnt = row
            if current_tbl is None:
                current_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
                current_tbl.add_column("name",  style="white")
                current_tbl.add_column("count", justify="right")
            cnt_col = P.HUD_WARN if cnt >= 150 else ("white" if cnt >= 50 else P.LABEL)
            current_tbl.add_row(name, Text(str(cnt), style=f"bold {cnt_col}"))
    _flush_tbl()

    return Group(*parts)


def _render_missions(s: AppState, scroll: int = 0) -> RenderableType:
    if not s.missions:
        t = Text()
        t.append("No active missions.", style=P.LABEL)
        return t

    parts: list[RenderableType] = []

    # Massacre kill progress (grouped by faction)
    if s.massacre_kills:
        # Group by faction
        fac_kills: dict = {}
        for mid, mk in s.massacre_kills.items():
            fac = mk["faction"]
            if fac not in fac_kills:
                fac_kills[fac] = {"needed": 0, "done": 0}
            fac_kills[fac]["needed"] += mk["needed"]
            fac_kills[fac]["done"]   += mk["done"]

        kill_head = Text()
        kill_head.append("MASSACRE PROGRESS\n", style="bold rgb(195,60,60)")
        parts.append(kill_head)

        for fac, kd in fac_kills.items():
            done   = kd["done"]
            needed = kd["needed"]
            filled = int(10 * done / needed) if needed > 0 else 0
            bar    = "█" * filled + "░" * (10 - filled)
            pct_t  = Text()
            pct_t.append(f"  [{bar}] ", style="rgb(200,80,80)")
            pct_t.append(f"{done}/{needed}", style="white")
            pct_t.append(f"  {fac}\n", style=P.LABEL)
            parts.append(pct_t)

    missions = s.missions
    effective_scroll = min(scroll, max(0, len(missions) - 1))
    visible_missions = missions[effective_scroll:]

    tbl = Table(
        show_header=True, show_edge=False, show_lines=False,
        padding=(0, 1), box=None,
    )
    HDR = "bold rgb(195,160,55)"
    tbl.add_column("Mission",     header_style=HDR)
    tbl.add_column("Destination", width=20, header_style=HDR)
    tbl.add_column("Time left",   width=9,  header_style=HDR, justify="right")

    for m in visible_missions:
        remaining = _mission_time_remaining(m.expiry)
        if remaining == "Expired":
            time_col = P.HUD_CRIT
        elif remaining.endswith("m") and not remaining[0].isdigit():
            time_col = P.HUD_WARN
        else:
            time_col = P.LABEL

        tbl.add_row(
            Text(m.name, style="white"),
            Text(m.destination, style=P.LABEL),
            Text(remaining, style=f"bold {time_col}"),
        )
    parts.append(tbl)

    return Group(*parts)


# Odyssey (on-foot) engineers — they don't use the 1–5 grade system
_ODY_ENGINEERS: frozenset = frozenset({
    "Baltanos", "Eleanor Bresa", "Hero Ferrari", "Rosa Dayette",
    "Yi Shen", "Domino Green", "Uma Laszlo", "Oden Geiger", "Terra Velasquez",
})

_ENGINEER_STATIC: dict[str, tuple[str, str]] = {
    # name → (specialty, system)
    "Elvira Martuuk":     ("FSD",             "Long Sight Base, Kwatee"),
    "Felicity Farseer":   ("FSD / Thrusters", "Farseer Inc, Deciat"),
    "Ishmael Palin":      ("Thrusters",       "Mawson Dock, Arque"),
    "Professor Palin":    ("Thrusters",       "Mawson Dock, Arque"),
    "Chloe Sedesi":       ("FSD / Thrusters", "Synuefe XR-H d11-102"),
    "Mel Brandon":        ("Various",         "The Brig, Luchtaine"),
    "Marco Qwent":        ("Power Plant",     "Qwent Research Base, Sirius"),
    "Hera Tani":          ("Power Plant",     "The Jet's Hole, Kuwemaki"),
    "Etienne Dorn":       ("Sensors",         "Krins Survey, Los"),
    "Juri Ishmaak":       ("Sensors/Countermeasures", "Pater's Memorial, Giryak"),
    "Lei Cheung":         ("Shields",         "Trader's Rest, Laksak"),
    "Selene Jean":        ("Armour",          "Prospector's Rest, Kuk"),
    "The Dweller":        ("Weapons",         "Black Hide, Wyrd"),
    "Tod 'The Blaster' McQuinn": ("Weapons",  "Trophy Camp, Wolf 397"),
    "Broo Tarquin":       ("Weapons",         "Broo's Legacy, Muang"),
    "Liz Ryder":          ("Explosives",      "Demolition Unlimited, Eurybia"),
    "Ram Tah":            ("Electronic Countermeasures", "Phoenix Base, Meene"),
    "Bill Turner":        ("Plasma Charger",  "Alioth Research Facility, Alioth"),
    "Didi Vatermann":     ("Shields",         "Vatermann LLC, Leesti"),
    "Colonel Bris Dekker":("FSD Interdictor", "Dekker's Yard, Sol"),
    "Petra Olmanova":     ("Armour",          "Sanctuary, Asura"),
    "Zacariah Nemo":      ("Pulse Laser",     "Nemo Cyber Party Base, Yoru"),
    "Yarden Bond":        ("Shields",         "Brestla i-Ship Brewery, Brestla"),
    "Corra Sang":         ("Shields",         "Piri's Retreat, Eurybia"),
    "Kit Fowler":         ("Launch Bay",      "Fowler's Hope, Capella"),
    "Marsha Hicks":       ("Detailed Scanner","The Watchtower, 83 Leonis"),
    "Wellington Beck":    ("Mining Equipment","The Watchtower, 83 Leonis"),
    "Baltanos":           ("Suit",            "Builders Croft, Deriso"),
    "Eleanor Bresa":      ("Suit",            "Bresa Modifications, Kojeara"),
    "Hero Ferrari":       ("Suit",            "Ferrari Salvage Inc, Siris"),
    "Rosa Dayette":       ("Suit/Weapon",     "Rosa's Retreat, Novas"),
    "Yi Shen":            ("Weapon",          "Shen's World, Pan Geminorum"),
    "Domino Green":       ("Weapon",          "Prosperous Horizons, Orishis"),
    "Uma Laszlo":         ("Weapon",          "Laszlo's Resolve, Xuane"),
    "Oden Geiger":        ("Suit",            "Ankh's Promise, Candiaei"),
    "Terra Velasquez":    ("Suit",            "Rascals' Choice, Shou Xing"),
    "Yarden Bond":        ("Shield",          "Brestla i-Ship Brewery, Brestla"),
}


def _render_engineers(s: AppState, scroll: int = 0) -> RenderableType:
    if not s.engineers:
        t = Text()
        t.append("No engineer data.", style=P.LABEL)
        return t

    # Classify engineers into Horizons vs Odyssey, then by progress status
    horizons: dict[str, list] = {"UNLOCKED": [], "IN PROGRESS": [], "LOCKED": []}
    odyssey:  dict[str, list] = {"UNLOCKED": [], "IN PROGRESS": [], "LOCKED": []}

    for name, info in sorted(s.engineers.items()):
        if isinstance(info, EngineerInfo):
            prog, rank, rp = info.progress, info.rank, info.rank_progress
        else:
            rank, prog = info; rp = 0.0

        bucket = odyssey if name in _ODY_ENGINEERS else horizons
        if prog == "Unlocked":
            bucket["UNLOCKED"].append((name, rank, rp, prog))
        elif prog in ("Invited", "Acquainted", "Known"):
            bucket["IN PROGRESS"].append((name, rank, rp, prog))
        else:
            bucket["LOCKED"].append((name, rank, rp, prog))

    # Flatten: (era, section, entry)
    all_engs: list[tuple[str, str, tuple]] = []
    for era_label, era_dict in (("HORIZONS", horizons), ("ODYSSEY", odyssey)):
        for section_label, group in era_dict.items():
            for entry in group:
                all_engs.append((era_label, section_label, entry))

    if not all_engs:
        t = Text()
        t.append("No engineer data.", style=P.LABEL)
        return t

    effective_scroll = min(scroll, max(0, len(all_engs) - 1))
    parts: list[RenderableType] = []

    current_era: Optional[str] = None
    current_section: Optional[str] = None

    for era, section, (name, rank, rp, prog) in all_engs[effective_scroll:]:
        is_ody = name in _ODY_ENGINEERS
        spec, location = _ENGINEER_STATIC.get(name, ("", ""))
        if "," in location:
            station, system = [x.strip() for x in location.split(",", 1)]
        else:
            station, system = location, ""

        # Era header (HORIZONS / ODYSSEY)
        if era != current_era:
            if current_era is not None:
                parts.append(Text(""))
            parts.append(_section_header(era))
            current_era = era
            current_section = None

        # Section sub-header (UNLOCKED / IN PROGRESS / LOCKED)
        if section != current_section:
            t = Text()
            t.append(f"  {section}\n", style="bold rgb(195,160,55)")
            parts.append(t)
            current_section = section

        # Card line 1: name + rank/status
        card = Text()
        card.append(f"  {name}", style="white")
        padding = max(1, 26 - len(name))
        card.append(" " * padding)

        if prog == "Unlocked":
            max_r = 1 if is_ody else 5
            eff_r = min(1 if is_ody else rank, max_r)
            card.append("█" * eff_r,          style=P.HUD_GREEN)
            card.append("░" * (max_r - eff_r), style=P.LABEL)
            card.append(f"  {eff_r}/{max_r}",  style=P.LABEL)
        elif prog in ("Invited", "Acquainted", "Known"):
            if rp > 0:
                width  = 8
                filled = int(rp / 100.0 * width)
                card.append("▓" * filled,          style=P.AMBER)
                card.append("░" * (width - filled), style=P.LABEL)
                card.append(f"  {rp:.0f}%",         style=P.LABEL)
            else:
                card.append(prog, style=P.AMBER)
        else:
            card.append(prog or "Unknown", style=P.LABEL)
        card.append("\n")

        # Card line 2: specialty · system · station
        card.append("    ")
        sep = False
        if spec:
            card.append(spec, style=P.LABEL)
            sep = True
        if system:
            if sep:
                card.append("  ·  ", style=P.LABEL)
            card.append(system, style=P.HUD_CYAN)
            sep = True
        if station:
            if sep:
                card.append("  ·  ", style=P.LABEL)
            card.append(station, style=P.LABEL)
        card.append("\n")
        parts.append(card)

    return Group(*parts)


def _render_wealth(s: AppState) -> RenderableType:
    parts: list[RenderableType] = []

    # ── Balance ──────────────────────────────────────────────────────────────
    bal_text = Text()
    bal_text.append("BALANCE\n", style="bold rgb(195,160,55)")
    if s.credits > 0:
        bal_text.append(f"  {_de(s.credits)} Cr\n", style="bold white")
    else:
        bal_text.append("  Unknown\n", style=P.LABEL)
    parts.append(bal_text)

    # ── Fleet ────────────────────────────────────────────────────────────────
    # Current ship always first
    cur_ship = Text()
    cur_ship.append("\nFLEET\n", style="bold rgb(195,160,55)")
    if s.ship_type or s.ship_name:
        label = s.ship_name or s.ship_type
        cur_ship.append(f"  {label}", style="bold white")
        if s.ship_ident:
            cur_ship.append(f"  [{s.ship_ident}]", style=P.LABEL)
        cur_ship.append("  ◀ HERE\n", style=P.HUD_GREEN)
    parts.append(cur_ship)

    if s.stored_ships:
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",    style="white")
        tbl.add_column("ident",   style=P.LABEL,    width=8)
        tbl.add_column("system",  style=P.HUD_CYAN,  width=20)
        for ship in s.stored_ships[:8]:
            name   = ship.get("name") or ship.get("type") or "Unknown"
            ident  = ship.get("ident") or ""
            system = ship.get("system") or ""
            here   = ship.get("here", False)
            tbl.add_row(
                Text(name, style="bold white" if here else "white"),
                Text(ident, style=P.LABEL),
                Text(system + (" [HERE]" if here else ""), style=P.HUD_GREEN if here else P.HUD_CYAN),
            )
        parts.append(tbl)
    else:
        no_fleet = Text()
        no_fleet.append("  Open the ship transfer screen at any station\n", style=P.LABEL)
        no_fleet.append("  to load your full fleet.\n", style=P.LABEL)
        parts.append(no_fleet)

    # ── Cargo ────────────────────────────────────────────────────────────────
    if s.cargo_items:
        parts.append(_section_header(f"CARGO  {s.cargo}/{s.cargo_capacity}t"))
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",  style="white")
        tbl.add_column("count", justify="right", style=P.AMBER)
        for item in s.cargo_items[:12]:
            style = "rgb(255,80,80)" if item.get("stolen") else "white"
            tbl.add_row(Text(item["name"], style=style), Text(str(item["count"]), style=f"bold {P.AMBER}"))
        parts.append(tbl)

    # ── Suit / backpack ──────────────────────────────────────────────────────
    if s.suit_loadout:
        suit_text = Text()
        suit_text.append("\nSUIT LOADOUT\n", style="bold rgb(195,160,55)")
        suit_name = s.suit_loadout.get("suit") or "Unknown Suit"
        suit_text.append(f"  {suit_name}\n", style="white")
        weapons = s.suit_loadout.get("weapons") or []
        for w in weapons[:3]:
            wname = (w.get("SuitModuleName_Localised") or w.get("SuitModuleName") or "")
            if wname:
                suit_text.append(f"  ▸ {wname}\n", style=P.LABEL)
        parts.append(suit_text)

    if s.backpack:
        items = s.backpack.get("items") or []
        comps = s.backpack.get("components") or []
        data  = s.backpack.get("data") or []
        consumables = s.backpack.get("consumables") or []
        total_items = len(items) + len(comps) + len(data) + len(consumables)
        if total_items > 0:
            bp_text = Text()
            bp_text.append("\nBACKPACK\n", style="bold rgb(195,160,55)")
            bp_text.append(f"  {total_items} item(s) — Items {len(items)}  Comps {len(comps)}  Data {len(data)}\n", style=P.LABEL)
            parts.append(bp_text)

    # ── Odyssey materials (backpack + ship locker) ────────────────────────────
    def _ody_section(label: str, items: list) -> None:
        if not items:
            return
        parts.append(Text("\n"))
        parts.append(_section_header(label))
        ody_tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        ody_tbl.add_column("name",  style="rgb(200,220,255)")
        ody_tbl.add_column("count", justify="right")
        for item in sorted(items, key=lambda x: (x.get("Name_Localised") or x.get("Name", "")).lower()):
            name  = item.get("Name_Localised") or item.get("Name", "?")
            count = item.get("Count", 0)
            cnt_col = P.HUD_WARN if count >= 100 else ("white" if count >= 30 else P.LABEL)
            ody_tbl.add_row(name, Text(str(count), style=f"bold {cnt_col}"))
        parts.append(ody_tbl)

    has_backpack = any(s.backpack.get(k) for k in ("items", "components", "consumables", "data"))
    has_locker   = any(s.ship_locker.get(k) for k in ("items", "components", "consumables", "data"))
    if has_backpack or has_locker:
        parts.append(Text("\n"))
        div = Text()
        div.append("── ODYSSEY ──────────────────────\n", style=f"bold {P.AMBER}")
        parts.append(div)

    if has_backpack:
        bp = s.backpack
        _ody_section("BACKPACK — Items",       bp.get("items", []))
        _ody_section("BACKPACK — Components",  bp.get("components", []))
        _ody_section("BACKPACK — Consumables", bp.get("consumables", []))
        _ody_section("BACKPACK — Data",        bp.get("data", []))

    if has_locker:
        lk = s.ship_locker
        _ody_section("LOCKER — Items",       lk.get("items", []))
        _ody_section("LOCKER — Components",  lk.get("components", []))
        _ody_section("LOCKER — Consumables", lk.get("consumables", []))
        _ody_section("LOCKER — Data",        lk.get("data", []))

    if not parts:
        t = Text()
        t.append("No wealth data yet.\n", style=P.LABEL)
        t.append("Dock at a station or open the in-game outfitting/shipyard menu.", style=P.LABEL)
        return t

    return Group(*parts)


def _render_neutron(s: AppState, scroll: int = 0) -> RenderableType:
    parts: list[RenderableType] = []

    # Status header
    status = s.neutron_route_status
    target = s.neutron_route_to
    route  = s.neutron_route

    hdr = Text()
    hdr.append("NEUTRON ROUTE PLOTTER  ", style="bold rgb(195,160,55)")
    hdr.append("via Spansh API\n", style=P.LABEL)
    if s.jump_range > 0:
        hdr.append(f"  Unladen max: ", style=P.LABEL)
        hdr.append(f"{s.jump_range:.1f} ly", style="white")
        hdr.append(f"  →  boosted {s.jump_range * 4:.0f} ly\n", style=P.LABEL)
        if s.jump_range_last > 0:
            diff = s.jump_range - s.jump_range_last
            diff_str = f"  ({diff:+.1f} ly vs unladen)" if abs(diff) > 0.5 else ""
            hdr.append(f"  Last jump:  ", style=P.LABEL)
            hdr.append(f"{s.jump_range_last:.1f} ly", style="white")
            hdr.append(f"{diff_str}\n", style=P.LABEL)
        else:
            hdr.append("  Last jump:  unknown — make a jump first for accurate routing\n", style=P.LABEL)
    else:
        hdr.append("  Jump range: unknown — fly your ship first\n", style=P.LABEL)
    parts.append(hdr)

    if status == "plotting":
        t = Text()
        t.append(f"\n  Plotting route to {target}…\n", style=P.AMBER)
        parts.append(t)
    elif status == "error":
        t = Text()
        t.append(f"\n  Could not plot route to '{target}'.\n", style=P.HUD_CRIT)
        t.append("  Check that the system name is spelled exactly as in-game.\n", style=P.LABEL)
        parts.append(t)
    elif status == "done" and route:
        # Skip the starting-system entry (distance=0, jumps=0) — it's just the origin
        display_route = [j for j in route if j.get("distance", 0) > 0 or j.get("jumps", 0) > 0]
        total_ly      = sum(j.get("distance", 0) for j in display_route)
        neutron_count = sum(1 for j in display_route if j.get("neutron"))
        regular_hops  = sum(j.get("jumps", 0) for j in display_route)
        summary = Text()
        summary.append(f"\n  → {target}\n", style="bold white")
        summary.append(
            f"  {len(display_route)} waypoints  |  {regular_hops} regular + {neutron_count} boosted jumps"
            f"  |  {total_ly:,.0f} ly\n",
            style=P.AMBER,
        )
        parts.append(summary)

        PAGE = 30
        scroll = max(0, min(scroll, max(0, len(display_route) - PAGE)))
        visible = display_route[scroll:scroll + PAGE]

        tbl = Table(show_header=True, show_edge=False, box=None, padding=(0, 1))
        HDR = "bold rgb(195,160,55)"
        tbl.add_column("#",    width=4,  header_style=HDR, justify="right")
        tbl.add_column("System", header_style=HDR)
        tbl.add_column("Boost", width=9, header_style=HDR, justify="right")
        tbl.add_column("",     width=5,  header_style=HDR)

        for i, jump in enumerate(visible, scroll + 1):
            sys_name  = jump.get("system") or "—"
            dist      = jump.get("distance", 0.0)
            pre_jumps = jump.get("jumps", 0)
            is_n      = jump.get("neutron", False)
            is_last   = (i == len(display_route))

            dist_str = Text(
                f"{dist:.1f} ly",
                style=P.HUD_GREEN if is_n else ("bold white" if is_last else "white"),
            )

            # Marker col: ⚡ Nj for neutron (Nj = regular hops to reach this star)
            #             Nj → for non-neutron with pre-hops  (e.g. final destination)
            #             (empty) for non-neutron without pre-hops
            marker = Text()
            if is_n:
                marker.append("⚡", style=f"bold {P.HUD_GREEN}")
                if pre_jumps > 0:
                    marker.append(f" {pre_jumps}j", style=P.LABEL)
            elif pre_jumps > 0:
                marker.append(f"{pre_jumps}j", style=P.LABEL)

            tbl.add_row(
                Text(str(i), style=P.LABEL),
                Text(sys_name, style="bold white" if is_last else "white"),
                dist_str,
                marker,
            )

        if scroll > 0:
            tbl.add_row(Text("↑", style=P.LABEL), Text(f"{scroll} above", style=P.LABEL), Text(""), Text(""))
        remaining = len(display_route) - scroll - len(visible)
        if remaining > 0:
            tbl.add_row(Text("↓", style=P.LABEL), Text(f"{remaining} more  (↓/↑)", style=P.LABEL), Text(""), Text(""))
        parts.append(tbl)
    else:
        hint = Text()
        hint.append("\n  Press  n  to enter a destination system.\n", style=P.LABEL)
        hint.append("  Uses local neutron star data (Spansh dump, refreshed daily).\n", style=P.LABEL)
        parts.append(hint)

    return Group(*parts)


def _render_system_map(s: AppState, standalone: bool = False) -> RenderableType | None:
    """System bodies diagram: *---O-o-o---O-o---O---*---O---
    Returns None if no bodies are available yet.
    standalone=True adds a system name header for the MAP sub-screen."""
    _sys     = s.system
    _s_stars   = sorted([b for b in s.bodies if b.star_type],
                        key=lambda b: (0 if not _short_name(b.name, _sys).strip() else 1,
                                       _natural_key(_short_name(b.name, _sys))))
    _s_planets = sorted([b for b in s.bodies if b.planet_class and b.level <= 1],
                        key=lambda b: _natural_key(_short_name(b.name, _sys)))
    _s_moons   = sorted([b for b in s.bodies if b.planet_class and b.level == 2],
                        key=lambda b: _natural_key(_short_name(b.name, _sys)))

    if not (_s_stars or _s_planets):
        if standalone:
            t = Text()
            t.append("No bodies scanned yet.\n", style=P.LABEL)
            t.append("Use FSS to scan the system.", style="dim rgb(100,100,100)")
            return t
        return None

    diag = Text()
    if standalone:
        diag.append(f"{_sys}\n", style="bold white")
        diag.append("\nSYSTEM DIAGRAM\n", style="bold rgb(195,160,55)")
    else:
        diag.append("\nSYSTEM\n", style="bold rgb(195,160,55)")

    # Map star short-name key → BodyInfo
    star_index: dict[str, BodyInfo] = {
        _short_name(b.name, _sys).strip(): b for b in _s_stars
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
        p_short = _short_name(p.name, _sys).strip()
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
    barycentre_planets.sort(key=lambda b: _natural_key(_short_name(b.name, _sys)))

    # Which planet does each moon belong to?  Remove last token.
    planet_moons: dict[str, list[BodyInfo]] = {}
    for m in _s_moons:
        m_short = _short_name(m.name, _sys).strip()
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
                return "bold rgb(220,60,0)"
            if g >= 1.5:
                return "bold rgb(220,140,0)"
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
                    for i, ch in enumerate(lbl):
                        if rel_pos + i < len(name_arr) and name_arr[rel_pos + i] == " ":
                            name_arr[rel_pos + i] = ch
                            name_body[rel_pos + i] = b
            row2 = Text("  ")
            for ch, b in zip(name_arr, name_body):
                style = (f"bold {P.HUD_GREEN}") if (b and b.mapped) else "rgb(160,160,160)"
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
        legend.append("\n  * star   O planet   o moon\n", style="dim rgb(100,100,100)")
        legend.append("  + notable body   ✓/N bio signals\n", style="dim rgb(100,100,100)")
        legend.append("  green = DSS mapped   orange/red = high-G\n", style="dim rgb(100,100,100)")
        diag.append_text(legend)

    return diag


def _render_overview(s: AppState) -> RenderableType:
    """Travel overview: route + galaxy position + system diagram + notable bodies + session stats."""
    import math
    parts: list[RenderableType] = []

    # ── Two-column header: ROUTE (left) + POSITION (right) ────────────────────
    _R = "      "  # ~6-char indent for ROUTE column (visual separation from POSITION)
    route_col = Text()
    route_col.append(f"{_R}ROUTE\n", style=f"bold {P.AMBER}")
    if s.route_destination:
        route_col.append(f"{_R}→ ", style=P.LABEL)
        route_col.append(s.route_destination + "\n", style="bold white")
        word = "jump" if s.route_hops == 1 else "jumps"
        route_col.append(f"{_R}  {s.route_hops} {word} remaining\n", style=P.AMBER)
        if s.route_next:
            route_col.append(f"{_R}→ ", style=P.LABEL)
            route_col.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                mark     = " ⛽" if s.route_next_scoopable else " ✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                route_col.append(f"  {s.route_next_star}{mark}", style=f"bold {star_col}")
            route_col.append("\n")
    else:
        route_col.append(f"{_R}No route set.\n", style=P.AMBER_DIM)

    pos_col = Text()
    if s.star_pos:
        x, y, z = s.star_pos
        dist_sol  = math.sqrt(x**2 + y**2 + z**2)
        core_x, core_y, core_z = 25.21875, -20.90625, 25899.96875
        dist_core = math.sqrt((x - core_x)**2 + (y - core_y)**2 + (z - core_z)**2)
        pos_col.append("POSITION\n", style=f"bold {P.AMBER}")
        pos_col.append(f"{x:.0f} / {y:.0f} / {z:.0f}\n", style="rgb(150,150,150)")
        pos_col.append("Sol   ", style=P.LABEL)
        pos_col.append(f"{dist_sol:,.0f} ly\n".replace(",", _NNBSP), style="white")
        pos_col.append("Core  ", style=P.LABEL)
        pos_col.append(f"{dist_core:,.0f} ly\n".replace(",", _NNBSP), style="white")
    else:
        pos_col.append("POSITION\n", style=f"bold {P.AMBER}")
        pos_col.append("No position data.\n", style=P.LABEL)

    hdr_grid = Table.grid(padding=(0, 2))
    hdr_grid.add_column(ratio=1)
    hdr_grid.add_column(ratio=1)
    hdr_grid.add_row(pos_col, route_col)
    parts.append(hdr_grid)

    # Notable bodies in current system
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
    if notable:
        notable.sort(key=lambda b: _natural_key(_short_name(b.name, s.system)))
        hdr = Text()
        hdr.append("\nNOTABLE BODIES\n", style="bold rgb(195,160,55)")
        parts.append(hdr)

        tbl = Table(show_header=True, show_edge=False, box=None, padding=(0, 1),
                    header_style="dim rgb(130,130,130)")
        tbl.add_column("BODY",  style="white", width=10, no_wrap=True)
        tbl.add_column("TYPE",  width=11, no_wrap=True)
        tbl.add_column("G",     width=6,  justify="right", no_wrap=True)
        tbl.add_column("SCAN",  width=9,  justify="right", no_wrap=True)
        tbl.add_column("BIO",   width=12, justify="right", no_wrap=True)
        tbl.add_column("WHY",   width=18, no_wrap=True)

        # Pre-compute actual bio values and completion per body
        from collections import defaultdict as _dd2
        _bio_done_cnt:  dict = _dd2(int)
        _bio_actual_cr: dict = _dd2(int)
        for _sc in s.bio_scans:
            if _sc.complete:
                _bio_done_cnt[_sc.body]  += 1
                _bio_actual_cr[_sc.body] += _sc.value

        for b in notable:
            short  = _short_name(b.name, s.system)
            btype  = _abbrev_type(b.planet_class, b.star_type)
            body_col = _body_color(b.planet_class, b.star_type)
            is_unusual = bool(b.unusual_body)

            # Bio completion state
            has_bio      = b.bio_signals > 0
            bio_done_cnt = _bio_done_cnt.get(b.name, 0)
            bio_all_done = has_bio and bio_done_cnt >= b.bio_signals
            actual_bio   = _bio_actual_cr.get(b.name, 0) if bio_all_done else 0

            # "Done" = body scanned (mapped) AND bio complete (or no bio)
            scan_done = b.mapped
            bio_done  = bio_all_done or not has_bio
            all_done  = scan_done and bio_done

            # Body scan value (includes first-mapping bonus when applicable)
            body_v = _body_value(b)

            if all_done:
                val_s = _fmt_notable_val(body_v)
                vcol  = P.GOLD
                bio_s = _fmt_notable_val(actual_bio) if actual_bio > 0 else "✓"
                bio_c = P.HUD_GREEN
            elif bio_all_done:
                val_s = _fmt_notable_val(body_v)
                vcol  = P.AMBER if body_v == 0 else P.GOLD
                bio_s = _fmt_notable_val(actual_bio) if actual_bio > 0 else "✓"
                bio_c = P.GOLD
            else:
                val_s = _fmt_notable_val(body_v)
                vcol  = P.GOLD if body_v > 1_000_000 else (P.AMBER if body_v > 0 else P.DIM)
                if has_bio:
                    if b.bio_value_max > 0:
                        # DSS confirmed genus ranges (sum of all confirmed genera)
                        bio_s = f"~{_fmt_cr_compact(b.bio_value_min)}–{_fmt_cr_compact(b.bio_value_max)}"
                        bio_c = P.AMBER
                    elif b.bio_genuses:
                        # DSS confirmed genera but no value estimate (unknown genera)
                        bio_s = f"{len(b.bio_genuses)}×✓"
                        bio_c = P.AMBER
                    elif b.bio_genuses_predicted:
                        # FSS prediction — show range: cheapest to most expensive predicted genus
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
                            bio_c = "rgb(140,130,60)"  # dimmer gold — uncertain prediction
                        else:
                            bio_s = f"{b.bio_signals}×?"
                            bio_c = P.LABEL
                    else:
                        bio_s = f"{b.bio_signals}×"
                        bio_c = P.HUD_GREEN
                else:
                    bio_s = "—"
                    bio_c = P.DIM

            # Gravity
            if b.landable and b.surface_gravity > 0:
                g_val = b.surface_gravity / 9.80665
                g_s   = f"{g_val:.2f}G"
                g_col = ("bold rgb(220,60,0)"   if g_val >= 3.0
                         else "bold rgb(220,140,0)" if g_val >= 1.5
                         else "rgb(160,160,160)")
            else:
                g_s   = "—"
                g_col = P.DIM

            # Name/type style — dim when all done (already collected)
            dim_done = all_done
            name_style = "rgb(110,110,110)" if dim_done else "white"
            type_prefix = "! " if is_unusual else ""
            type_style  = "rgb(110,110,110)" if dim_done else (
                f"bold rgb(220,140,0)" if is_unusual else f"bold {body_col}"
            )

            # WHY column — build reason string
            why_parts = []
            if b.planet_class == "Earthlike body":  why_parts.append("ELW")
            if b.planet_class == "Water world":      why_parts.append("WW")
            if b.planet_class == "Ammonia world":    why_parts.append("AW")
            if b.terraform:                           why_parts.append("TF")
            if b.bio_signals > 0:                    why_parts.append(f"{b.bio_signals}B")
            if body_v > s.notable_value_threshold:  why_parts.append("HV")
            if b.unusual_body:                        why_parts.append(b.unusual_body)
            why_str = ", ".join(why_parts)

            tbl.add_row(
                Text(short,                  style=name_style),
                Text(type_prefix + btype,    style=type_style),
                Text(g_s,                    style=g_col),
                Text(val_s,                  style=vcol),
                Text(bio_s,                  style=bio_c),
                Text(why_str,                style=P.LABEL),
            )
        parts.append(tbl)

    # System summary — when no notable bodies and system is inhabited
    has_notable = any(_is_notable(b) for b in s.bodies) if s.bodies else False
    if not has_notable and s.economy and s.population > 0:
        sys_head = Text()
        sys_head.append("\nCURRENT SYSTEM\n", style=f"bold rgb(195,160,55)")
        parts.append(sys_head)
        sys_info = Text()
        if s.economy:
            sys_info.append("  Economy    ", style=P.LABEL)
            sys_info.append(s.economy + "\n", style="white")
        if s.allegiance:
            sys_info.append("  Allegiance ", style=P.LABEL)
            sys_info.append(s.allegiance + "\n", style="white")
        if s.controlling_faction:
            faction_str = (
                f"{s.controlling_faction} [{s.controlling_state}]"
                if s.controlling_state and s.controlling_state != "None"
                else s.controlling_faction
            )
            sys_info.append("  Faction    ", style=P.LABEL)
            sys_info.append(faction_str + "\n", style="white")
        parts.append(sys_info)

    # PowerPlay merits summary
    if s.pp_power:
        pp_head = Text()
        pp_head.append("\nPOWERPLAY\n", style="bold rgb(130,80,200)")
        parts.append(pp_head)
        pp_info = Text()
        rank_str = f" Rank {s.pp_rank}" if s.pp_rank > 0 else ""
        pp_info.append("  Power      ", style=P.LABEL)
        pp_info.append(f"{s.pp_power}{rank_str}\n", style="white")
        if s.pp_total_merits > 0:
            pp_info.append("  Merits     ", style=P.LABEL)
            pp_info.append(f"{_de(s.pp_total_merits)}", style="rgb(180,130,255)")
            if s.pp_session_merits > 0:
                pp_info.append(f"  (+{_de(s.pp_session_merits)} session)", style=P.LABEL)
            pp_info.append("\n", style="")
        parts.append(pp_info)

    # BGS activity summary (today's log)
    if s.bgs_log:
        bgs_head = Text()
        bgs_head.append("\nBGS ACTIVITY\n", style="bold rgb(0,180,100)")
        parts.append(bgs_head)
        bgs_info = Text()
        for sys_name, fac_map in list(s.bgs_log.items())[:3]:
            short_sys = _short_name(sys_name, s.system) if sys_name == s.system else sys_name
            for faction, acts in fac_map.items():
                total = sum(acts.values())
                act_str = ", ".join(f"{v}×{k}" for k, v in sorted(acts.items(), key=lambda x: -x[1]))
                bgs_info.append(f"  {faction[:20]}\n", style="white")
                bgs_info.append(f"    {act_str}\n", style=P.LABEL)
        parts.append(bgs_info)

    # Nearest inhabited system — shown only when current system is uninhabited
    if s.nearest_populated_name and s.population == 0:
        import math as _imath
        inh_head = Text()
        inh_head.append("\nNEAREST INHABITED SYSTEM\n", style="bold rgb(100,180,255)")
        parts.append(inh_head)
        dist_ly   = s.nearest_populated_dist
        dist_str  = f"{dist_ly:.0f} ly"
        jrange    = s.jump_range_last or s.jump_range
        jumps_est = _imath.ceil(dist_ly / jrange) if jrange > 0 and dist_ly > 0 else None
        jumps_str = f"~{jumps_est} jump{'s' if jumps_est != 1 else ''}" if jumps_est else ""
        stn_count = sum(
            1 for _s in s.nearest_populated_stations
            if _s.get("type", "") != "Drake-Class Carrier"
        )
        svcs: set[str] = set()
        for _stn in s.nearest_populated_stations:
            if _stn.get("market"):     svcs.add("Market")
            if _stn.get("shipyard"):   svcs.add("Shipyard")
            if _stn.get("outfitting"): svcs.add("Outfitting")
            for _sv in _stn.get("services", []):
                if _sv in ("Repair", "Refuel", "Rearm", "BlackMarket"):
                    svcs.add(_sv)
        inh_tbl = Table(show_header=False, show_edge=False, box=None,
                        padding=(0, 1), expand=False)
        inh_tbl.add_column("name",   style="white",           no_wrap=True)
        inh_tbl.add_column("dist",   style=P.LABEL,           no_wrap=True, justify="right")
        inh_tbl.add_column("jumps",  style="rgb(130,130,130)", no_wrap=True, justify="right")
        inh_tbl.add_row(
            s.nearest_populated_name, dist_str, jumps_str,
        )
        row2_col1 = Text(s.nearest_populated_allegiance or "", style=P.LABEL)
        row2_col2 = Text(f"{stn_count} Station{'s' if stn_count != 1 else ''}" if stn_count else "", style=P.LABEL)
        row2_col3 = Text(", ".join(sorted(svcs)) if svcs else "", style=P.LABEL)
        inh_tbl.add_row(row2_col1, row2_col2, row2_col3)
        parts.append(inh_tbl)
        parts.append(Text(""))

    # Fleet carrier (from Spansh API, when carrier_lookup enabled) — nearest only
    if s.carriers_current_system:
        import math as _math
        car_head = Text()
        car_head.append("\nNEAREST FLEET CARRIER\n", style="bold rgb(100,180,255)")
        parts.append(car_head)

        nearest = min(s.carriers_current_system, key=lambda c: c.get("dist_ls", float("inf")))
        c          = nearest
        c_name     = c.get("name", "")
        c_system   = c.get("system_name", "")
        c_dist_ls  = c.get("dist_ls", 0.0)
        c_updated  = c.get("updated_at", "")
        c_x        = c.get("sys_x", 0.0)
        c_y        = c.get("sys_y", 0.0)
        c_z        = c.get("sys_z", 0.0)

        ly_dist: Optional[float] = None
        car_jumps_est: Optional[int] = None
        if s.star_pos and (c_x or c_y or c_z):
            px, py, pz = s.star_pos
            ly_dist = _math.sqrt((px-c_x)**2 + (py-c_y)**2 + (pz-c_z)**2)
            if s.jump_dist > 0 and ly_dist > 0:
                car_jumps_est = _math.ceil(ly_dist / s.jump_dist)

        in_current = c_system and c_system.lower() == s.system.lower()
        if in_current and c_dist_ls > 0:
            c_dist_str  = _fmt_ls_compact(c_dist_ls)
            c_jumps_str = ""
        elif ly_dist is not None:
            c_dist_str  = f"{ly_dist:.0f} ly"
            c_jumps_str = f"~{car_jumps_est} jump{'s' if car_jumps_est != 1 else ''}" if car_jumps_est else ""
        else:
            c_dist_str  = ""
            c_jumps_str = ""

        if c_updated:
            ago = _fmt_ago(c_updated)
            c_location_str = ago if ago else (c_system or "")
            c_location_style = "rgb(100,100,100)" if ago else "white"
        elif c_system:
            c_location_str  = c_system
            c_location_style = "white"
        else:
            c_location_str  = ""
            c_location_style = P.LABEL

        svc_parts = []
        if c.get("market"):     svc_parts.append("Market")
        if c.get("shipyard"):   svc_parts.append("Shipyard")
        if c.get("outfitting"): svc_parts.append("Outfitting")
        if c.get("rearm"):      svc_parts.append("Rearm")
        if c.get("refuel"):     svc_parts.append("Refuel")
        if c.get("repair"):     svc_parts.append("Repair")

        car_tbl = Table(show_header=False, show_edge=False, box=None,
                        padding=(0, 1), expand=False)
        car_tbl.add_column("name",  no_wrap=True)
        car_tbl.add_column("dist",  no_wrap=True, justify="right")
        car_tbl.add_column("jumps", no_wrap=True, justify="right")
        car_tbl.add_row(
            Text(c_name, style=f"bold {P.AMBER}"),
            Text(c_dist_str, style=P.LABEL),
            Text(c_jumps_str, style="rgb(130,130,130)"),
        )
        car_tbl.add_row(
            Text(c_location_str, style=c_location_style),
            Text(""),
            Text(", ".join(svc_parts) if svc_parts else "", style=P.LABEL),
        )
        parts.append(car_tbl)
        parts.append(Text(""))

    if not parts:
        return Text("No data.", style=P.LABEL)
    return Group(*parts)


# ── Braille canvas helpers ─────────────────────────────────────────────────────

# Bit values for each dot position in a 2×4 braille cell.
# Index: [dot_row][dot_col]
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
    title_str = f"GALAXY  {scale_str} ({mode_str})  [R]"

    title_line = Text()
    title_line.append(f"  {title_str}\n", style=f"bold {P.LABEL}")
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


# ── System orrery renderer ─────────────────────────────────────────────────────

def _render_orrery(s: AppState) -> RenderableType:
    """System orrery: colored braille orbital chart with legend table."""
    import math

    AU = 1.496e11  # metres per AU

    star_bodies   = [b for b in s.bodies if b.star_type and b.level == 0]
    planet_bodies = [b for b in s.bodies if not b.star_type and b.level == 1 and b.planet_class]

    if not planet_bodies:
        t = Text()
        t.append("No planet data scanned yet.", style=P.LABEL)
        return t

    # Compute semi-major axis in AU for each planet
    def get_au(b: BodyInfo) -> float:
        if b.semi_major_axis > 0:
            return b.semi_major_axis / AU
        if b.dist_ls > 0:
            return b.dist_ls / 499.0
        return 0.0

    planet_data = sorted(
        [(get_au(b), b) for b in planet_bodies if get_au(b) > 0],
        key=lambda x: x[0],
    )
    if not planet_data:
        t = Text()
        t.append("Insufficient orbital data.", style=P.LABEL)
        return t

    a_max = planet_data[-1][0]

    W, H = 44, 17
    DW, DH = W * 2, H * 4
    cx_d, cy_d = DW // 2, DH // 2
    canvas_r = min(cx_d, cy_d) - 3  # max dot radius

    dots, cg = _bc_new(W, H)

    def log_r(a: float) -> int:
        if a <= 0:
            return 0
        return max(2, int(math.log(a + 1) / math.log(a_max + 1) * canvas_r))

    # ── Star(s) at center ─────────────────────────────────────────────────────
    for ox, oy in ((0,0),(1,0),(-1,0),(0,1),(0,-1),(2,0),(-2,0),(0,2),(0,-2)):
        _bc_set(dots, cg, cx_d + ox, cy_d + oy, P.GOLD, 9)

    # ── Orbit rings + planet positions ────────────────────────────────────────
    for a_au, b in planet_data:
        r_d = log_r(a_au)

        # Orbit ring (dim)
        _bc_circle(dots, cg, cx_d, cy_d, r_d, P.DIM, 1)

        # Planet position angle from mean_anomaly (or 0 if unavailable)
        e = b.eccentricity
        M_deg = b.mean_anomaly
        if b.semi_major_axis > 0 and M_deg != 0.0:
            M = math.radians(M_deg)
            E = M
            for _ in range(10):
                denom = 1.0 - e * math.cos(E)
                if abs(denom) < 1e-9:
                    break
                E -= (E - e * math.sin(E) - M) / denom
            nu = 2.0 * math.atan2(
                math.sqrt(1 + e) * math.sin(E / 2),
                math.sqrt(max(0.0, 1 - e)) * math.cos(E / 2),
            )
        else:
            nu = 0.0

        bx = cx_d + int(r_d * math.cos(nu))
        by = cy_d + int(r_d * math.sin(nu))

        col = _body_color(b.planet_class, b.star_type)
        for ox, oy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
            _bc_set(dots, cg, bx + ox, by + oy, col, 7)

    # ── Render canvas ─────────────────────────────────────────────────────────
    t = Text()
    t.append_text(_bc_render(dots, cg, W, H))
    t.append("\n")
    t.append(" (orbital angles at scan time)", style=P.LABEL)

    # Star name(s)
    for b in star_bodies[:2]:
        short = _short_name(b.name, s.system) or "A"
        t.append(f"  ★ {short}", style=P.GOLD)
    t.append("\n")

    # Planet legend — compact two-column table
    col1, col2 = [], []
    for i, (a_au, b) in enumerate(planet_data):
        short  = _short_name(b.name, s.system) or "?"
        btype  = _abbrev_type(b.planet_class, b.star_type)
        col    = _body_color(b.planet_class, b.star_type)
        dist_s = f"{a_au:.1f}AU" if a_au < 100 else f"{int(a_au)}AU"
        bio_s  = f" Bio:{b.bio_signals}" if b.bio_signals else ""
        entry  = (f" ● {short:<5} {btype:<8} {dist_s:<6}{bio_s}", col)
        if i % 2 == 0:
            col1.append(entry)
        else:
            col2.append(entry)

    for i in range(max(len(col1), len(col2))):
        if i < len(col1):
            t.append(col1[i][0], style=col1[i][1])
        if i < len(col2):
            t.append(col2[i][0], style=col2[i][1])
        t.append("\n")

    return t


# ── Bio panel (kept for standalone use) ───────────────────────────────────────

class BioPanel(_Panel):
    BORDER_TITLE = "◈ Biological Scans"

    DEFAULT_CSS = """
    BioPanel {
        border: solid rgb(0,170,60);
        border-title-color: rgb(0,170,60);
        border-title-style: bold;
        height: auto;
        min-height: 3;
    }
    """

    def render(self) -> RenderableType:
        if self._snap is None:
            return Text("")
        return _render_bio(self._snap)


# ── Materials / Cargo panel (kept for standalone use) ─────────────────────────

class MaterialsPanel(_Panel):
    BORDER_TITLE = "◈ Inventory"

    DEFAULT_CSS = """
    MaterialsPanel {
        border: solid rgb(90,90,90);
        border-title-color: rgb(180,180,180);
        border-title-style: bold;
        height: 1fr;
    }
    """

    def render(self) -> RenderableType:
        if self._snap is None:
            return Text("")
        return _render_inventory(self._snap)


# ── Missions panel (kept for standalone use) ───────────────────────────────────

class MissionsPanel(_Panel):
    BORDER_TITLE = "◈ Missions"

    DEFAULT_CSS = """
    MissionsPanel {
        border: solid rgb(195,150,0);
        border-title-color: rgb(195,150,0);
        border-title-style: bold;
        height: auto;
        min-height: 3;
    }
    """

    def render(self) -> RenderableType:
        if self._snap is None:
            return Text("")
        return _render_missions(self._snap)


# ── Engineers panel (kept for standalone use) ──────────────────────────────────

class EngineersPanel(_Panel):
    BORDER_TITLE = "◈ Engineers"

    DEFAULT_CSS = """
    EngineersPanel {
        border: solid rgb(70,70,140);
        border-title-color: rgb(130,130,220);
        border-title-style: bold;
        height: auto;
        min-height: 3;
    }
    """

    def render(self) -> RenderableType:
        if self._snap is None:
            return Text("")
        return _render_engineers(self._snap)


# ── Situational panel ─────────────────────────────────────────────────────────

class SituationalPanel(_Panel):
    """Context-aware panel: auto-switches between Bio / Missions / Inventory.
    Tab cycles through modes manually."""

    _MODES = (
        "auto", "overview", "bio", "galaxy", "missions", "engineers",
        "bgs", "colonisation", "route", "neutron", "wealth", "inventory",
        "docking", "stats",
    )
    _mode:            str   = "overview"  # current shown panel (user or auto-triggered)
    _active:          str   = "overview" # resolved panel being rendered (always == _mode)
    _auto:            bool  = True       # auto-switching enabled (A key toggles)
    _last_auto_panel: str   = ""         # last panel returned by _auto_resolve; change triggers override
    _jump_at_seen:    float = 0.0        # last state.last_jump_at we've acted on
    _galaxy_submode:      str  = "system"   # "system" | "regional" | "galaxy"
    _neutron_scroll:      int  = 0
    _bgs_scroll:          int  = 0
    _colonisation_scroll: int  = 0
    _route_scroll:        int  = 0
    _general_scroll:      int  = 0
    _visible_modes:       list = []  # populated in update() from snap.situational_panels

    _MODE_ABBREVS = {
        "auto": "***", "overview": "OVR", "bio": "BIO", "galaxy": "MAP",
        "missions": "MIS", "engineers": "ENG", "bgs": "BGS", "colonisation": "COL",
        "route": "ROU", "neutron": "NTR", "wealth": "WLT", "inventory": "INV",
        "docking": "DKG", "stats": "STS",
    }

    _MODE_FULLNAMES = {
        "auto": "AUTO", "overview": "OVERVIEW", "bio": "BIOLOGICAL", "galaxy": "MAPS",
        "missions": "MISSION", "engineers": "ENGINEERS", "bgs": "BGS", "colonisation": "COLONISATION",
        "route": "ROUTE", "neutron": "NEUTRON", "wealth": "WALLET", "inventory": "INVENTORY",
        "docking": "DOCKING", "stats": "STATISTICS",
    }

    DEFAULT_CSS = """
    SituationalPanel {
        border: solid rgb(90,90,90);
        border-title-color: rgb(180,180,180);
        border-title-style: bold;
        height: 1fr;
    }
    """

    def _active_modes(self) -> list:
        """Return the ordered list of visible modes (from config or default), excluding 'auto'."""
        base = self._visible_modes if self._visible_modes else list(self._MODES)
        return [m for m in base if m != "auto"]

    def cycle(self) -> None:
        modes = self._active_modes()
        if not modes:
            return
        idx = modes.index(self._mode) if self._mode in modes else -1
        self._mode = modes[(idx + 1) % len(modes)]
        self._active = self._mode
        self._general_scroll = 0
        self.border_title = self._make_title()
        self.refresh()

    def back_cycle(self) -> None:
        modes = self._active_modes()
        if not modes:
            return
        idx = modes.index(self._mode) if self._mode in modes else 0
        self._mode = modes[(idx - 1) % len(modes)]
        self._active = self._mode
        self._general_scroll = 0
        self.border_title = self._make_title()
        self.refresh()

    def toggle_auto_lock(self) -> None:
        """Toggle automatic panel switching on/off."""
        self._auto = not self._auto
        if self._auto and self._snap is not None:
            # Re-sync last_auto_panel so the next real trigger overrides correctly
            self._last_auto_panel = self._auto_resolve(self._snap)
            self._mode = self._last_auto_panel
            self._active = self._mode
        self.border_title = self._make_title()
        self.refresh()

    def toggle_galaxy_scale(self) -> None:
        """Cycle through MAP sub-screens: system diagram → regional map → galaxy map."""
        _cycle = ("system", "regional", "galaxy")
        idx = _cycle.index(self._galaxy_submode) if self._galaxy_submode in _cycle else 0
        self._galaxy_submode = _cycle[(idx + 1) % len(_cycle)]
        self.refresh()

    def toggle_galaxy_scale_back(self) -> None:
        """Cycle MAP sub-screens backward: galaxy → regional → system."""
        _cycle = ("system", "regional", "galaxy")
        idx = _cycle.index(self._galaxy_submode) if self._galaxy_submode in _cycle else 0
        self._galaxy_submode = _cycle[(idx - 1) % len(_cycle)]
        self.refresh()

    def scroll_neutron(self, delta: int) -> None:
        """Scroll the neutron route list up/down."""
        route_len = len(self._snap.neutron_route) if self._snap else 0
        self._neutron_scroll = max(0, min(self._neutron_scroll + delta, max(0, route_len - 5)))
        self.refresh()

    def scroll_bgs(self, delta: int) -> None:
        self._bgs_scroll = max(0, self._bgs_scroll + delta)
        self.refresh()

    def scroll_colonisation(self, delta: int) -> None:
        self._colonisation_scroll = max(0, self._colonisation_scroll + delta)
        self.refresh()

    def scroll_route(self, delta: int) -> None:
        route_len = len(self._snap.route_list) if self._snap else 0
        self._route_scroll = max(0, min(self._route_scroll + delta, max(0, route_len - 3)))
        self.refresh()

    _NON_SCROLLABLE = frozenset({"overview", "wealth", "stats", "docking", "galaxy"})

    def scroll_general(self, delta: int) -> None:
        """Scroll the current situational panel up/down (for all non-specialised modes)."""
        if self._active in self._NON_SCROLLABLE:
            return
        self._general_scroll = max(0, self._general_scroll + delta)
        self.refresh()

    def _auto_resolve(self, s: AppState) -> str:
        """Compute which panel auto-mode would switch to based on current game state."""
        visible = set(self._active_modes())
        def _v(m: str) -> str:
            return m if m in visible else "overview"
        # Offline: no live game data — show statistics
        if not s.client_online:
            return _v("stats")
        # Hyperspace jump in progress — show route so remaining hops are visible
        if s.in_hyperspace and s.route_hops > 0:
            return _v("route")
        # Docking granted — show pad diagram
        if s.docked_pad > 0 and not s.docked:
            return _v("docking")
        # Incomplete bio scans — player is actively scanning
        if any(not sc.complete for sc in s.bio_scans):
            return _v("bio")
        # Approaching or on a DSS'd body with bio signals — show pre-scan genus list
        body_name = s.approach_body or (s.nearest_body if (s.landed or s.in_srv) else "")
        if body_name:
            idx = s._bodies_by_name.get(body_name, -1)
            if 0 <= idx < len(s.bodies) and s.bodies[idx].bio_genuses:
                return _v("bio")
        # Show colonisation when active sites exist and player is in system
        if s.colonisation_sites and any(
            site.get("system") == s.system for site in s.colonisation_sites.values()
        ):
            return _v("colonisation")
        # Show missions when active (not in supercruise)
        if s.missions and not s.supercruise:
            return _v("missions")
        # Route set — show route when no higher-priority context is active
        if s.route_hops > 0:
            return _v("route")
        return "overview"

    def _make_title(self) -> str:
        # *** indicator: bright = auto ON, dim = auto OFF
        if self._auto:
            auto_tag = "[bold rgb(255,220,80)]***[/]"
        else:
            auto_tag = "[dim]***[/]"

        parts = []
        for m in self._active_modes():
            abbr     = self._MODE_ABBREVS[m]
            fullname = self._MODE_FULLNAMES[m]
            is_current = (m == self._mode)
            is_auto_target = self._auto and (m == self._last_auto_panel)

            if is_current and is_auto_target:
                # Auto is driving this panel
                parts.append(f"[bold rgb(255,220,80)]{fullname}[/]")
            elif is_current:
                # User manually selected (auto ON or OFF)
                col = "rgb(0,200,150)" if self._auto else "white"
                parts.append(f"[bold {col}]{fullname}[/]")
            elif is_auto_target:
                # Auto wants this panel but user has browsed elsewhere
                parts.append(f"[rgb(160,130,40)]{abbr}[/]")
            else:
                parts.append(f"[dim]{abbr}[/]")

        joined = auto_tag + "   " + " ".join(parts)
        return "◈ " + joined

    def update(self, snap: AppState) -> None:
        self._snap = snap
        # Update visible modes from config (rebuild each tick — cheap)
        if snap.situational_panels:
            self._visible_modes = [
                m for m in snap.situational_panels if m in self._MODES and m != "auto"
            ]
        else:
            self._visible_modes = [m for m in self._MODES if m != "auto"]
        # If current mode was removed from config, fall back to first visible
        if self._mode not in self._visible_modes:
            self._mode = self._visible_modes[0] if self._visible_modes else "overview"

        # Auto-switching: only override _mode when the suggested panel changes.
        # This lets the user browse panels freely; a new trigger overrides.
        if self._auto:
            # New jump detected → reset scroll; _auto_resolve handles mode naturally
            # (in_hyperspace → route; arrived → overview/bio/missions/etc.)
            if snap.last_jump_at > 0 and snap.last_jump_at != self._jump_at_seen:
                self._jump_at_seen   = snap.last_jump_at
                self._general_scroll = 0

            auto_panel = self._auto_resolve(snap)
            if auto_panel != self._last_auto_panel:
                self._last_auto_panel = auto_panel
                if auto_panel != self._mode:
                    self._mode = auto_panel
                    self._general_scroll = 0

        new_active = self._mode
        if new_active != self._active:
            self._general_scroll = 0
        self._active = new_active
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        mode    = self._active
        panel_h = self.size.height or 20
        panel_w = self.size.width  or 40

        # ── Galaxy: sub-view indicator only, no scroll ────────────────────
        if mode == "galaxy":
            _subs = ("system", "regional", "galaxy")
            idx   = _subs.index(self._galaxy_submode) + 1 if self._galaxy_submode in _subs else 1
            self.border_title    = self._make_title()
            self.border_subtitle = f"{idx}/3  "
            sub = self._galaxy_submode
            if sub == "system":
                result = _render_system_map(s, standalone=True)
                return result if result is not None else Text("No bodies scanned yet.", style=P.LABEL)
            return _render_galaxy(s, regional=(sub == "regional"),
                                  panel_w=panel_w, panel_h=panel_h)

        # ── Compute per-mode item count + clamp scroll ────────────────────
        max_rows_route = max(5, panel_h - 5)  # matches _render_route

        if mode in self._NON_SCROLLABLE:
            total  = 0
            scroll = 0

        elif mode == "route":
            route         = s.route_list or []
            display_route = route[1:] if len(route) > 1 else []
            total         = len(display_route)
            scroll        = max(0, min(self._route_scroll, max(0, total - max_rows_route)))
            self._route_scroll = scroll

        elif mode == "bio":
            by_body: dict = {}
            for sc in s.bio_scans:
                by_body.setdefault(sc.body or "Unknown", [])
            scanned_bodies = set(by_body.keys())
            _prescan = [b for b in s.bodies if b.bio_genuses and b.name not in scanned_bodies]
            _dss     = {b.name for b in _prescan}
            _pred    = [b for b in s.bodies
                        if b.bio_signals > 0 and not b.bio_genuses
                        and b.name not in scanned_bodies and b.name not in _dss]
            total  = len(_pred) + len(_prescan) + len(by_body)
            scroll = max(0, min(self._general_scroll, max(0, total - 1)))
            self._general_scroll = scroll

        elif mode == "missions":
            total  = len(s.missions)
            scroll = max(0, min(self._general_scroll, max(0, total - 1)))
            self._general_scroll = scroll

        elif mode == "engineers":
            total  = len(s.engineers) if s.engineers else 0
            scroll = max(0, min(self._general_scroll, max(0, total - 1)))
            self._general_scroll = scroll

        elif mode == "inventory":
            _inv_rows = 0
            if s.cargo_items:
                _inv_rows += 1 + len(s.cargo_items)
            for _md in (s.materials_raw, s.materials_mfg, s.materials_enc):
                if _md:
                    _inv_rows += 1 + len(_md)
            total  = _inv_rows
            scroll = max(0, min(self._general_scroll, max(0, total - 1)))
            self._general_scroll = scroll

        elif mode == "bgs":
            total  = sum(len(facs) for facs in s.bgs_log.values()) if s.bgs_log else 0
            scroll = max(0, min(self._bgs_scroll, max(0, total - 1)))
            self._bgs_scroll = scroll

        elif mode == "colonisation":
            total  = len(s.colonisation_sites) if s.colonisation_sites else 0
            scroll = max(0, min(self._colonisation_scroll, max(0, total - 1)))
            self._colonisation_scroll = scroll

        elif mode == "neutron":
            total  = len(s.neutron_route) if s.neutron_route else 0
            scroll = max(0, min(self._neutron_scroll, max(0, total - 1)))
            self._neutron_scroll = scroll

        else:
            total  = 0
            scroll = 0

        # ── Compute above / below ─────────────────────────────────────────
        above = scroll
        if total == 0:
            below = 0
        elif mode == "route":
            below = max(0, total - scroll - max_rows_route)
        else:
            below = max(0, total - scroll - max(1, panel_h - 2))

        # ── Set border indicators (▲ top-right, ▼ bottom-right) ──────────
        base = self._make_title()
        if above > 0:
            indicator = f" ▲{above}"
            avail     = panel_w - 4
            pad       = max(1, avail - Text.from_markup(base).cell_len - len(indicator))
            self.border_title = base + " " * pad + indicator
        else:
            self.border_title = base
        self.border_subtitle = f"▼{below}" if below > 0 else ""

        # ── Dispatch to render functions ──────────────────────────────────
        if mode == "bio":
            return _render_bio(s, scroll=scroll)
        if mode == "missions":
            return _render_missions(s, scroll=scroll)
        if mode == "engineers":
            return _render_engineers(s, scroll=scroll)
        if mode == "wealth":
            return _render_wealth(s)
        if mode == "neutron":
            return _render_neutron(s, scroll=scroll)
        if mode == "inventory":
            return _render_inventory(s, scroll=scroll)
        if mode == "stats":
            return _render_stats(s)
        if mode == "docking":
            return _render_docking(s)
        if mode == "bgs":
            return _render_bgs(s, scroll=scroll)
        if mode == "colonisation":
            return _render_colonisation(s, scroll=scroll)
        if mode == "route":
            return _render_route(s, scroll=scroll, panel_height=panel_h)
        return _render_overview(s)


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

    HDR  = "bold rgb(195,160,55)"
    MAIN = "white"
    SUB  = P.LABEL

    tbl = Table(show_header=False, show_edge=False, show_lines=False,
                padding=(0, 1), box=None)
    tbl.add_column("label", width=12)
    tbl.add_column("today", width=7,  justify="right")
    tbl.add_column("week",  width=7,  justify="right")
    tbl.add_column("month", width=7,  justify="right")
    tbl.add_column("year",  width=8,  justify="right")
    tbl.add_column("total", width=8,  justify="right")

    # Header
    tbl.add_row(
        Text("",      style=HDR),
        Text("Today", style=HDR),
        Text("Week",  style=HDR),
        Text("Month", style=HDR),
        Text("Year",  style=HDR),
        Text("Total", style=HDR),
    )

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

    hdr = Text()
    hdr.append("STATISTICS\n", style=f"bold {P.AMBER}")

    disclaimer = Text(
        "* Estimated payouts incl. bonuses. Unsold data is retained if killed.",
        style="rgb(70,70,70)",
    )
    return Group(hdr, tbl, disclaimer)


def _render_docking(s: AppState) -> RenderableType:
    """Docking pad circular diagram — top-down view of the station.

    Ring layout (Coriolis/Orbis):
      Outer (1–12): large pads, outermost ring
      Mid-1 (13–24): large pads, second ring
      Mid-2 (25–36): medium pads, third ring
      Inner (37–40): small pads, axis centre
    """
    import math as _math

    pad = s.docked_pad
    stn = s.docked_station_name or s.station or "Unknown Station"
    stype = s.docked_station_type or s.station_type or ""

    parts: list[RenderableType] = []

    head = Text()
    head.append(f"DOCKING: {stn}\n", style="bold white")
    if stype:
        head.append(f"{stype}  ", style=P.LABEL)
    head.append("Pad ", style=P.LABEL)
    head.append(f"{pad}\n", style="bold rgb(0,255,150)")
    parts.append(head)

    # ── Circular grid diagram ────────────────────────────────────────────────
    # Characters are ~2× taller than wide, so rx ≈ 2 × ry for a round circle.
    W, H = 38, 13
    cx, cy = W // 2, H // 2

    # grid[row][col] = (char, style)
    BLANK = (" ", "")
    grid: list[list[tuple]] = [[BLANK] * W for _ in range(H)]

    def place(gx: int, gy: int, label: str, style: str) -> None:
        """Place label centred at (gx, gy), clipping to grid bounds."""
        sx = gx - len(label) // 2
        for j, ch in enumerate(label):
            x = sx + j
            if 0 <= gy < H and 0 <= x < W:
                grid[gy][x] = (ch, style)

    # Ring definitions: (start_pad, count, rx, ry)
    # Each ring has enough radius clearance so pad labels don't overlap.
    ring_defs = [
        ( 1, 12, 16, 5),  # outer large
        (13, 12, 11, 3),  # mid large
        (25, 12,  7, 2),  # mid medium
        (37,  4,  4, 1),  # inner small
    ]

    for start, count, rx, ry in ring_defs:
        for i in range(count):
            p = start + i
            # Angle 0 = top (pad 1 at 12 o'clock), clockwise
            angle = i * 2 * _math.pi / count
            gx = int(round(cx + rx * _math.sin(angle)))
            gy = int(round(cy - ry * _math.cos(angle)))
            is_mine = (p == pad)
            label   = f"[{p}]" if is_mine else f"{p:2}"
            style   = "bold rgb(0,255,150)" if is_mine else "dim rgb(65,65,65)"
            place(gx, gy, label, style)

    # Centre marker
    place(cx, cy, "·", "rgb(80,80,120)")

    diag = Text()
    for row in grid:
        for ch, sty in row:
            diag.append(ch, style=sty) if sty else diag.append(ch)
        diag.append("\n")
    parts.append(diag)

    # Ring hint
    hint = Text()
    if 1 <= pad <= 12:
        hint.append("Outer ring (large pad) — stay near the wall\n", style=P.LABEL)
    elif 13 <= pad <= 24:
        hint.append("Mid ring (large pad) — mid-distance from wall\n", style=P.LABEL)
    elif 25 <= pad <= 36:
        hint.append("Inner ring (medium pad)\n", style=P.LABEL)
    else:
        hint.append("Centre pad (small) — fly through the axis\n", style=P.LABEL)
    parts.append(hint)

    return Group(*parts)


def _render_bgs(s: AppState, scroll: int = 0) -> RenderableType:
    """BGS activity log: per-system per-faction activity counts (today's tick)."""
    if not s.bgs_log:
        t = Text()
        t.append("No BGS activity recorded today.", style=P.LABEL)
        return t

    parts: list[RenderableType] = []
    head = Text()
    head.append(f"BGS ACTIVITY  ", style="bold rgb(0,180,100)")
    head.append(f"({s.bgs_log_date})\n", style=P.LABEL)
    parts.append(head)

    rows: list[tuple] = []  # (system, faction, act_str, total)
    for sys_name, fac_map in s.bgs_log.items():
        for faction, acts in fac_map.items():
            total   = sum(acts.values())
            act_str = "  ".join(f"{v}×{k}" for k, v in sorted(acts.items(), key=lambda x: -x[1]))
            rows.append((sys_name, faction, act_str, total))

    rows.sort(key=lambda r: -r[3])
    visible = rows[scroll:]

    tbl = Table(show_header=True, show_edge=False, box=None, padding=(0, 1),
                header_style="dim rgb(130,130,130)")
    tbl.add_column("System/Faction", no_wrap=True)
    tbl.add_column("Activity",       no_wrap=True)
    tbl.add_column("Total", width=5, justify="right", no_wrap=True)

    for sys_name, faction, act_str, total in visible:
        fac_short = faction[:28]
        sys_str = sys_name if sys_name != s.system else f"● {sys_name}"
        tbl.add_row(
            Text(f"{sys_str}\n  {fac_short}", style="white"),
            Text(act_str, style=P.LABEL),
            Text(str(total), style=P.AMBER),
        )
    parts.append(tbl)
    return Group(*parts)


def _render_colonisation(s: AppState, scroll: int = 0) -> RenderableType:
    """Colonisation construction sites with commodity progress."""
    if not s.colonisation_sites:
        t = Text()
        t.append("No colonisation sites tracked.\n", style=P.LABEL)
        t.append("Approach a construction depot to populate this view.", style="dim rgb(100,100,100)")
        return t

    import math as _math
    parts: list[RenderableType] = []
    head = Text()
    head.append("COLONISATION SITES\n", style="bold rgb(255,200,0)")
    parts.append(head)

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
            site_head.append(f"  #{mkt_id}\n", style="dim rgb(100,100,100)")
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
            t.append("    Approach depot for commodity details\n", style="dim rgb(100,100,100)")
            parts.append(t)

    return Group(*parts)


def _render_route(s: AppState, scroll: int = 0, panel_height: int = 40) -> RenderableType:
    """Nav route panel: jump#, system, star class+scoopable, body count, dist, jump dist, EDSM."""
    import math as _math

    route = s.route_list
    if not route:
        t = Text()
        t.append("No nav route active.\n", style=P.LABEL)
        t.append("Set a route in-game to populate this view.", style="dim rgb(100,100,100)")
        return t

    edsm   = getattr(s, "route_list_edsm",   {})
    bodies = getattr(s, "route_bodies_edsm",  {})
    cur_pos = s.star_pos  # (x, y, z) or None

    _SCOOPABLE = frozenset("OBAFGKM")

    def _fmt_ly(d: float) -> str:
        if d <= 0:    return "—"
        if d >= 1000: return f"{d/1000:.1f}k"
        return f"{d:.1f}"

    def _star_col(sc: str) -> str:
        c = sc[:1] if sc else ""
        if c == "O": return "rgb(140,160,255)"
        if c == "B": return "rgb(180,210,255)"
        if c == "A": return "white"
        if c == "F": return "rgb(255,255,200)"
        if c == "G": return "rgb(255,230,120)"
        if c == "K": return "rgb(255,160,80)"
        if c == "M": return P.HUD_CRIT
        if c == "L": return "rgb(160,60,30)"
        if c in ("T", "Y"): return "rgb(100,80,60)"
        if c == "N": return "rgb(180,220,255)"
        if c == "H": return P.LABEL
        if sc.startswith("D"): return "rgb(200,230,255)"
        return P.LABEL

    # Skip current system (route[0]); display route[1:]
    display_route = route[1:]
    if not display_route:
        t = Text()
        t.append("Last jump — route complete.\n", style=P.LABEL)
        if s.route_destination:
            t.append(s.route_destination, style="white")
        return t

    # Compute total remaining distance (cur_pos → last waypoint)
    total_ly = 0.0
    if cur_pos:
        prev = cur_pos
        for entry in display_route:
            sp = entry.get("StarPos")
            if sp and isinstance(sp, list) and len(sp) >= 3:
                dx = sp[0] - prev[0]; dy = sp[1] - prev[1]; dz = sp[2] - prev[2]
                total_ly += _math.sqrt(dx*dx + dy*dy + dz*dz)
                prev = (sp[0], sp[1], sp[2])

    # ── Header ───────────────────────────────────────────────────────────────
    hops = s.route_hops
    word = "jump" if hops == 1 else "jumps"
    hdr = Text()
    hdr.append(f"  {hops} {word} remaining", style=P.AMBER)
    if total_ly > 0:
        hdr.append(f" ({_fmt_ly(total_ly)} ly)", style=P.LABEL)
    if s.route_destination:
        hdr.append(" → ", style=P.LABEL)
        hdr.append(s.route_destination, style="bold white")
    hdr.append("\n")

    parts: list[RenderableType] = [hdr]

    effective_scroll = min(scroll, max(0, len(display_route) - 1))

    tbl = Table(show_header=True, show_edge=False, box=None,
                padding=(0, 1), header_style=f"bold {P.LABEL}")
    tbl.add_column("#",      width=3,  justify="right",  no_wrap=True)
    tbl.add_column("System", width=18, no_wrap=True)
    tbl.add_column("★",      width=5,  no_wrap=True)
    tbl.add_column("Bd",     width=2,  justify="right",  no_wrap=True)
    tbl.add_column("Dist",   width=7,  justify="right",  no_wrap=True)
    tbl.add_column("Jump",   width=6,  justify="right",  no_wrap=True)
    tbl.add_column("✦",      width=1,  justify="center", no_wrap=True)

    # Dynamic rows: panel height minus header (1) + table header (1) + footer indicator (1) = 3
    max_rows = max(5, panel_height - 5)

    prev_pos = cur_pos
    visible  = display_route[effective_scroll:effective_scroll + max_rows]

    for i, entry in enumerate(visible, start=effective_scroll + 1):
        name       = entry.get("StarSystem", "?")
        pos_list   = entry.get("StarPos")
        star_class = entry.get("StarClass", "?")

        scoopable = star_class[:1] in _SCOOPABLE if star_class else False

        if cur_pos and pos_list:
            dx = pos_list[0] - cur_pos[0]
            dy = pos_list[1] - cur_pos[1]
            dz = pos_list[2] - cur_pos[2]
            dist_cur = _math.sqrt(dx*dx + dy*dy + dz*dz)
        else:
            dist_cur = 0.0

        if prev_pos and pos_list:
            dx = pos_list[0] - prev_pos[0]
            dy = pos_list[1] - prev_pos[1]
            dz = pos_list[2] - prev_pos[2]
            jump_d = _math.sqrt(dx*dx + dy*dy + dz*dz)
        else:
            jump_d = 0.0

        edsm_entry = edsm.get(name)
        if edsm_entry is None:
            edsm_text = Text("?", style=P.LABEL)
        elif edsm_entry.get("live_known") is False and not edsm_entry.get("x"):
            edsm_text = Text("✗", style=P.HUD_CRIT)
        else:
            edsm_text = Text("✓", style=P.HUD_GREEN)

        sc_short  = (star_class[:3] if star_class else "?").ljust(3)
        sc_col    = _star_col(star_class or "")
        star_cell = Text()
        star_cell.append(sc_short, style=sc_col)
        star_cell.append("⛽" if scoopable else " ·", style=P.HUD_GREEN if scoopable else "dim rgb(70,70,70)")

        population = (edsm_entry or {}).get("population", 0) or 0
        name_style = "rgb(255,235,180)" if population > 0 else "white"

        body_entry = bodies.get(name)
        if body_entry is None:
            bd_text = Text("…", style=P.LABEL)
        else:
            bd = body_entry.get("bodies", 0)
            bd_text = Text(str(bd) if bd else "·", style=P.WHITE if bd else "dim")

        tbl.add_row(
            Text(str(i), style=P.LABEL),
            Text(name[:18], style=name_style),
            star_cell,
            bd_text,
            Text(_fmt_ly(dist_cur), style=P.WHITE),
            Text(_fmt_ly(jump_d),   style=P.LABEL),
            edsm_text,
        )

        if pos_list:
            prev_pos = (pos_list[0], pos_list[1], pos_list[2])

    parts.append(tbl)

    return Group(*parts)


# ── Shared log-line renderer ──────────────────────────────────────────────────

def _render_log_lines(
    events: list,
    prefix_w: int,
    msg_w: int,
    format_prefix,  # Callable[[ev], Iterable[(str, str)]] → (text, style) pairs before message
    format_message,  # Callable[[ev], (lines: list[str], style: str, first_line_prefix: list)]
) -> Text:
    """Shared renderer: timestamp + prefix + wrapped message for any log panel.

    format_prefix(ev)  → list of (text, style) to append after the timestamp.
    format_message(ev) → (lines: list[str], msg_style: str, first_extra: list[(str,str)])
                         first_extra is appended on the first line before the message text.
    """
    t = Text()
    for ev in events:
        time_str = ev.time[:5]
        prefix_parts = format_prefix(ev)
        lines_text, msg_style, first_extra = format_message(ev)
        for i, line in enumerate(lines_text):
            if i == 0:
                t.append(f"{time_str} ", style="rgb(100,100,100)")
                for txt, sty in prefix_parts:
                    t.append(txt, style=sty)
                for txt, sty in first_extra:
                    t.append(txt, style=sty)
                t.append(line + "\n", style=msg_style)
            else:
                t.append(" " * prefix_w + line + "\n", style=msg_style)
    return t


# ── Event log panel ───────────────────────────────────────────────────────────

class EventLogPanel(_Panel):
    BORDER_TITLE = "◈ Event Log"

    DEFAULT_CSS = """
    EventLogPanel {
        border: solid rgb(70,70,70);
        border-title-color: white;
        border-title-style: bold;
    }
    """

    _scroll: int = 0

    def set_scroll(self, scroll: int) -> None:
        self._scroll = scroll
        self.refresh()

    def scroll_log(self, delta: int) -> None:
        s = self._snap
        events = [ev for ev in s.events if ev.category != EventCategory.Chat] if s else []
        max_s = max(0, len(events) - 1)
        self._scroll = max(0, min(self._scroll + delta, max_s))
        self.refresh()

    _CAT_ABBR = {
        EventCategory.Nav:     "NAV",
        EventCategory.Combat:  "COM",
        EventCategory.Explore: "EXP",
        EventCategory.Mission: "MIS",
        EventCategory.Trade:   "TRD",
        EventCategory.Status:  "STA",
        EventCategory.System:  "SYS",
        EventCategory.Warn:    "WRN",
        EventCategory.Chat:    "CHT",
    }

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        events  = [ev for ev in s.events if ev.category != EventCategory.Chat]
        visible = events[self._scroll:]

        above   = self._scroll
        panel_h = self.size.height or 0
        below   = max(0, len(events) - self._scroll - max(1, panel_h - 2))
        _base_ev = "◈ Event Log"
        if above > 0:
            _ind   = f" ▲{above}"
            _avail = (self.size.width or 20) - 4
            _pad   = max(1, _avail - Text.from_markup(_base_ev).cell_len - len(_ind))
            self.border_title = _base_ev + " " * _pad + _ind
        else:
            self.border_title = _base_ev
        self.border_subtitle = (f"▼{below}" if below > 0 else "")

        prefix_w  = 10  # "HH:MM " (6) + "NAV " (4)
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w

        def _prefix(ev):
            col  = ev.category.rich_color()
            abbr = self._CAT_ABBR.get(ev.category, "   ")
            return [(f"{abbr} ", col)]

        def _message(ev):
            warn      = ev.category == EventCategory.Warn
            msg_style = f"bold {P.HUD_CRIT}" if warn else "white"
            lines     = textwrap.wrap(ev.message, width=msg_w) or [""]
            return lines, msg_style, []

        return _render_log_lines(visible, prefix_w, msg_w, _prefix, _message)


# ── Chat log panel ────────────────────────────────────────────────────────────

class ChatLogPanel(_Panel):
    BORDER_TITLE = "◈ Chat"

    DEFAULT_CSS = """
    ChatLogPanel {
        border: solid rgb(0,120,160);
        border-title-color: rgb(0,160,210);
        border-title-style: bold;
    }
    """

    _scroll: int = 0

    def scroll_chat(self, delta: int) -> None:
        s = self._snap
        chats = [ev for ev in s.events if ev.category == EventCategory.Chat] if s else []
        max_s = max(0, len(chats) - 1)
        self._scroll = max(0, min(self._scroll + delta, max_s))
        self.refresh()

    # Source tag → (3-char abbrev, color)
    _SRC_TAGS: dict[str, tuple[str, str]] = {
        "[Twitch]":  ("TWI", "rgb(145,70,255)"),   # Twitch purple
        "[YouTube]": ("YTL", "rgb(255,70,70)"),    # YouTube red
        "[Wing]":    ("WNG", "rgb(0,175,185)"),    # Cyan
        "[Local]":   ("LCL", "rgb(160,160,160)"),  # Grey
        "[Sqn]":     ("SQN", "rgb(0,200,100)"),    # Green
        "[System]":  ("SYS", "rgb(195,150,0)"),    # Amber
        "[Friend]":  ("FRD", "rgb(60,130,210)"),   # Blue
    }

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("No chat.", style=P.LABEL)
        chats = [ev for ev in s.events if ev.category == EventCategory.Chat]
        if not chats:
            t = Text()
            t.append("No chat messages.", style=P.LABEL)
            return t
        effective_scroll = min(self._scroll, max(0, len(chats) - 1))

        above   = effective_scroll
        panel_h = self.size.height or 0
        below   = max(0, len(chats) - effective_scroll - max(1, panel_h - 2))
        _base_ch = "◈ Chat"
        if above > 0:
            _ind   = f" ▲{above}"
            _avail = (self.size.width or 20) - 4
            _pad   = max(1, _avail - Text.from_markup(_base_ch).cell_len - len(_ind))
            self.border_title = _base_ch + " " * _pad + _ind
        else:
            self.border_title = _base_ch
        self.border_subtitle = (f"▼{below}" if below > 0 else "")

        chats = chats[effective_scroll:]
        prefix_w  = 11  # "HH:MM " (6) + "TWI " (4) + padding 1
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w

        def _strip_tag(ev):
            msg = ev.message
            src_abbr, src_col = "MSG", "rgb(160,160,160)"
            for tag, (abbr, col) in self._SRC_TAGS.items():
                if msg.startswith(tag + " "):
                    src_abbr, src_col = abbr, col
                    msg = msg[len(tag) + 1:]
                    break
            return msg, src_abbr, src_col

        def _prefix(ev):
            _, src_abbr, src_col = _strip_tag(ev)
            return [(f"{src_abbr} ", f"bold {src_col}")]

        def _message(ev):
            msg, _, src_col = _strip_tag(ev)
            colon_idx = msg.find(": ")
            if colon_idx > 0:
                username = msg[:colon_idx]
                msg_body = msg[colon_idx + 2:]
            else:
                username, msg_body = "", msg
            display = f"{username}: {msg_body}" if username else msg_body
            lines   = textwrap.wrap(display, width=msg_w) or [""]
            # Build first-line username prefix (italic) if present
            first_extra = []
            if username and lines and lines[0].startswith(username + ": "):
                first_extra = [(username, f"italic {src_col}"),
                               (": " + lines[0][len(username)+2:], "white")]
                lines = ([""] + lines[1:]) if len(lines) > 1 else [""]
            return lines, "white", first_extra

        return _render_log_lines(chats, prefix_w, msg_w, _prefix, _message)



# ── Footer bar ────────────────────────────────────────────────────────────────

class FooterBar(_Panel):
    DEFAULT_CSS = """
    FooterBar {
        height: 1;
    }
    """

    def render(self) -> RenderableType:
        s   = self._snap
        vol = s.volume if s is not None else 50

        left = Text()
        key  = f"bold {P.AMBER}"
        lbl  = P.AMBER_DIM

        # Thread stall warning: show if journal or status thread silent >60s while online
        stall_msg = ""
        if s is not None and s.client_online:
            now = time.time()
            stalled = []
            if 0 < s.journal_heartbeat < now - 60:
                stalled.append("journal")
            if 0 < s.status_heartbeat < now - 60:
                stalled.append("status")
            if stalled:
                stall_msg = f"⚠ {'+'.join(stalled)} thread stalled"

        if stall_msg:
            left.append(f" {stall_msg} ", style="bold rgb(220,60,0)")
        else:
            left.append(" q",      style=key); left.append(" Quit ", style=lbl)
            left.append(" Tab",    style=key); left.append(" Mode ", style=lbl)
            left.append(" ?",      style=key); left.append(" Help ", style=lbl)
            left.append(" ↑↓",     style=key); left.append(" Scroll ", style=lbl)
            left.append(" m",      style=key)

        muted = s.muted if s is not None else False
        if stall_msg:
            pass  # stall takes over left side; still show volume on the right
        elif muted:
            left.append(" MUTED ", style="bold rgb(220,60,0)")
        else:
            left.append(" +/-",    style=key); left.append(f" Vol {vol}%", style="bold white")

        center = Text(justify="center")
        center.append(datetime.now().strftime("%H:%M:%S"), style="bold rgb(160,160,160)")

        right = Text(justify="right")
        if s is not None:
            if s.session_start:
                right.append(f"Online: {s.session_start}  ", style="rgb(110,110,110)")
            _append_edsm(right, s.edsm_status)
        right.append(f"  v{_NOVA_VERSION}", style="rgb(70,70,70)")

        tbl = Table.grid(expand=True)
        tbl.add_column("left",   no_wrap=True)
        tbl.add_column("center", justify="center", no_wrap=True)
        tbl.add_column("right",  justify="right",  no_wrap=True)
        tbl.add_row(left, center, right)
        return tbl


def _append_edsm(t: Text, st) -> None:
    t.append("EDSM ", style="bold rgb(100,100,100)")
    if not st.enabled:
        t.append("—", style=P.DIM)
        return
    if st.connected is None:
        t.append("…", style=P.AMBER)
    elif st.connected:
        t.append("●", style=P.HUD_GREEN)
    else:
        t.append("✗", style=P.HUD_CRIT)
    if st.last_rx:
        t.append(f"  {st.last_rx}", style="rgb(90,90,90)")
    if st.last_error:
        t.append(f"  {st.last_error}", style=P.HUD_WARN)
    t.append(" ")
