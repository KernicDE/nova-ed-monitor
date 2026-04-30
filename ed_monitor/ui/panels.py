from __future__ import annotations

import re
import textwrap
import time
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version
from typing import NamedTuple, Optional

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

from ..state import (
    AppState, BioScan, BodyInfo, EngineerInfo, EventCategory,
    estimate_value_base as _estimated_value,
    estimate_value_mapped as _body_value,
    _SPECIFIC_BONUS, _BASIC_BONUS_TERRAFORMABLE, _EFFICIENCY_MULTIPLIER, _ODYSSEY_MAPPING_BONUS,
)
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
    t.append("○" * empty, style=P.DIM)
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
        }.get(star) or ("White Dwarf" if star.startswith("D") else (star if len(star) > 2 else f"{star} Star"))
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



def _body_value_color(b: BodyInfo) -> str:
    """Rich color style for the body value column, based on FSS status and bonus tier.

    FSS'd bodies use tier-based coloring:
      GOLD  — first discovered + first mapped (maximum bonus)
      AMBER — first mapped only
      white — basic DSS payout (already discovered/mapped by others)

    Non-FSS'd bodies:
      AMBER — EDSM/estimated value available
      DIM   — no value available
    """
    if not b.fss_scanned:
        return P.AMBER if b.value > 0 else P.DIM
    # FSS'd — color by bonus tier
    if b.first_discovered and b.first_mapped:
        return P.GOLD
    if b.first_mapped:
        return P.AMBER
    return "white"


def _data_table(h2: str = P.HEADER) -> Table:
    """Create a consistently styled Rich Table for panel data.

    Uses ``box=None``, alternating row backgrounds, and mode-tinted headers.
    Pass ``h2=mp["h2"]`` to tint column headers to the current mode.
    Callers add columns with ``tbl.add_column(...)``.
    """
    return Table(
        show_header=True, show_edge=False, show_lines=False,
        padding=(0, 1), box=None,
        row_styles=["", f"on {P.ROW_ALT}"],
        header_style=f"bold {h2}",
    )


def _kv_row(label: str, value: str, value_style: str = P.WHITE, width: int = 0,
            h3: str = P.LABEL) -> Text:
    """Return a label:value Text row with consistent label styling.

    *width* sets a fixed left-padding for the label (e.g. 8 for single-column
    layouts).  When 0 the label is followed by a single space.
    Pass ``h3=mp["h3"]`` to tint the label to the current mode.
    """
    t = Text()
    if width:
        t.append(f"{label:<{width}}", style=h3)
    else:
        t.append(f"{label} ", style=h3)
    t.append(value, style=value_style)
    return t


def _kv_line(t: Text, label: str, value: str, value_style: str = P.WHITE, width: int = 8,
             h3: str = P.LABEL) -> None:
    """Append a label:value line (with trailing newline) to an existing Text."""
    t.append_text(_kv_row(label, value, value_style, width, h3))
    t.append("\n")


def _two_column_table(left_cells: list[Text], right_cells: list[Text]) -> Table:
    """Build a 1:1 two-column table from lists of Text cells."""
    tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    tbl.add_column("left", ratio=1)
    tbl.add_column("right", ratio=1)
    rows = max(len(left_cells), len(right_cells))
    for i in range(rows):
        lc = left_cells[i] if i < len(left_cells) else Text("")
        rc = right_cells[i] if i < len(right_cells) else Text("")
        tbl.add_row(lc, rc)
    return tbl


def _section_header(title: str, h1: str = P.HEADER, bg: str = P.HEADER_BG) -> Text:
    """Return a mode-tinted section header bar.

    Pass ``h1=mp["h1"], bg=mp["bg"]`` to tint to the current mode.
    """
    t = Text()
    t.append(f" {title} ", style=f"bold {h1} on {bg}")
    t.append("\n")
    return t


# ── Base class ────────────────────────────────────────────────────────────────

class _Panel(Widget):
    _snap: Optional[AppState] = None
    _last_key: tuple = ()

    def _key_changed(self, new_key: tuple) -> bool:
        """Return True (and store new_key) if new_key differs from the last seen key."""
        if new_key != self._last_key:
            self._last_key = new_key
            return True
        return False

    def update(self, snap: AppState) -> None:
        self._snap = snap
        self.refresh()

    def jump_top(self) -> None:
        """Jump to the top of the panel content. No-op by default."""
        pass

    def jump_bottom(self) -> None:
        """Jump to the bottom of the panel content. No-op by default."""
        pass


