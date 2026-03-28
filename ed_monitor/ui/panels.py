from __future__ import annotations

import re
import textwrap
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

from ..state import AppState, BioScan, BodyInfo, EventCategory
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
        "Rocky ice body":                    "Rocky Ice",
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
    base = _BODY_EST_VALUES.get(b.planet_class, 0)
    if base > 0:
        if b.terraform:
            base = int(base * 2.5)
        # Apply discovery bonus (approx +50%)
        if b.first_discovered:
            base = int(base * 1.5)
    return base


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
        fss_done    = sum(1 for b in s.bodies if b.fss_scanned and b.planet_class)
        stars_found = sum(1 for b in s.bodies if b.star_type)
        fss_total   = max(0, s.fss_body_count - stars_found)

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

        if s.nearest_populated_name and s.population == 0:
            dist_str = f"{s.nearest_populated_dist:.0f} ly"
            left_cells.append(_cell("Nearest", f"{s.nearest_populated_name} ({dist_str})"))

        if s.nearest_body:
            left_cells.append(_cell("At", _short_name(s.nearest_body, s.system)))

        if s.lat is not None and s.lon is not None:
            pos = f"{s.lat:.2f}, {s.lon:.2f}"
            if s.altitude is not None:
                pos += f" alt{s.altitude:.0f}"
            left_cells.append(_cell("Pos", pos))

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

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

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

        on_foot  = s.client_online and not s.in_main_ship and not s.in_srv
        in_ship  = s.in_main_ship
        in_srv   = s.in_srv

        # Gauges — only when piloting (main ship or SRV); hidden when offline or on foot
        parts: list[RenderableType] = [Align.center(header)]
        if in_ship or in_srv:
            gauges = Columns([hull_panel, sh_panel, fuel_panel], expand=True, equal=True)
            parts.append(gauges)

            if s.cargo_capacity > 0 and in_ship:
                cargo_w     = max(4, self.size.width - 16)
                cargo_ratio = min(s.cargo / s.cargo_capacity, 1.0)
                cargo_txt   = Text(justify="center")
                cargo_txt.append(f"CARGO {s.cargo}/{s.cargo_capacity}  ", style="bold white")
                cargo_txt.append_text(_gauge_bar(cargo_ratio, cargo_w, "rgb(150,60,180)"))
                parts.append(Align.center(cargo_txt))

            # PIPs — only when in main ship
            if in_ship:
                pip_txt = Text(justify="center")
                pip_txt.append("SYS ", style=f"bold rgb(60,100,200)")
                pip_txt.append_text(_pip_bar(s.pips_sys, "rgb(60,100,200)"))
                pip_txt.append("  ENG ", style=f"bold rgb(160,200,60)")
                pip_txt.append_text(_pip_bar(s.pips_eng, "rgb(160,200,60)"))
                pip_txt.append("  WEP ", style=f"bold rgb(200,60,60)")
                pip_txt.append_text(_pip_bar(s.pips_wep, "rgb(200,60,60)"))
                parts.append(Align.center(pip_txt))

        # Separator
        sep_w = max(10, self.size.width - 4)
        parts.append(Text("─" * sep_w, style="rgb(60,60,60)"))

        # Status + contextual toggles — combined on one line, with breathing room above
        parts.append(Text(""))  # half-line spacer

        if not s.client_online:
            status_label, status_col = "OFL",  P.DIM
        elif on_foot:
            status_label, status_col = "FT",   "rgb(180,200,255)"
        elif s.supercruise:
            status_label, status_col = "SC",   P.HUD_CYAN
        elif s.docked:
            status_label, status_col = "DKCD", P.HUD_GREEN
        elif s.landed:
            status_label, status_col = "LAND", P.HUD_WARN
        elif in_srv:
            status_label, status_col = "SRV",  P.HUD_WARN
        else:
            status_label, status_col = "FLT",  P.LABEL

        btn_row: list[tuple[str, bool, str]] = [(status_label, True, status_col)]

        if in_ship:
            if s.analysis_mode:
                mode_label, mode_col = "ANL", "rgb(200,255,200)"
            else:
                mode_label, mode_col = "CMB", P.HUD_CRIT

            if s.docked:
                btn_row += [(mode_label, True, mode_col), ("LGT", s.lights_on, P.AMBER), ("N/V", s.night_vision, P.HUD_GREEN)]
            elif s.landed:
                btn_row += [(mode_label, True, mode_col), ("LGT", s.lights_on, P.AMBER), ("N/V", s.night_vision, P.HUD_GREEN), ("SLT", s.silent_running, P.HUD_CRIT)]
            elif s.supercruise:
                btn_row += [(mode_label, True, mode_col), ("FAO", s.flight_assist_off, P.HUD_CRIT), ("LGT", s.lights_on, P.AMBER), ("SLT", s.silent_running, P.HUD_CRIT)]
            else:
                btn_row += [(mode_label, True, mode_col), ("GER", s.landing_gear, P.AMBER), ("FAO", s.flight_assist_off, P.HUD_CRIT), ("SCP", s.cargo_scoop, P.AMBER), ("LGT", s.lights_on, P.AMBER), ("N/V", s.night_vision, P.HUD_GREEN), ("SLT", s.silent_running, P.HUD_CRIT)]
        elif in_srv:
            btn_row += [("LGT", s.lights_on, P.AMBER)]

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
    BORDER_TITLE = "◈ Route"

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

    def update(self, snap: AppState) -> None:
        self._snap = snap
        if snap.docked:
            self.border_title = f"◈ Docked: {snap.station}" if snap.station else "◈ Station"
        elif snap.target_body:
            short = _short_name(snap.target_body, snap.system)
            self.border_title = f"◈ Target: {short}"
        else:
            self.border_title = "◈ Route"
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        if s.docked:
            return self._render_station(s)
        if s.target_body:
            result = self._render_target(s)
            if result is not None:
                return result
        return self._render_route(s)

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

    def _render_target(self, s: AppState) -> Optional[RenderableType]:
        """Show body details for currently targeted body. Returns None if body not found."""
        body_name = s.target_body
        body = next((b for b in s.bodies if b.name == body_name), None)
        if body is None:
            return None

        t = Text()

        def row(label: str, value: str, vstyle: str = "white") -> None:
            t.append(f"{label:<8}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        short = _short_name(body_name, s.system)
        btype = _abbrev_type(body.planet_class, body.star_type)
        col   = _body_color(body.planet_class, body.star_type)

        t.append("TARGETING\n", style=f"bold {P.HUD_CYAN}")
        t.append(f"{short}\n", style=f"bold {col}")

        row("Type", btype, f"bold {col}")
        if body.dist_ls > 0.0:
            row("Dist", _fmt_ls(body.dist_ls), P.LABEL)

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

        v = body.value if body.value > 0 else _estimated_value(body)
        if v > 0:
            v_col = P.GOLD if v > 1_000_000 else (P.AMBER if body.value == 0 else "white")
            prefix = "~" if body.value == 0 else ""
            row("Value", f"{prefix}{_fmt_value(v)}", v_col)

        if body.first_discovered:
            t.append("★ First discovered!\n", style=f"bold {P.GOLD}")

        return t

    def _render_route(self, s: AppState) -> RenderableType:
        t = Text()

        if not s.route_destination:
            t.append("No route set\n", style=P.AMBER_DIM)
            if s.jump_dist > 0.0 or s.jump_dist_total > 0.0:
                if s.jump_dist > 0.0:
                    t.append("Last ", style=P.LABEL)
                    t.append(f"{s.jump_dist:.1f} ly", style="white")
                if s.jump_dist > 0.0 and s.jump_dist_total > 0.0:
                    t.append("  ·  ", style=P.DIM)
                if s.jump_dist_total > 0.0:
                    t.append("Session ", style=P.LABEL)
                    t.append(f"{s.jump_dist_total:.1f} ly", style=P.LABEL)
                t.append("\n")
            return t

        word = "jump" if s.route_hops == 1 else "jumps"
        t.append("→ ", style=f"bold {P.AMBER}")
        t.append(s.route_destination + "\n", style="bold white")

        # Compact: hops · next dist · total on one line
        t.append("  ")
        t.append(f"{s.route_hops} {word}", style=P.AMBER)
        if s.route_next_dist > 0:
            t.append(f"  ·  {s.route_next_dist:.1f} ly", style="rgb(120,120,120)")
        if s.route_dist > 0:
            t.append(f"  ({s.route_dist:.1f} total)", style=P.DIM)
        t.append("\n")

        if s.route_next:
            t.append("Next  ", style=P.LABEL)
            if s.route_hops == 1:
                t.append(s.route_next, style="bold white")
            else:
                t.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                star_desc = {
                    "N": "Neutron",
                    "H": "Black Hole",
                }.get(s.route_next_star) or (
                    "White Dwarf" if s.route_next_star.startswith("D")
                    else f"{s.route_next_star}"
                )
                mark     = "⛽" if s.route_next_scoopable else "✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                t.append(f"  {star_desc} {mark}", style=f"bold {star_col}")
            t.append("\n")

        # Next-waypoint stations (from EDSM dump cache)
        if s.route_next_stations:
            t.append("Stations at next:\n", style=P.LABEL)
            for stn in s.route_next_stations[:3]:
                icons = ""
                if stn.get("market"):     icons += "M"
                if stn.get("shipyard"):   icons += "S"
                if stn.get("outfitting"): icons += "O"
                if "Repair" in stn.get("services", []):  icons += "R"
                stn_name = stn["name"]
                if len(stn_name) > 16:
                    stn_name = stn_name[:15] + "…"
                dist_s = _fmt_ls_compact(stn["dist_ls"]) if stn["dist_ls"] > 0 else ""
                t.append(f"  {stn_name}", style="white")
                if dist_s:
                    t.append(f"  {dist_s}", style=P.LABEL)
                if icons:
                    t.append(f"  [{icons}]", style=P.AMBER)
                t.append("\n")


        # Compact last/total on one line
        if s.jump_dist > 0.0 or s.jump_dist_total > 0.0:
            if s.jump_dist > 0.0:
                t.append("Jump ", style=P.LABEL)
                t.append(f"{s.jump_dist:.1f} ly", style="white")
            if s.jump_dist > 0.0 and s.jump_dist_total > 0.0:
                t.append("  ·  ", style=P.DIM)
            if s.jump_dist_total > 0.0:
                t.append("Session ", style=P.LABEL)
                t.append(f"{s.jump_dist_total:.1f} ly", style=P.LABEL)
            t.append("\n")

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
        tbl.add_column("Body", style="white", width=11, header_style=HDR)
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
        
        # Sort bodies: single-star children first (A, B...), barycentre bodies last (AB, BC...)
        def _body_sort_key(b: BodyInfo) -> tuple:
            short = _short_name(b.name, system).strip()
            if not short and b.star_type and " " in b.name:
                m = re.search(r"\s+([A-Z0-9]{1,2})$", b.name)
                if m: short = m.group(1)

            if not short:
                return (0, "")  # Primary star always first

            parts = short.split()
            is_barycentre = not b.star_type and parts[0].isalpha() and len(parts[0]) > 1
            bucket = 1 if is_barycentre else 0

            # Zero-pad numbers for correct lexicographic ordering
            key_parts = [f"{int(p):04d}" if p.isdigit() else p.lower() for p in parts]
            return (bucket, " ".join(key_parts))

        visible.sort(key=_body_sort_key)

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
            # Stars / primary bodies:   level 0 (no indent)
            # Single-star planets:      level 1  (A 1, B 2, 1...)
            # Single-star moons:        level 2+ (A 1 a, 1 a...)
            # Barycentre planets:       level 0  (AB 4 — orbits the binary, not A)
            # Barycentre moons:         level 1  (AB 4 a)
            is_barycentre_body = not b.star_type and parts[0].isalpha() and len(parts[0]) > 1
            if b.star_type:
                level = 0
            elif parts[0][0].isdigit():
                level = len(parts)
            elif is_barycentre_body:
                level = max(0, len(parts) - 2)
            else:
                level = len(parts) - 1

            indent = " " * max(0, level)
            name   = indent + display_name
            btype  = _abbrev_type(b.planet_class, b.star_type)

            val     = _fmt_value_short(b.value if b.value > 0 else _estimated_value(b))
            val_col = (P.GOLD if b.value > 1_000_000
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

def _render_bio(s: AppState) -> RenderableType:
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

    total_known = sum(sc.value for sc in s.bio_scans if sc.complete and sc.value > 0)
    parts: list[RenderableType] = []

    # Pre-scan section: show genus list + value estimates before first sample
    for b in prescan_bodies:
        short = _short_name(b.name, s.system) if b.name and s.system else b.name
        hdr_t = Text()
        hdr_t.append("─" * 3, style="rgb(60,80,100)")
        hdr_t.append(f" {short} ", style="bold rgb(80,200,240)")
        hdr_t.append("(DSS) ", style="rgb(100,140,180)")
        hdr_t.append("─" * 14, style="rgb(60,80,100)")
        hdr_t.append("\n")
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
            val_s = f"~{_fmt_cr_compact(lo)}–{_fmt_cr_compact(hi)}" if lo > 0 else "?"
            tbl.add_row(
                Text(g, style=P.HUD_CYAN),
                Text(val_s, style=P.AMBER),
            )
        parts.append(tbl)

        if b.bio_value_min > 0:
            est_t = Text()
            est_t.append("Est. total  ", style=P.LABEL)
            est_t.append(
                f"~{_fmt_cr_compact(b.bio_value_min)}–{_fmt_cr_compact(b.bio_value_max)}",
                style=f"bold {P.GOLD}",
            )
            est_t.append("\n")
            parts.append(est_t)

    if not by_body and not prescan_bodies:
        t = Text()
        t.append("No biological scans active.", style=P.LABEL)
        return t

    for body_name in sorted(by_body):
        # Body header row
        short = _short_name(body_name, s.system) if body_name and s.system else body_name
        hdr_t = Text()
        hdr_t.append("─" * 3, style="rgb(60,80,100)")
        hdr_t.append(f" {short} ", style="bold rgb(80,200,240)")
        hdr_t.append("─" * 20, style="rgb(60,80,100)")
        hdr_t.append("\n")
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

        for sc in by_body[body_name]:
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
                bearing    = f" {sc.current_bearing}" if sc.current_bearing else ""
                travel_str = f"{bar}{bearing} {sc.current_dist:.0f}m"
                travel_col = P.HUD_GREEN if ratio >= 1.0 else P.HUD_WARN
            elif sc.samples == 0 or sc.complete:
                travel_str, travel_col = "—", P.DIM
            else:
                travel_str, travel_col = "No position", P.LABEL

            tbl.add_row(
                Text(species_str, style=name_style),
                Text(sc.genus_localised, style=P.HUD_CYAN),
                Text(samples_str, style=f"bold {samples_col}"),
                Text(min_str),
                Text(travel_str, style=travel_col),
                Text(value_str, style=f"bold {P.GOLD}" if sc.value > 0 else P.LABEL),
            )

        parts.append(tbl)

    if total_known > 0:
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


def _render_inventory(s: AppState) -> RenderableType:
    parts: list[RenderableType] = []

    if s.cargo_items:
        parts.append(_section_header("CARGO"))
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",  style="white")
        tbl.add_column("count", justify="right", style=P.AMBER)
        for item in s.cargo_items:
            style = "rgb(255,80,80)" if item.get("stolen") else "white"
            tbl.add_row(
                Text(item["name"], style=style),
                Text(str(item["count"]), style=f"bold {P.AMBER}"),
            )
        parts.append(tbl)

    for label, mdict in (
        ("RAW",          s.materials_raw),
        ("MANUFACTURED", s.materials_mfg),
        ("ENCODED",      s.materials_enc),
    ):
        if not mdict:
            continue
        parts.append(_section_header(label))
        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",  style="white")
        tbl.add_column("count", justify="right")
        for name in sorted(mdict):
            cnt = mdict[name]
            cnt_col = P.HUD_WARN if cnt >= 150 else ("white" if cnt >= 50 else P.LABEL)
            tbl.add_row(name, Text(str(cnt), style=f"bold {cnt_col}"))
        parts.append(tbl)

    if not parts:
        t = Text()
        t.append("No inventory data yet.", style=P.LABEL)
        return t

    return Group(*parts)


def _render_missions(s: AppState) -> RenderableType:
    if not s.missions:
        t = Text()
        t.append("No active missions.", style=P.LABEL)
        return t

    tbl = Table(
        show_header=True, show_edge=False, show_lines=False,
        padding=(0, 1), box=None,
    )
    HDR = "bold rgb(195,160,55)"
    tbl.add_column("Mission",     header_style=HDR)
    tbl.add_column("Destination", width=20, header_style=HDR)
    tbl.add_column("Time left",   width=9,  header_style=HDR, justify="right")

    for m in s.missions:
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

    return tbl


def _render_engineers(s: AppState) -> RenderableType:
    if not s.engineers:
        t = Text()
        t.append("No engineer data.", style=P.LABEL)
        return t

    tbl = Table(
        show_header=False, show_edge=False, show_lines=False,
        padding=(0, 1), box=None,
    )
    tbl.add_column("name",     style="white")
    tbl.add_column("progress", width=11)
    tbl.add_column("rank",     width=3, justify="right")

    for name in sorted(s.engineers):
        rank, progress = s.engineers[name]
        if progress == "Unlocked":
            prog_col = P.HUD_GREEN
            rank_str = str(rank) if rank > 0 else "—"
        elif progress in ("Invited", "Acquainted"):
            prog_col = P.AMBER
            rank_str = "—"
        else:
            prog_col = P.LABEL
            rank_str = "—"

        tbl.add_row(
            Text(name, style="white"),
            Text(progress, style=prog_col),
            Text(rank_str, style=f"bold {prog_col}"),
        )

    return tbl


def _render_overview(s: AppState) -> RenderableType:
    """Travel overview: route + galaxy position + system diagram + notable bodies + session stats."""
    import math
    parts: list[RenderableType] = []

    # Route section
    route_text = Text()
    if s.route_destination:
        route_text.append("ROUTE  ", style=P.LABEL)
        route_text.append(f"→ {s.route_destination}", style="bold white")
        hops = f"  {s.route_hops} jump{'s' if s.route_hops != 1 else ''} remaining"
        route_text.append(hops + "\n", style=P.AMBER)
        if s.route_next:
            route_text.append("NEXT   ", style=P.LABEL)
            route_text.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                mark     = "⛽" if s.route_next_scoopable else "✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                route_text.append(f"  {s.route_next_star} {mark}", style=f"bold {star_col}")
            route_text.append("\n")
    else:
        route_text.append("No route set.\n", style=P.AMBER_DIM)
    parts.append(route_text)

    # Galaxy position
    if s.star_pos:
        x, y, z = s.star_pos
        dist_sol  = math.sqrt(x**2 + y**2 + z**2)
        core_x, core_y, core_z = 25.21875, -20.90625, 25899.96875
        dist_core = math.sqrt((x - core_x)**2 + (y - core_y)**2 + (z - core_z)**2)
        
        gal_text = Text()
        gal_text.append("\nGALAXY POSITION\n", style="bold rgb(195,160,55)")
        gal_text.append(f"  Sol   ", style=P.LABEL)
        gal_text.append(f"{dist_sol:,.0f} ly\n".replace(",", _NNBSP), style="white")
        gal_text.append(f"  Core  ", style=P.LABEL)
        gal_text.append(f"{dist_core:,.0f} ly\n".replace(",", _NNBSP), style="white")
        gal_text.append(f"  Pos   ", style=P.LABEL)
        gal_text.append(f"{x:.0f} / {y:.0f} / {z:.0f}\n", style="rgb(150,150,150)")
        parts.append(gal_text)

    # System bodies diagram — hierarchical: *---O-o-o---O-o---O---*---O---
    _sys     = s.system
    _s_stars   = sorted([b for b in s.bodies if b.star_type],
                        key=lambda b: (0 if not _short_name(b.name, _sys).strip() else 1,
                                       _natural_key(_short_name(b.name, _sys))))
    _s_planets = sorted([b for b in s.bodies if b.planet_class and b.level <= 1],
                        key=lambda b: _natural_key(_short_name(b.name, _sys)))
    _s_moons   = sorted([b for b in s.bodies if b.planet_class and b.level == 2],
                        key=lambda b: _natural_key(_short_name(b.name, _sys)))

    if _s_stars or _s_planets:
        diag = Text()
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
        # ruler_chars: list of (char, rich_style)
        # body_pos:    list of (ruler_index, BodyInfo)
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
                p_col   = _body_color(planet.planet_class, planet.star_type)
                _emit("O", f"bold {p_col}", planet)
                for moon in sorted(planet_moons.get(p_short, []),
                                   key=lambda b: _natural_key(_short_name(b.name, _sys))):
                    _sep(1)
                    _emit("o", _body_color(moon.planet_class, moon.star_type), moon)

        # Barycentre planets at the end (orbit the binary, not a single star)
        for planet in barycentre_planets:
            _sep(3)
            p_short = _short_name(planet.name, _sys).strip()
            p_col   = _body_color(planet.planet_class, planet.star_type)
            _emit("O", f"bold {p_col}", planet)
            for moon in sorted(planet_moons.get(p_short, []),
                               key=lambda b: _natural_key(_short_name(b.name, _sys))):
                _sep(1)
                _emit("o", _body_color(moon.planet_class, moon.star_type), moon)

        W = len(ruler_chars)
        if W:
            # Split wide diagrams into multiple parts (max width per part)
            max_width = 60  # Maximum width before splitting
            num_parts = max(1, (W + max_width - 1) // max_width)
            
            for part_idx in range(num_parts):
                start = part_idx * max_width
                end = min((part_idx + 1) * max_width, W)
                
                # ── Row 1: ruler (part) ──────────────────────────────────────
                row1 = Text("  ")
                for i in range(start, end):
                    ch, style = ruler_chars[i]
                    row1.append(ch, style=style)
                row1.append("\n")

                # ── Row 2: last label of each body (part) ────────────────────
                def _last_label(b: BodyInfo) -> str:
                    short = _short_name(b.name, _sys).strip()
                    return short.split()[-1] if short else "A"

                name_arr = [" "] * (end - start)
                for pos, b in body_pos:
                    if start <= pos < end:
                        lbl = _last_label(b)
                        rel_pos = pos - start
                        for i, ch in enumerate(lbl):
                            if rel_pos + i < len(name_arr) and name_arr[rel_pos + i] == " ":
                                name_arr[rel_pos + i] = ch
                row2 = Text("  ")
                row2.append("".join(name_arr) + "\n", style="rgb(160,160,160)")

                # ── Row 3: notable (+) (part) ────────────────────────────────
                notable_arr = [" "] * (end - start)
                for pos, b in body_pos:
                    if start <= pos < end:
                        if (b.planet_class in ("Earthlike body", "Water world", "Ammonia world")
                                or b.terraform or b.value > 1_000_000):
                            notable_arr[pos - start] = "+"
                has_notable = any(c != " " for c in notable_arr)

                # ── Row 4: bio signal counts (part) ────────────────────────
                bio_arr = [" "] * (end - start)
                for pos, b in body_pos:
                    if start <= pos < end:
                        if b.bio_signals > 0:
                            bio_arr[pos - start] = str(b.bio_signals)
                has_bio = any(c != " " for c in bio_arr)

                diag.append_text(row1)
                diag.append_text(row2)
                if has_notable:
                    row3 = Text("  ")
                    row3.append("".join(notable_arr) + "\n", style=f"bold {P.GOLD}")
                    diag.append_text(row3)
                if has_bio:
                    row4 = Text("  ")
                    row4.append("".join(bio_arr) + "\n", style="rgb(0,200,80)")
                    diag.append_text(row4)
                
                if part_idx < num_parts - 1:
                    diag.append("\n")  # Add spacing between parts

        parts.append(diag)

    # Notable bodies in current system
    notable = [
        b for b in s.bodies
        if b.planet_class in (
            "Earthlike body", "Water world", "Ammonia world",
        ) or b.terraform or b.bio_signals > 0 or b.value > s.notable_value_threshold
    ]
    if notable:
        notable.sort(key=lambda b: _natural_key(_short_name(b.name, s.system)))
        hdr = Text()
        hdr.append("\nNOTABLE BODIES\n", style="bold rgb(195,160,55)")
        parts.append(hdr)

        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",  style="white", width=10)
        tbl.add_column("type",  width=10)
        tbl.add_column("val",   width=12, justify="right")
        tbl.add_column("bio",   width=12, justify="right")
        tbl.add_column("flags", width=4)

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

            # Bio completion state
            has_bio      = b.bio_signals > 0
            bio_done_cnt = _bio_done_cnt.get(b.name, 0)
            bio_all_done = has_bio and bio_done_cnt >= b.bio_signals
            actual_bio   = _bio_actual_cr.get(b.name, 0) if bio_all_done else 0

            # "Done" = body scanned (mapped) AND bio complete (or no bio)
            scan_done = b.mapped
            bio_done  = bio_all_done or not has_bio
            all_done  = scan_done and bio_done

            # Body scan value
            body_v = b.value if b.value > 0 else _estimated_value(b)

            if all_done:
                # Combined total — fold bio into val column
                total = body_v + actual_bio
                val_s = _fmt_value(total) if total > 0 else "—"
                vcol  = P.GOLD
                bio_s = "✓"
                bio_c = P.HUD_GREEN
            elif bio_all_done:
                # Bio done but body not yet mapped — show separate values
                val_s = _fmt_value(body_v) if body_v > 0 else "—"
                vcol  = P.AMBER if b.value == 0 else P.GOLD
                bio_s = _fmt_cr_compact(actual_bio) if actual_bio > 0 else "✓"
                bio_c = P.GOLD
            else:
                # In-progress — body value and bio estimate
                val_s = _fmt_value(body_v) if body_v > 0 else "—"
                vcol  = P.GOLD if b.value > 1_000_000 else (P.AMBER if body_v > 0 else P.DIM)
                if has_bio:
                    if b.bio_value_max > 0:
                        bio_s = f"~{_fmt_cr_compact(b.bio_value_min)}–{_fmt_cr_compact(b.bio_value_max)}"
                        bio_c = P.AMBER
                    else:
                        bio_s = f"{b.bio_signals}×"
                        bio_c = P.HUD_GREEN
                else:
                    bio_s = "—"
                    bio_c = P.DIM

            # Name/type style — dim when all done (already collected)
            dim_done = all_done
            name_style = "rgb(110,110,110)" if dim_done else "white"
            type_style = f"rgb(110,110,110)" if dim_done else f"bold {body_col}"

            flags = ""
            if b.terraform:        flags += "T"
            if b.first_discovered: flags += "★"
            if all_done:           flags += "✓"
            elif bio_all_done:     flags += "B"  # bio done, body scan pending

            tbl.add_row(
                Text(short, style=name_style),
                Text(btype, style=type_style),
                Text(val_s, style=vcol),
                Text(bio_s, style=bio_c),
                Text(flags, style=P.HUD_GREEN if not dim_done else "rgb(80,140,80)"),
            )
        parts.append(tbl)

    # Session stats block (when there's activity)
    if s.session_jumps > 0 or s.session_first_disc > 0 or s.session_mapped > 0 or s.session_value > 0:
        sess_tbl = Table(show_header=False, box=None, padding=(0, 1), expand=False)
        sess_tbl.add_column("k1", style=P.LABEL, no_wrap=True)
        sess_tbl.add_column("v1", style="white",  no_wrap=True)
        sess_tbl.add_column("k2", style=P.LABEL,  no_wrap=True)
        sess_tbl.add_column("v2", style="white",  no_wrap=True)

        sess_head = Text()
        sess_head.append("\nSESSION\n", style=f"bold {P.AMBER}")
        parts.append(sess_head)

        val_s = _fmt_cr_compact(s.session_value) if s.session_value > 0 else "—"
        sess_tbl.add_row(
            "Jumps",  str(s.session_jumps)      if s.session_jumps      else "—",
            "Disc",   str(s.session_first_disc) if s.session_first_disc else "—",
        )
        sess_tbl.add_row(
            "Mapped", str(s.session_mapped)     if s.session_mapped     else "—",
            "Value",  val_s,
        )
        parts.append(sess_tbl)

    # System summary — when no notable bodies and system is inhabited
    has_notable = any(True for b in s.bodies if (
        b.bio_signals > 0 or b.terraform or
        b.planet_class in ("Earthlike body", "Water world", "Ammonia world") or
        b.value >= s.notable_value_threshold
    ))
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

    # Fleet carriers (from Spansh API, when carrier_lookup enabled)
    if s.carriers_current_system:
        import math as _math
        car_head = Text()
        car_head.append("\nFLEET CARRIERS\n", style="bold rgb(100,180,255)")
        parts.append(car_head)

        for c in s.carriers_current_system[:5]:
            c_name     = c.get("name", "")
            c_system   = c.get("system_name", "")
            c_dist_ls  = c.get("dist_ls", 0.0)
            c_updated  = c.get("updated_at", "")
            c_x        = c.get("sys_x", 0.0)
            c_y        = c.get("sys_y", 0.0)
            c_z        = c.get("sys_z", 0.0)

            # Compute Ly distance from current position
            ly_dist: Optional[float] = None
            jumps_est: Optional[int] = None
            if s.star_pos and (c_x or c_y or c_z):
                px, py, pz = s.star_pos
                ly_dist = _math.sqrt((px-c_x)**2 + (py-c_y)**2 + (pz-c_z)**2)
                if s.jump_dist > 0 and ly_dist > 0:
                    jumps_est = _math.ceil(ly_dist / s.jump_dist)

            # Location line
            loc_txt = Text()
            loc_txt.append("  " + c_name + "\n", style="bold white")
            loc_txt.append("  ", style="")
            in_current = c_system and c_system.lower() == s.system.lower()
            if c_system:
                loc_txt.append(c_system, style=P.HUD_CYAN if in_current else P.AMBER)
            if in_current and c_dist_ls > 0:
                loc_txt.append(f"  {_fmt_ls_compact(c_dist_ls)}", style=P.LABEL)
            elif ly_dist is not None:
                loc_txt.append(f"  {ly_dist:.0f} ly", style=P.LABEL)
                if jumps_est is not None:
                    loc_txt.append(f"  ~{jumps_est} jump{'s' if jumps_est != 1 else ''}", style="rgb(130,130,130)")
            if c_updated:
                ago = _fmt_ago(c_updated)
                if ago:
                    loc_txt.append(f"  {ago}", style="rgb(100,100,100)")
            loc_txt.append("\n", style="")

            # Services line
            icons = ""
            if c.get("market"):     icons += "M"
            if c.get("shipyard"):   icons += "S"
            if c.get("outfitting"): icons += "O"
            if icons:
                loc_txt.append(f"  [{icons}]\n", style=P.AMBER)

            parts.append(loc_txt)

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

    framed = Panel(canvas_text, title=title_str, title_align="center",
                   border_style=P.LABEL, padding=(0, 0), expand=True)

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

    _MODES           = ("auto", "overview", "inventory", "bio", "missions", "engineers", "galaxy", "stats")
    _mode:   str     = "auto"
    _active: str     = "overview"
    _galaxy_regional: bool = False

    DEFAULT_CSS = """
    SituationalPanel {
        border: solid rgb(90,90,90);
        border-title-color: rgb(180,180,180);
        border-title-style: bold;
        height: 1fr;
    }
    """

    def cycle(self) -> None:
        idx = self._MODES.index(self._mode)
        self._mode = self._MODES[(idx + 1) % len(self._MODES)]
        if self._snap is not None:
            self._active = self._resolve(self._snap)
        self.border_title = self._make_title()
        self.refresh()

    def toggle_galaxy_scale(self) -> None:
        """Toggle between galactic and regional scale in galaxy mode."""
        self._galaxy_regional = not self._galaxy_regional
        self.refresh()

    def _resolve(self, s: AppState) -> str:
        if self._mode != "auto":
            return self._mode
        # Offline: no live game data — show statistics
        if not s.client_online:
            return "stats"
        # Incomplete bio scans — player is actively scanning
        if any(not sc.complete for sc in s.bio_scans):
            return "bio"
        # Approaching or on a DSS'd body with bio signals — show pre-scan genus list
        body_name = s.approach_body or (s.nearest_body if (s.landed or s.in_srv) else "")
        if body_name:
            idx = s._bodies_by_name.get(body_name, -1)
            if 0 <= idx < len(s.bodies) and s.bodies[idx].bio_genuses:
                return "bio"
        # Show missions when active (not in supercruise)
        if s.missions and not s.supercruise:
            return "missions"
        return "overview"

    def _make_title(self) -> str:
        if self._mode == "auto":
            return f"◈ Situation: AUTO→{self._active.upper()}  [Tab]"
        return f"◈ Situation: {self._mode.upper()}  [Tab]"

    def update(self, snap: AppState) -> None:
        self._snap   = snap
        self._active = self._resolve(snap)
        self.border_title = self._make_title()
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")
        if self._active == "bio":
            return _render_bio(s)
        if self._active == "missions":
            return _render_missions(s)
        if self._active == "engineers":
            return _render_engineers(s)
        if self._active == "inventory":
            return _render_inventory(s)
        if self._active == "galaxy":
            return _render_galaxy(s, regional=self._galaxy_regional,
                                  panel_w=self.size.width, panel_h=self.size.height)
        if self._active == "stats":
            return _render_stats(s)
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

    return Panel(tbl, title="STATISTICS", title_align="left",
                 border_style=P.LABEL, padding=(0, 0), expand=True)


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

        t       = Text()
        events  = [ev for ev in s.events if ev.category != EventCategory.Chat]
        visible = events[self._scroll:]

        prefix_w  = 10  # "HH:MM " (6) + "NAV " (4)
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w

        for ev in visible:
            col  = ev.category.rich_color()
            warn = ev.category == EventCategory.Warn
            msg_style = f"bold {P.HUD_CRIT}" if warn else "white"
            abbr      = self._CAT_ABBR.get(ev.category, "   ")
            time_str  = ev.time[:5]  # "HH:MM" (trim seconds)
            lines     = textwrap.wrap(ev.message, width=msg_w) or [""]
            for i, line in enumerate(lines):
                if i == 0:
                    t.append(f"{time_str} ", style="rgb(100,100,100)")
                    t.append(f"{abbr} ", style=col)
                else:
                    t.append(" " * prefix_w)
                t.append(line + "\n", style=msg_style)

        return t


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
        prefix_w  = 11  # "HH:MM " (6) + "TWI " (4) + padding 1
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w
        t = Text()
        for ev in chats:
            msg = ev.message
            # Detect and strip source tag from message
            src_abbr  = "MSG"
            src_col   = "rgb(160,160,160)"
            for tag, (abbr, col) in self._SRC_TAGS.items():
                if msg.startswith(tag + " "):
                    src_abbr = abbr
                    src_col  = col
                    msg = msg[len(tag) + 1:]  # strip tag + space
                    break
            time_str = ev.time[:5]  # HH:MM
            # Split "Username: message" — make username italic
            colon_idx = msg.find(": ")
            if colon_idx > 0:
                username    = msg[:colon_idx]
                msg_body    = msg[colon_idx + 2:]
            else:
                username    = ""
                msg_body    = msg
            display     = f"{username}: {msg_body}" if username else msg_body
            lines = textwrap.wrap(display, width=msg_w) or [""]
            for i, line in enumerate(lines):
                if i == 0:
                    t.append(f"{time_str} ", style="rgb(100,100,100)")
                    t.append(f"{src_abbr} ", style=f"bold {src_col}")
                    if username and line.startswith(username + ": "):
                        t.append(username, style=f"italic {src_col}")
                        t.append(": " + line[len(username)+2:] + "\n", style="white")
                    else:
                        t.append(line + "\n", style="white")
                else:
                    t.append(" " * prefix_w)
                    t.append(line + "\n", style="white")
        return t



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
        left.append(" q",      style=key); left.append(" Quit ", style=lbl)
        left.append(" Tab",    style=key); left.append(" Mode ", style=lbl)
        left.append(" ?",      style=key); left.append(" Help ", style=lbl)
        left.append(" ↑↓",     style=key); left.append(" Scroll ", style=lbl)
        left.append(" +/-",    style=key); left.append(f" Vol {vol}%", style="bold white")

        right = Text(justify="right")
        if s is not None:
            if s.session_start:
                right.append(f"Online: {s.session_start}  ", style="rgb(110,110,110)")
                parts = []
                if s.session_jumps:      parts.append(f"{s.session_jumps}J")
                if s.session_first_disc: parts.append(f"{s.session_first_disc}D")
                if s.session_mapped:     parts.append(f"{s.session_mapped}M")
                if parts:
                    right.append("· " + " ".join(parts) + "   ", style="rgb(90,90,90)")
            _append_edsm(right, s.edsm_status)
        right.append(f"  v{_NOVA_VERSION}", style="rgb(70,70,70)")

        tbl = Table.grid(expand=True)
        tbl.add_column("left", no_wrap=True)
        tbl.add_column("right", justify="right", no_wrap=True)
        tbl.add_row(left, right)
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
