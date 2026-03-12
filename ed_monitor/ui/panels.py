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


def _fmt_ls_compact(ls: float) -> str:
    if ls <= 0: return "—"
    if ls >= 100:            return f"{int(ls):,}".replace(",", _NNBSP) + " ls"
    return f"{ls:.0f} ls"


def _fmt_pop(n: int) -> str:
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
    if n >= 1_000:         return f"{n/1_000:.1f}K"
    return str(n)


def _pl(n: int) -> str:
    return "" if n == 1 else "s"


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

        t = Text()

        def row(label: str, value: str, vstyle: str = P.WHITE) -> None:
            t.append(f"{label:<9}", style=P.LABEL)
            t.append(value + "\n", style=vstyle)

        row("System", s.system, "bold white")

        if s.population > 0:
            row("Pop", _fmt_pop(s.population))
        if s.economy:
            row("Economy", s.economy)
        if s.security:
            col = (P.HUD_GREEN if "High" in s.security
                   else P.HUD_WARN if "Medium" in s.security
                   else P.HUD_CRIT)
            row("Security", s.security, f"bold {col}")
        if s.government:
            row("Gov", s.government)
        if s.allegiance:
            row("Alleg", s.allegiance)
        if s.controlling_faction:
            faction_str = (
                f"{s.controlling_faction} [{s.controlling_state}]"
                if s.controlling_state and s.controlling_state != "None"
                else s.controlling_faction
            )
            row("Faction", faction_str)

        stars   = sum(1 for b in s.bodies if b.star_type)
        planets = sum(1 for b in s.bodies if b.planet_class and b.level <= 1)
        moons   = sum(1 for b in s.bodies if b.planet_class and b.level == 2)
        fss_done = sum(1 for b in s.bodies if b.fss_scanned)

        if stars or planets:
            parts = [f"{stars} star{_pl(stars)}"]
            if planets: parts.append(f"{planets} planet{_pl(planets)}")
            if moons:   parts.append(f"{moons} moon{_pl(moons)}")
            row("Bodies", ", ".join(parts))

        # FSS progress (ignore stars as requested)
        fss_done = sum(1 for b in s.bodies if b.fss_scanned and not b.star_type)
        stars_found = sum(1 for b in s.bodies if b.star_type)
        fss_total = max(0, s.fss_body_count - stars_found)

        if fss_total > 0:
            fss_col = P.HUD_GREEN if fss_done >= fss_total else P.AMBER
            row("FSS", f"{fss_done} / {fss_total}", fss_col)

        if s.station_count > 0:
            row("Stations", str(s.station_count))

        if s.nearest_body:
            row("At", _short_name(s.nearest_body, s.system))

        if s.lat is not None and s.lon is not None:
            pos = f"{s.lat:.2f}, {s.lon:.2f}"
            if s.altitude is not None:
                pos += f"  alt {s.altitude:.0f}m"
            row("Pos", pos)

        # Session stats removed (moved to footer)
        return t


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
        sh_label = "100%" if s.shields_up else "DOWN"
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

        gauges = Columns([hull_panel, sh_panel, fuel_panel], expand=True, equal=True)
        parts: list[RenderableType] = [Align.center(header), gauges]

        if s.cargo_capacity > 0:
            cargo_w     = max(4, self.size.width - 16)
            cargo_ratio = min(s.cargo / s.cargo_capacity, 1.0)
            cargo_txt   = Text(justify="center")
            cargo_txt.append(f"CARGO {s.cargo}/{s.cargo_capacity}  ", style="bold white")
            cargo_txt.append_text(_gauge_bar(cargo_ratio, cargo_w, "rgb(150,60,180)"))
            parts.append(Align.center(cargo_txt))

        modes_txt = Text()
        on_foot = not s.in_main_ship and not s.in_srv
        modes = [
            ("SUPERCRUISE", s.supercruise and s.in_main_ship,                                              P.HUD_CYAN),
            ("DOCKED",      s.docked,                                                                      P.HUD_GREEN),
            ("LANDED",      s.landed and not s.docked and s.in_main_ship,                                  P.HUD_WARN),
            ("SRV",         s.in_srv,                                                                      P.HUD_WARN),
            ("NORMAL SPC",  s.in_main_ship and not s.supercruise and not s.docked and not s.landed,        P.LABEL),
        ]
        _append_buttons(modes_txt, modes)
        parts.append(Align.center(modes_txt))
        parts.append(Text(""))

        toggles_txt = Text()
        on_foot = not s.in_main_ship and not s.in_srv and s.client_online
        if on_foot:
            mode_label = "ON FOOT"
            mode_col   = P.PURPLE
        elif not s.client_online:
            mode_label = "OFFLINE"
            mode_col   = P.DIM
        elif s.analysis_mode:
            mode_label = "ANALYSIS"
            mode_col   = P.HUD_GREEN  # Changed from P.ANALYSIS to green tone
        else:
            mode_label = "COMBAT"
            mode_col   = P.HUD_CRIT
        toggles = [
            (mode_label, True, mode_col),
            ("GEAR↓",    s.landing_gear,      P.AMBER),
            ("FA OFF",   s.flight_assist_off, P.HUD_CRIT),
            ("SCOOP",    s.cargo_scoop,       P.AMBER),
            ("LIGHTS",   s.lights_on,         P.AMBER),
            ("VISION",   s.night_vision,      P.HUD_GREEN),
            ("SILENT",   s.silent_running,    P.HUD_CRIT),
        ]
        _append_buttons(toggles_txt, toggles)
        parts.append(Align.center(toggles_txt))

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
            if s.jump_dist > 0.0:
                t.append("Last  ", style=P.LABEL)
                t.append(f"{s.jump_dist:.1f} ly\n")
            if s.jump_dist_total > 0.0:
                t.append("Total ", style=P.LABEL)
                t.append(f"{s.jump_dist_total:.1f} ly this session\n", style=P.LABEL)
            return t

        word = "jump" if s.route_hops == 1 else "jumps"
        word = "jump" if s.route_hops == 1 else "jumps"
        t.append("→ ", style=f"bold {P.AMBER}")
        t.append(s.route_destination + "\n", style="bold white")
        t.append("  ")
        t.append(f"{s.route_hops} {word}", style=P.AMBER)
        if s.route_next_dist > 0:
            t.append(f"  ({s.route_next_dist:.1f} ly next)", style="rgb(120,120,120)")
        t.append(f"\n  Total {s.route_dist:.1f} ly\n", style=P.DIM)

        if s.route_next:
            t.append("Next  ", style=P.LABEL)
            if s.route_hops == 1:
                # Next IS the destination — show it prominently
                t.append(s.route_next, style="bold white")
            else:
                t.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                star_desc = {
                    "N": "Neutron",
                    "H": "Black Hole",
                }.get(s.route_next_star) or (
                    "White Dwarf" if s.route_next_star.startswith("D")
                    else f"{s.route_next_star} class"
                )
                mark     = "⛽" if s.route_next_scoopable else "✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                t.append(f"\n      {star_desc} {mark}", style=f"bold {star_col}")
            t.append("\n")

        if s.jump_dist > 0.0:
            t.append("Last  ", style=P.LABEL)
            t.append(f"{s.jump_dist:.1f} ly\n")
        if s.jump_dist_total > 0.0:
            t.append("Total ", style=P.LABEL)
            t.append(f"{s.jump_dist_total:.1f} ly this session\n", style=P.LABEL)

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
        tbl.add_column("Type", width=10, header_style=HDR)
        tbl.add_column("Val",  width=11, header_style=HDR, justify="right")
        tbl.add_column("Dist", width=11, header_style=HDR, justify="right")
        tbl.add_column("B",    width=2,  header_style=HDR)
        tbl.add_column("G",    width=2,  header_style=HDR)
        tbl.add_column("LTA",  width=5,  header_style=HDR)
        tbl.add_column("F",    width=2,  header_style=HDR)
        tbl.add_column("D",    width=2,  header_style=HDR)

        system  = s.system
        visible = [b for b in s.bodies if b.planet_class or b.star_type]
        
        # Sort by actual name component. "A 1 a" -> ["A", 1, "a"]
        def _body_sort_key(b: BodyInfo) -> list:
            short = _short_name(b.name, system).strip()
            # If short is empty but looks like it has a designation, extract it
            if not short and b.star_type and " " in b.name:
                m = re.search(r"\s+([A-Z0-9]{1,2})$", b.name)
                if m: short = m.group(1)

            if not short: 
                return [(-1, "")] # Primary star/body always first
            
            # Priority: Alpha (Stars) 0, then Digits (Planets) 1
            parts = []
            for part in short.split():
                if part.isdigit():
                    parts.append((1, int(part)))
                else:
                    parts.append((0, part.lower()))
            return parts
            
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

            # Hierarchical Indentation Logic:
            # - Level 0: Stars (Designations A, B or Primary star name)
            # - Level 1: Planets (Orbital numbers 1, 2, 3 or A 1, AB 1)
            # - Level 2+: Moons and sub-satellites (1 a, A 1 a, A 1 a 1)
            if b.star_type:
                level = 0
            elif parts[0][0].isdigit():
                # Primary system planets/moons (1, 1 a, 2...)
                level = len(parts)
            else:
                # Secondary/Binary system planets/moons (A 1, AB 1 a...)
                # The letter designation (parts[0]) is level 0, then we add levels.
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
    if not s.bio_scans:
        t = Text()
        t.append("No biological scans active.", style=P.LABEL)
        return t

    HDR = "bold rgb(195,160,55)"

    # Group by body
    from collections import defaultdict as _dd
    by_body: dict = _dd(list)
    for sc in s.bio_scans:
        by_body[sc.body or "Unknown"].append(sc)

    total_known = sum(sc.value for sc in s.bio_scans if sc.complete and sc.value > 0)
    parts: list[RenderableType] = []

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
    t = Text()

    # Route section
    if s.route_destination:
        t.append("ROUTE  ", style=P.LABEL)
        t.append(f"→ {s.route_destination}", style="bold white")
        hops = f"  {s.route_hops} jump{'s' if s.route_hops != 1 else ''} remaining"
        t.append(hops + "\n", style=P.AMBER)
        if s.route_next:
            t.append("NEXT   ", style=P.LABEL)
            t.append(s.route_next, style=P.HUD_CYAN)
            if s.route_next_star:
                mark     = "⛽" if s.route_next_scoopable else "✗"
                star_col = P.HUD_GREEN if s.route_next_scoopable else P.HUD_CRIT
                t.append(f"  {s.route_next_star} {mark}", style=f"bold {star_col}")
            t.append("\n")
    else:
        t.append("No route set.\n", style=P.AMBER_DIM)
    parts.append(t)

    # Galaxy position
    if s.star_pos:
        x, y, z = s.star_pos
        dist_sol  = math.sqrt(x**2 + y**2 + z**2)
        core_x, core_y, core_z = 25.21875, -20.90625, 25899.96875
        dist_core = math.sqrt((x - core_x)**2 + (y - core_y)**2 + (z - core_z)**2)
        gal = Text()
        gal.append("\nGALAXY POSITION\n", style="bold rgb(195,160,55)")
        gal.append(f"  Sol   ", style=P.LABEL)
        gal.append(f"{dist_sol:,.0f} ly\n".replace(",", _NNBSP), style="white")
        gal.append(f"  Core  ", style=P.LABEL)
        gal.append(f"{dist_core:,.0f} ly\n".replace(",", _NNBSP), style="white")
        gal.append(f"  Pos   ", style=P.LABEL)
        gal.append(f"{x:.0f} / {y:.0f} / {z:.0f}\n", style="rgb(150,150,150)")
        parts.append(gal)

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
        star_planets: dict[str, list[BodyInfo]] = {k: [] for k in star_index}
        primary_key  = sorted_star_keys[0] if sorted_star_keys else ""
        for p in _s_planets:
            p_short = _short_name(p.name, _sys).strip()
            parts   = p_short.split()
            assigned = False
            for length in range(len(parts) - 1, 0, -1):
                candidate = " ".join(parts[:length])
                if candidate in star_index:
                    star_planets[candidate].append(p)
                    assigned = True
                    break
            if not assigned:
                star_planets.setdefault(primary_key, []).append(p)

        # Which planet does each moon belong to?  Remove last token.
        planet_moons: dict[str, list[BodyInfo]] = {}
        for m in _s_moons:
            m_short = _short_name(m.name, _sys).strip()
            parts   = m_short.split()
            pk      = " ".join(parts[:-1]) if len(parts) > 1 else primary_key
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

        W = len(ruler_chars)
        if W:
            # ── Row 1: ruler ────────────────────────────────────────────────
            row1 = Text("  ")
            for ch, style in ruler_chars:
                row1.append(ch, style=style)
            row1.append("\n")

            # ── Row 2: last label of each body ───────────────────────────────
            def _last_label(b: BodyInfo) -> str:
                short = _short_name(b.name, _sys).strip()
                return short.split()[-1] if short else "A"

            name_arr = [" "] * W
            for pos, b in body_pos:
                lbl = _last_label(b)
                for i, ch in enumerate(lbl):
                    if pos + i < W and name_arr[pos + i] == " ":
                        name_arr[pos + i] = ch
            row2 = Text("  ")
            row2.append("".join(name_arr) + "\n", style="rgb(160,160,160)")

            # ── Row 3: notable (+) ───────────────────────────────────────────
            notable_arr = [" "] * W
            for pos, b in body_pos:
                if (b.planet_class in ("Earthlike body", "Water world", "Ammonia world")
                        or b.terraform or b.value > 1_000_000):
                    notable_arr[pos] = "+"
            has_notable = any(c != " " for c in notable_arr)

            # ── Row 4: bio signal counts ─────────────────────────────────────
            bio_arr = [" "] * W
            for pos, b in body_pos:
                if b.bio_signals > 0:
                    bio_arr[pos] = str(b.bio_signals)
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

        parts.append(diag)

    # Notable bodies in current system
    notable = [
        b for b in s.bodies
        if b.planet_class in (
            "Earthlike body", "Water world", "Ammonia world",
        ) or b.terraform or b.bio_signals > 0 or b.value > 500_000
    ]
    if notable:
        notable.sort(key=lambda b: _natural_key(_short_name(b.name, s.system)))
        hdr = Text()
        hdr.append("\nNOTABLE BODIES\n", style="bold rgb(195,160,55)")
        parts.append(hdr)

        tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        tbl.add_column("name",  style="white", width=10)
        tbl.add_column("type",  width=11)
        tbl.add_column("val",   width=11, justify="right")
        tbl.add_column("flags", width=8)

        for b in notable:
            short  = _short_name(b.name, s.system)
            btype  = _abbrev_type(b.planet_class, b.star_type)
            col    = _body_color(b.planet_class, b.star_type)
            v      = b.value if b.value > 0 else _estimated_value(b)
            val_s  = _fmt_value(v) if v > 0 else "—"
            vcol   = P.GOLD if b.value > 1_000_000 else (P.AMBER if v > 0 else P.DIM)
            flags  = ""
            if b.bio_signals > 0:  flags += f"Bio:{b.bio_signals} "
            if b.terraform:        flags += "T "
            if b.first_discovered: flags += "★"
            tbl.add_row(
                Text(short, style="white"),
                Text(btype, style=f"bold {col}"),
                Text(val_s, style=vcol),
                Text(flags.strip(), style=P.HUD_GREEN),
            )
        parts.append(tbl)

    # Session stats removed (moved to footer)
    if not parts:
        return Text("No data.", style=P.LABEL)
    return Group(*parts)


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

    _MODES  = ("auto", "overview", "inventory", "bio", "missions", "engineers")
    _mode:   str = "auto"
    _active: str = "overview"

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

    def _resolve(self, s: AppState) -> str:
        if self._mode != "auto":
            return self._mode
        # Incomplete bio scans only exist when player is actively scanning on a surface
        if any(not sc.complete for sc in s.bio_scans):
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
        return _render_overview(s)


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

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        t       = Text()
        events  = [ev for ev in s.events if ev.category != EventCategory.Chat]
        visible = events[self._scroll:]

        prefix_w  = 11  # "HH:MM:SS " (9) + "◈ " (2)
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w

        for ev in visible:
            col       = ev.category.rich_color()
            warn      = ev.category == EventCategory.Warn
            msg_style = f"bold {P.HUD_CRIT}" if warn else "white"
            lines     = textwrap.wrap(ev.message, width=msg_w) or [""]
            for i, line in enumerate(lines):
                if i == 0:
                    t.append(f"{ev.time} ", style="rgb(120,120,120)")
                    t.append(f"{ev.category.icon()} ", style=col)
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

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("No chat.", style=P.LABEL)
        chats = [ev for ev in s.events if ev.category == EventCategory.Chat]
        if not chats:
            t = Text()
            t.append("No chat messages.", style=P.LABEL)
            return t
        prefix_w  = 9  # "HH:MM:SS " (9)
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w
        t = Text()
        for ev in chats:
            lines = textwrap.wrap(ev.message, width=msg_w) or [""]
            for i, line in enumerate(lines):
                if i == 0:
                    t.append(f"{ev.time} ", style="rgb(120,120,120)")
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