# ── System panel ──────────────────────────────────────────────────────────────

class SystemPanel(_Panel):
    BORDER_TITLE = "◈ Position"

    DEFAULT_CSS = """
    SystemPanel {
        border: solid rgb(0,175,185);         /* P.HUD_CYAN */
        border-title-color: rgb(0,175,185);   /* P.HUD_CYAN */
        border-title-style: bold;
        height: auto;
        min-height: 11;
        width: 1fr;
    }
    """

    def update(self, snap: AppState) -> None:
        self._snap = snap
        key = (
            snap.system, snap.population, snap.economy, snap.security, snap.government,
            snap.allegiance, snap.bodies_version, snap.fss_body_count,
            snap.route_hops, snap.route_destination,
            snap.nearest_populated_name, snap.nearest_populated_dist,
            snap.system_power, snap.system_power_state,
            snap.pp_power, snap.pp_total_merits, snap.pp_rank,
            snap.client_online, snap.in_hyperspace,
            snap.nearest_body,
            round(snap.lat, 2)      if snap.lat      is not None else None,
            round(snap.lon, 2)      if snap.lon      is not None else None,
            round(snap.altitude, 0) if snap.altitude is not None else None,
        )
        if self._key_changed(key):
            self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        _mp = P.mp(s.ui_mode)
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
        left_cells: list[Text]  = []
        right_cells: list[Text] = []

        # Left column — exploration / natural data
        if stars or planets:
            body_parts = [f"{stars}★"]
            if planets: body_parts.append(f"{planets}P")
            if moons:   body_parts.append(f"{moons}M")
            left_cells.append(_kv_row("Bodies", " ".join(body_parts), h3=_mp["h3"]))

        if fss_total > 0:
            fss_col = P.HUD_GREEN if fss_done >= fss_total else P.AMBER
            left_cells.append(_kv_row("FSS", f"{fss_done}/{fss_total}", fss_col, h3=_mp["h3"]))

        if s.system_power:
            pp     = s.system_power
            pp_col = _power_state_color(s.system_power_state)
            if s.system_power_state:
                pp += f" [{s.system_power_state}]"
            left_cells.append(_kv_row("Power", pp, pp_col, h3=_mp["h3"]))


        # Right column — human/BGS data
        if s.population > 0:
            right_cells.append(_kv_row("Pop", _fmt_pop(s.population), h3=_mp["h3"]))
        if s.economy:
            right_cells.append(_kv_row("Economy", s.economy, h3=_mp["h3"]))
        if s.security:
            sec_col = (P.HUD_GREEN if "High" in s.security
                       else P.HUD_WARN if "Medium" in s.security
                       else P.HUD_CRIT)
            right_cells.append(_kv_row("Security", s.security, f"bold {sec_col}", h3=_mp["h3"]))
        if s.government:
            right_cells.append(_kv_row("Gov", s.government, h3=_mp["h3"]))
        if s.allegiance:
            right_cells.append(_kv_row("Alleg", s.allegiance, h3=_mp["h3"]))
        if s.controlling_faction:
            faction_str = (
                f"{s.controlling_faction} [{s.controlling_state}]"
                if s.controlling_state and s.controlling_state != "None"
                else s.controlling_faction
            )
            right_cells.append(_kv_row("Faction", faction_str, h3=_mp["h3"]))
        if s.station_count > 0:
            right_cells.append(_kv_row("Stations", str(s.station_count), h3=_mp["h3"]))

        # Build two-column table
        if left_cells or right_cells:
            parts.append(_two_column_table(left_cells, right_cells))

        # ── Body section — shown when near a known body ───────────────────────
        body_info: "BodyInfo | None" = None
        if s.nearest_body:
            body_info = next((b for b in s.bodies if b.name == s.nearest_body), None)

        if body_info is not None:
            # Section separator + body name header
            sep = Text()
            sep.append("\n")
            sep.append(_short_name(s.nearest_body, s.system), style="bold white")
            parts.append(sep)

            bleft:  list[Text] = []
            bright: list[Text] = []

            # Type
            btype = _abbrev_type(body_info.planet_class, body_info.star_type)
            if btype:
                tcol = _body_color(body_info.planet_class, body_info.star_type)
                bleft.append(_kv_row("Type", btype, tcol, h3=_mp["h3"]))

            # Gravity (planets only)
            if body_info.surface_gravity > 0 and body_info.planet_class:
                g     = body_info.surface_gravity / 9.80665
                gcol  = (P.HUD_CRIT if g >= 3.0
                         else P.HUD_WARN if g >= 1.5
                         else P.WHITE)
                bleft.append(_kv_row("Gravity", f"{g:.2f} G", gcol, h3=_mp["h3"]))

            # Radius
            if body_info.radius > 0:
                km = body_info.radius / 1000
                bleft.append(_kv_row("Radius", f"{km:,.0f} km", h3=_mp["h3"]))

            # Surface temperature
            if body_info.surface_temp > 0:
                bleft.append(_kv_row("Temp", f"{body_info.surface_temp:.0f} K", h3=_mp["h3"]))

            # Atmosphere (skip "No atmosphere")
            atm = body_info.atmosphere or ""
            if atm and "no atmosphere" not in atm.lower():
                atm_short = re.sub(r"\s+atmosphere$", "", atm, flags=re.IGNORECASE)
                bright.append(_kv_row("Atm", atm_short, h3=_mp["h3"]))

            # Bio and Geo signals
            if body_info.bio_signals > 0:
                bright.append(_kv_row("Bio", str(body_info.bio_signals), P.HUD_GREEN, h3=_mp["h3"]))
            if body_info.geo_signals > 0:
                bright.append(_kv_row("Geo", str(body_info.geo_signals), P.AMBER, h3=_mp["h3"]))

            # Volcanism (strip trailing " volcanism", title-case)
            if body_info.volcanism:
                vol = re.sub(r"\s+volcanism$", "", body_info.volcanism,
                             flags=re.IGNORECASE).title()
                bright.append(_kv_row("Volc", vol, h3=_mp["h3"]))

            # Terraformable
            if body_info.terraform:
                bright.append(_kv_row("TF", "Candidate", P.HUD_GREEN, h3=_mp["h3"]))

            if bleft or bright:
                parts.append(_two_column_table(bleft, bright))

        # Position footer — Pos/Alt (and "At" when no body section is shown)
        pos_parts: list[Text] = []
        if s.nearest_body and body_info is None:
            # Only show "At" when we have no detailed body section above
            pos_parts.append(_kv_row("At", _short_name(s.nearest_body, s.system), h3=_mp["h3"]))
        if s.lat is not None and s.lon is not None:
            pos_parts.append(_kv_row("Pos", f"{s.lat:.2f}, {s.lon:.2f}", h3=_mp["h3"]))
            if s.altitude is not None:
                pos_parts.append(_kv_row("Alt", f"{s.altitude:,.0f} m", h3=_mp["h3"]))
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
        border: solid rgb(210,115,0);         /* P.AMBER */
        border-title-color: rgb(210,115,0);   /* P.AMBER */
        border-title-style: bold;
        height: auto;
        min-height: 11;
        width: 2fr;
    }
    """

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
        key = (
            snap.client_online, snap.in_main_ship, snap.in_srv,
            snap.ship_type, snap.ship_name, snap.ship_ident,
            snap.commander,
            snap.hull, snap.shields_up, snap.fuel, snap.fuel_max, snap.heat,
            snap.pips_sys, snap.pips_eng, snap.pips_wep,
            snap.docked, snap.landed, snap.supercruise, snap.orbital_cruise,
            snap.cargo, snap.cargo_capacity, snap.credits,
            snap.high_g_extreme, snap.overheating, snap.low_fuel,
            snap.hardpoints, snap.analysis_mode, snap.silent_running,
            snap.lights_on, snap.night_vision, snap.flight_assist_off,
            snap.mass_locked, snap.landing_gear,
            # on-foot / SRV fields
            snap.suit_health, snap.suit_oxygen, snap.selected_weapon,
            snap.on_foot_gravity, snap.low_oxygen, snap.low_health_suit,
            snap.srv_handbrake, snap.srv_drive_assist,
        )
        if self._key_changed(key):
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
            _mp_ship = P.mp(s.ui_mode)
            if s.analysis_mode:
                mode_label, mode_col = "Analysis", _mp_ship["h1"]
            else:
                mode_label, mode_col = "Combat", _mp_ship["h1"]

            btn_row: list[tuple[str, bool, str]] = []
            if s.docked:
                btn_row = [(mode_label, True, mode_col), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN)]
            elif s.landed:
                btn_row = [(mode_label, True, mode_col), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN), ("Silent", s.silent_running, P.HUD_CRIT)]
            elif s.supercruise:
                btn_row = [(mode_label, True, mode_col), ("Manual", s.flight_assist_off, P.HUD_CRIT), ("Lights", s.lights_on, P.AMBER), ("Silent", s.silent_running, P.HUD_CRIT)]
            else:
                btn_row = [(mode_label, True, mode_col), ("Gear", s.landing_gear, P.AMBER), ("Manual", s.flight_assist_off, P.HUD_CRIT), ("Scoop", s.cargo_scoop, P.AMBER), ("Lights", s.lights_on, P.AMBER), ("Night", s.night_vision, P.HUD_GREEN), ("Silent", s.silent_running, P.HUD_CRIT)]

            parts.append(_button_bar(btn_row))

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
        _mp_srv = P.mp(s.ui_mode)
        mode_label, mode_col = "SRV", _mp_srv["h1"]

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

        parts.append(_button_bar(btn_row))

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


def _button_bar(items: list[tuple[str, bool, str]]) -> Table:
    """Return a fixed-position button bar using an invisible table.

    Buttons are arranged in a 2×4 grid so they fit narrow panels.
    Active buttons are shown in their designated colour; inactive ones
    are grey.  Both use ``[Label]`` to look like cockpit switches.
    """
    tbl = Table(show_header=False, show_edge=False, box=None, padding=(0, 0), expand=True)
    for _ in range(4):
        tbl.add_column(ratio=1)

    cells: list[list[Text]] = [
        [Text("", justify="center") for _ in range(4)],
        [Text("", justify="center") for _ in range(4)],
    ]
    _pos: dict[str, tuple[int, int]] = {
        "Combat":   (0, 0), "Analysis": (0, 0), "SRV":      (0, 0),
        "Gear":     (0, 1), "Assist":   (0, 1),
        "Manual":   (0, 2),
        "Scoop":    (0, 3),
        "Lights":   (1, 0),
        "Night":    (1, 1),
        "Silent":   (1, 2), "Turret":   (1, 2),
    }
    for label, active, col in items:
        r, c = _pos.get(label, (0, 0))
        style = f"bold {col}" if active else P.LABEL_LIGHT
        cells[r][c] = Text(f"[{label}]", style=style, justify="center")

    for row in cells:
        tbl.add_row(*row)
    return tbl


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
        border: solid rgb(210,115,0);         /* P.AMBER */
        border-title-color: rgb(210,115,0);   /* P.AMBER */
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
        key = (
            snap.docked, snap.station, snap.station_type, snap.station_economy,
            snap.station_services, snap.station_dist_ls,
            snap.target_ship, snap.target_body, snap.approach_body, snap.nearest_body,
            snap.route_destination, snap.route_hops, snap.route_next, snap.route_next_star,
            snap.route_next_scoopable, snap.route_dist, snap.route_next_dist,
            snap.bodies_version,
            len(snap.route_next_stations),
            len(snap.carriers_current_system),
            snap.nearest_populated_name, snap.nearest_populated_dist,
            len(snap.nearest_populated_stations),
            snap.client_online,
        )
        if self._key_changed(key):
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
        _mp = P.mp(s.ui_mode)

        def row(label: str, value: str, vstyle: str = "white") -> None:
            _kv_line(t, label, value, vstyle, h3=_mp["h3"])

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
                    t.append("  " + "  ·  ".join(pair) + "\n", style=P.LABEL_LIGHT)

        return t

    def _render_ship_target(self, s: AppState) -> RenderableType:
        """Show info for currently targeted ship (ShipTargeted event)."""
        t = Text()
        _mp = P.mp(s.ui_mode)

        def row(label: str, value: str, vstyle: str = "white") -> None:
            _kv_line(t, label, value, vstyle, h3=_mp["h3"])

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
            t.append("  (target to advance)", style=f"dim {P.DIM}")
        t.append("\n")

        return t

    def _render_target(self, s: AppState) -> Optional[RenderableType]:
        """Show body details for currently targeted body.
        When the target is a system (next route hop), shows route info instead."""
        body_name = s.target_body
        body = next((b for b in s.bodies if b.name == body_name), None)
        _mp = P.mp(s.ui_mode)
        if body is None:
            # System target (e.g. next route hop) — not a scanned body in this system
            t = Text()

            def _row(label: str, value: str, vstyle: str = "white") -> None:
                _kv_line(t, label, value, vstyle, h3=_mp["h3"])

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
            _kv_line(t, label, value, vstyle, h3=_mp["h3"])

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
            bio_col = P.GOLD if complete_count >= body.bio_signals else f"bold {P.BIO_DSS}"
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
        _mp = P.mp(s.ui_mode)

        def row(label: str, value: str, vstyle: str = "white") -> None:
            _kv_line(t, label, value, vstyle, h3=_mp["h3"])

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
                bio_col = P.GOLD if complete_count >= body.bio_signals else f"bold {P.BIO_DSS}"
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
        border: solid rgb(0,175,185);         /* P.HUD_CYAN */
        border-title-color: rgb(0,175,185);   /* P.HUD_CYAN */
        border-title-style: bold;
    }
    """

    _scroll: int = 0
    # Sort cache: avoid re-sorting bodies every 500 ms when nothing has changed
    _sorted_cache:         list  = []
    _sorted_cache_version: int   = -1
    _sorted_cache_system:  str   = ""

    def update(self, snap: AppState) -> None:
        self._snap = snap
        key = (snap.bodies_version, snap.system)
        if self._key_changed(key):
            self.refresh()

    def scroll_bodies(self, delta: int) -> None:
        """Scroll the bodies list up (delta<0) or down (delta>0)."""
        self._scroll = max(0, self._scroll + delta)
        self.refresh()

    def jump_top(self) -> None:
        self._scroll = 0
        self.refresh()

    def jump_bottom(self) -> None:
        # Render clamps to valid range automatically
        self._scroll = 9999
        self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None or not s.bodies:
            t = Text()
            t.append("No bodies scanned yet.", style=P.LABEL)
            return t

        _mp = P.mp(s.ui_mode)
        tbl = _data_table(_mp["h2"])
        tbl.add_column("Body", style="white", width=11, no_wrap=True)
        tbl.add_column("Type", width=8)
        tbl.add_column("Est Val", width=11, justify="right")
        tbl.add_column("Dist", width=11, justify="right")
        tbl.add_column("B",    width=4)
        tbl.add_column("G",    width=2)
        tbl.add_column("LTA",  width=5)
        tbl.add_column("F",    width=2)
        tbl.add_column("D",    width=2)

        system = s.system
        _star_short_names: set[str] = set()

        # Re-sort only when bodies or system changed — cache the result across ticks
        if (s.bodies_version != self._sorted_cache_version or
                system != self._sorted_cache_system):
            visible = [b for b in s.bodies if b.planet_class or b.star_type]

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
            self._sorted_cache         = visible
            self._sorted_cache_version = s.bodies_version
            self._sorted_cache_system  = system

        visible = self._sorted_cache

        # Apply scroll offset (w/s keys)
        total_bodies = len(visible)
        effective_scroll = min(self._scroll, max(0, total_bodies - 1))

        above = effective_scroll
        panel_h = self.size.height or 0
        below = max(0, total_bodies - effective_scroll - max(1, panel_h - 2))

        self.border_title = "◈ Scanned Bodies"
        if above > 0 and below > 0:
            self.border_subtitle = f"▲{above}  ▼{below}"
        elif above > 0:
            self.border_subtitle = f"▲{above}"
        elif below > 0:
            self.border_subtitle = f"▼{below}"
        else:
            self.border_subtitle = ""
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
                name_style = f"bold {P.HIGH_G_CRIT}"
            elif g_val >= 1.5:
                name_style = f"bold {P.HIGH_G_WARN}"
            else:
                name_style = "white"
            name  = Text(indent + display_name, style=name_style)
            btype = _abbrev_type(b.planet_class, b.star_type)

            bv      = _body_value(b)
            val     = _fmt_value_short(bv)
            val_col = _body_value_color(b)

            dist     = _fmt_ls_compact(b.dist_ls)
            dist_col = P.DIM if b.dist_ls == 0.0 else "white"

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
                bio_col = f"bold {P.BIO_DSS}"
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

def _render_log_lines(
    events: list,
    prefix_w: int,
    msg_w: int,
    line_width: int,
    format_prefix,  # Callable[[ev], Iterable[(str, str)]] → (text, style) pairs before message
    format_message,  # Callable[[ev], (lines: list[str], style: str, first_line_prefix: list)]
) -> Text:
    """Shared renderer: timestamp + prefix + wrapped message for any log panel.

    format_prefix(ev)  → list of (text, style) to append after the timestamp.
    format_message(ev) → (lines: list[str], msg_style: str, first_extra: list[(str,str)])
                         first_extra is appended on the first line before the message text.
    """
    t = Text()
    entry_idx = 0
    for ev in events:
        time_str = ev.time[:5]
        prefix_parts = format_prefix(ev)
        lines_text, msg_style, first_extra = format_message(ev)
        base = f"on {P.ROW_ALT}" if entry_idx % 2 == 1 else ""
        for i, line in enumerate(lines_text):
            seg = Text(style=base)
            if i == 0:
                seg.append(f"{time_str} ", style=P.LABEL_DIM)
                for txt, sty in prefix_parts:
                    seg.append(txt, style=sty)
                for txt, sty in first_extra:
                    seg.append(txt, style=sty)
                seg.append(line, style=msg_style)
            else:
                seg.append(" " * prefix_w + line, style=msg_style)
            # Pad to full line width so background fills the whole row
            visual_len = len(seg.plain)
            if visual_len < line_width:
                seg.append(" " * (line_width - visual_len), style="")
            seg.append("\n")
            if base:
                seg.stylize(base)
            t.append_text(seg)
        entry_idx += 1
    return t


# ── Event log panel ───────────────────────────────────────────────────────────

class EventLogPanel(_Panel):
    BORDER_TITLE = "◈ Event Log"

    DEFAULT_CSS = """
    EventLogPanel {
        border: solid rgb(90,90,90);         /* P.PANEL_BORDER */
        border-title-color: rgb(90,90,90);   /* P.PANEL_BORDER */
        border-title-style: bold;
    }
    """

    _scroll: int = 0

    def update(self, snap: AppState) -> None:
        self._snap = snap
        key = (snap.events_version,)
        if self._key_changed(key):
            self.refresh()

    def set_scroll(self, scroll: int) -> None:
        self._scroll = scroll
        self.refresh()

    def scroll_log(self, delta: int) -> None:
        s = self._snap
        events = [ev for ev in s.events if ev.category != EventCategory.Chat] if s else []
        max_s = max(0, len(events) - 1)
        self._scroll = max(0, min(self._scroll + delta, max_s))
        self.refresh()

    def jump_top(self) -> None:
        self.scroll_log(-9999)

    def jump_bottom(self) -> None:
        self.scroll_log(9999)

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
        self.border_title = "◈ Event Log"
        if above > 0 and below > 0:
            self.border_subtitle = f"▲{above}  ▼{below}"
        elif above > 0:
            self.border_subtitle = f"▲{above}"
        elif below > 0:
            self.border_subtitle = f"▼{below}"
        else:
            self.border_subtitle = ""

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

        return _render_log_lines(visible, prefix_w, msg_w, content_w, _prefix, _message)


# ── Chat log panel ────────────────────────────────────────────────────────────

class ChatLogPanel(_Panel):
    BORDER_TITLE = "◈ Chat"

    DEFAULT_CSS = """
    ChatLogPanel {
        border: solid rgb(90,90,90);         /* P.PANEL_BORDER */
        border-title-color: rgb(90,90,90);   /* P.PANEL_BORDER */
        border-title-style: bold;
    }
    """

    _scroll: int = 0

    def update(self, snap: AppState) -> None:
        self._snap = snap
        # Chat events share the events deque — use events_version as the change signal
        key = (snap.events_version,)
        if self._key_changed(key):
            self.refresh()

    def scroll_chat(self, delta: int) -> None:
        s = self._snap
        chats = [ev for ev in s.events if ev.category == EventCategory.Chat] if s else []
        max_s = max(0, len(chats) - 1)
        self._scroll = max(0, min(self._scroll + delta, max_s))
        self.refresh()

    def jump_top(self) -> None:
        self.scroll_chat(-9999)

    def jump_bottom(self) -> None:
        self.scroll_chat(9999)

    # Source tag → (3-char abbrev, color)
    _SRC_TAGS: dict[str, tuple[str, str]] = {
        "[Twitch]":  ("TWI", "rgb(145,70,255)"),   # Twitch purple
        "[YouTube]": ("YTL", "rgb(255,70,70)"),    # YouTube red
        "[Wing]":    ("WNG", P.HUD_CYAN),    # Cyan
        "[Local]":   ("LCL", P.LABEL_LIGHT),  # Grey
        "[Sqn]":     ("SQN", "rgb(0,200,100)"),    # Green
        "[System]":  ("SYS", P.HUD_WARN),    # Amber
        "[Friend]":  ("FRD", P.BLUE_SH),   # Blue
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
        self.border_title = "◈ Chat"
        if above > 0 and below > 0:
            self.border_subtitle = f"▲{above}  ▼{below}"
        elif above > 0:
            self.border_subtitle = f"▲{above}"
        elif below > 0:
            self.border_subtitle = f"▼{below}"
        else:
            self.border_subtitle = ""

        chats = chats[effective_scroll:]
        prefix_w  = 11  # "HH:MM " (6) + "TWI " (4) + padding 1
        content_w = max(prefix_w + 10, self.size.width - 2)
        msg_w     = content_w - prefix_w

        def _strip_tag(ev):
            msg = ev.message
            src_abbr, src_col = "MSG", P.LABEL_LIGHT
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

        return _render_log_lines(chats, prefix_w, msg_w, content_w, _prefix, _message)



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
            left.append(f" {stall_msg} ", style=f"bold {P.HIGH_G_CRIT}")
        else:
            left.append(" q",      style=key); left.append(" Quit ", style=lbl)
            left.append(" Tab",    style=key); left.append(" Mode ", style=lbl)
            left.append(" ?",      style=key); left.append(" Help ", style=lbl)
            left.append(" ↑↓",     style=key); left.append(" Scroll ", style=lbl)
            left.append(" m",      style=key)

        muted              = s.muted              if s is not None else False
        chat_tts_muted     = s.chat_tts_muted     if s is not None else False
        twitch_tts_muted   = s.twitch_tts_muted   if s is not None else False
        youtube_tts_muted  = s.youtube_tts_muted  if s is not None else False

        if stall_msg:
            pass  # stall takes over left side; still show volume on the right
        elif muted:
            left.append(" MUTED ", style=f"bold {P.HIGH_G_CRIT}")
        else:
            left.append(" +/-",    style=key); left.append(f" Vol {vol}%", style="bold white")

        # Chat TTS mute indicators (shown after volume, always visible when active)
        _mute_style = f"bold {P.HIGH_G_CRIT}"
        _ok_style   = P.DIM
        if not stall_msg:
            left.append("  ")
            left.append("CHAT", style=_mute_style if chat_tts_muted else _ok_style)
            left.append(" ")
            left.append("TW",   style=_mute_style if (twitch_tts_muted or chat_tts_muted) else _ok_style)
            left.append(" ")
            left.append("YT",   style=_mute_style if (youtube_tts_muted or chat_tts_muted) else _ok_style)

        center = Text(justify="center")
        center.append(datetime.now().strftime("%H:%M:%S"), style=f"bold {P.LABEL_LIGHT}")

        right = Text(justify="right")
        if s is not None:
            if s.session_start:
                right.append(f"Online: {s.session_start}  ", style=P.LABEL_DIM)
            _append_edsm(right, s.edsm_status)
        right.append(f"  v{_NOVA_VERSION}", style=P.DIM)

        tbl = Table.grid(expand=True)
        tbl.add_column("left",   no_wrap=True, ratio=1)
        tbl.add_column("center", justify="center", no_wrap=True, ratio=1)
        tbl.add_column("right",  justify="right",  no_wrap=True, ratio=1)
        tbl.add_row(left, center, right)
        return tbl


def _append_edsm(t: Text, st) -> None:
    t.append("EDSM ", style=f"bold {P.LABEL_DIM}")
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
        t.append(f"  {st.last_rx}", style=P.PANEL_BORDER)
    if st.last_error:
        t.append(f"  {st.last_error}", style=P.HUD_WARN)
    t.append(" ")

# SituationalPanel and all sub-mode renderers live in the
# ed_monitor.ui.situational package.  Re-exported here for backward compat.
from .situational.panel import SituationalPanel

# Re-exports for backward compatibility (tests, external callers)
from .situational.engineers import _build_eng_list, _ENGINEER_STATIC, _ODY_ENGINEERS
