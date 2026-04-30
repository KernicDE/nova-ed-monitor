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


_ODY_ENGINEERS: frozenset = frozenset({
    "Jude Navarro", "Baltanos", "Eleanor Bresa", "Hero Ferrari", "Rosa Dayette",
    "Yi Shen", "Domino Green", "Uma Laszlo", "Oden Geiger", "Terra Velasquez",
    "Kit Fowler", "Wellington Beck", "Yarden Bond",
})



class _EngData(NamedTuple):
    specialty: str
    station:   str
    system:    str
    unlock:    str
    modules:   tuple
    hint:      str = ""  # leveling shortcut shown in detail view



_ENGINEER_STATIC: dict[str, _EngData] = {
    # ── Horizons (ship modules) ────────────────────────────────────────────────
    "Felicity Farseer":   _EngData("FSD / Thrusters",   "Farseer Inc",              "Deciat",
                                   "Explorer rank Scout + 1 Meta-Alloy",
                                   ("Frame Shift Drive (G5)", "Thrusters (G3)", "Sensors (G3)",
                                    "Detailed Surface Scanner (G3)", "Shield Booster (G1)"),
                                   "Spam G1 FSD Increased Range — Iron only"),
    "Elvira Martuuk":     _EngData("FSD",               "Long Sight Base",          "Khun",
                                   "Travel 300+ ly from start + 3 Soontill Relics",
                                   ("Frame Shift Drive (G5)", "Shield Generator (G3)",
                                    "Thrusters (G2)", "Shield Cell Bank (G1)"),
                                   "Spam G3 FSD Increased Range — Iron, Nickel, Carbon"),
    "Professor Palin":    _EngData("Thrusters",         "Abel Laboratory",          "Arque",
                                   "Marco Qwent invite + 5,000 ly from start + 25 Sensor Fragments",
                                   ("Thrusters (G5)", "Frame Shift Drive (G3)"),
                                   "Spam G1 Dirty Drives — Sulphur only"),
    "Chloe Sedesi":       _EngData("Thrusters / FSD",   "Cinder Dock",              "Shenve",
                                   "Marco Qwent invite + 5,000 ly from start + 25 Sensor Fragments",
                                   ("Thrusters (G5)", "Frame Shift Drive (G3)"),
                                   "Spam G1 Dirty Drives — Sulphur only"),
    "The Dweller":        _EngData("Power Distributor", "Black Hide",               "Wyrd",
                                   "5 black market trades + 500,000 Cr bribe",
                                   ("Power Distributor (G5)", "Pulse Laser (G4)",
                                    "Burst Laser (G3)", "Beam Laser (G3)"),
                                   "Spam G1 Efficient Weapon on Pulse Laser — Sulphur only"),
    "Liz Ryder":          _EngData("Explosives",        "Demolition Unlimited",     "Eurybia",
                                   "Cordial w/ Eurybia Blue Mafia + 200 Landmines",
                                   ("Seeker Missile Rack (G5)", "Torpedo Pylon (G5)",
                                    "Missile Rack (G5)", "Mine Launcher (G3)",
                                    "Hull Reinforcement Package (G1)", "Armour (G1)"),
                                   "Spam G1 Blast Resistant Hull — Nickel only"),
    "Tod 'The Blaster' McQuinn": _EngData("Weapons",   "Trophy Camp",              "Wolf 397",
                                   "15+ bounty vouchers + 100,000 Cr in bounties",
                                   ("Multi-cannon (G5)", "Rail Gun (G5)",
                                    "Fragment Cannon (G3)", "Cannon (G2)"),
                                   "Farm bounties at Haz RES sites — 100k Cr triggers invite"),
    "Marco Qwent":        _EngData("Power Plant",       "Qwent Research Base",      "Sirius",
                                   "Elvira Martuuk invite + Sirius permit + 25 Modular Terminals",
                                   ("Power Plant (G4)", "Power Distributor (G3)"),
                                   "Spam G1 Overcharged Power Plant — Sulphur only"),
    "Selene Jean":        _EngData("Armour",            "Prospector's Rest",        "Kuk",
                                   "Tod McQuinn invite + mine 500 t + 10 Painite",
                                   ("Hull Reinforcement Package (G5)", "Armour (G5)"),
                                   "Spam G1 Heavy Duty Hull Reinforcement — Iron only"),
    "Zacariah Nemo":      _EngData("Fragment Cannon",   "Nemo Cyber Party Base",    "Yoru",
                                   "Elvira Martuuk invite + Party of Yoru invite + 25 Xihe Companions",
                                   ("Fragment Cannon (G5)", "Multi-cannon (G3)", "Plasma Accelerator (G2)"),
                                   "Spam G1 Overcharged Fragment Cannon — Sulphur only"),
    "Lei Cheung":         _EngData("Shields",           "Trader's Rest",            "Laksak",
                                   "The Dweller invite + trade at 50 markets + 200 Gold",
                                   ("Shield Generator (G5)", "Sensors (G5)",
                                    "Detailed Surface Scanner (G5)", "Shield Booster (G3)"),
                                   "Spam G1 Enhanced Low Power Shields — Germanium only"),
    "Didi Vatermann":     _EngData("Shield Booster",    "Vatermann LLC",            "Leesti",
                                   "Selene Jean invite + Trade rank Merchant + 50 Lavian Brandy",
                                   ("Shield Booster (G5)", "Shield Generator (G3)"),
                                   "Spam G1 Resistance Augmented Shield Booster — Phosphorus only"),
    "Hera Tani":          _EngData("Power Plant",       "The Jet's Hole",           "Kuwemaki",
                                   "Liz Ryder invite + Empire rank Outsider + 50 Kamitra Cigars",
                                   ("Power Plant (G5)", "Detailed Surface Scanner (G5)",
                                    "Sensors (G3)", "Power Distributor (G3)"),
                                   "Spam G1 Overcharged Power Plant — Sulphur only"),
    "Juri Ishmaak":       _EngData("Sensors / Missiles","Pater's Memorial",         "Giryak",
                                   "Felicity Farseer invite + 50+ fed bonds + 100k-1M Cr fed bonds",
                                   ("Mine Launcher (G5)", "Sensors (G5)", "Detailed Surface Scanner (G5)",
                                    "Torpedo Pylon (G3)", "Seeker Missile Rack (G3)",
                                    "Wake Scanner (G3)", "Kill Warrant Scanner (G3)",
                                    "Manifest Scanner (G3)", "Missile Rack (G3)"),
                                   "Farm Federation combat bonds at Conflict Zones"),
    "Colonel Bris Dekker":_EngData("FSD Interdictor",  "Dekker's Yard",            "Sol",
                                   "Juri Ishmaak invite + Friendly with Federation + 1-10M Cr fed bonds",
                                   ("FSD Interdictor (G4)", "Frame Shift Drive (G3)"),
                                   "Farm Federation combat bonds at Conflict Zones"),
    "Broo Tarquin":       _EngData("Energy Weapons",    "Broo's Legacy",            "Muang",
                                   "Hera Tani invite + Combat rank Competent + 50 Fujin Tea",
                                   ("Burst Laser (G5)", "Pulse Laser (G5)", "Beam Laser (G5)"),
                                   "Spam G1 Efficient Weapon on Pulse Laser — Sulphur only"),
    "Tiana Fortune":      _EngData("Scanners / Limpets","Fortune's Loss",           "Achenar",
                                   "Hera Tani invite + Friendly with Empire + 50 Decoded Emission Data",
                                   ("Wake Scanner (G5)", "Kill Warrant Scanner (G5)",
                                    "Manifest Scanner (G5)", "Collector Limpet (G5)",
                                    "Fuel Transfer Limpet (G5)", "Hatch Breaker Limpet (G5)",
                                    "Prospector Limpet (G5)", "Sensors (G5)",
                                    "FSD Interdictor (G3)", "Detailed Surface Scanner (G3)"),
                                   "Farm Empire combat bonds or bounties at Achenar CZs"),
    "The Sarge":          _EngData("Weapons / Limpets", "The Beach",               "Beta-3 Tucani",
                                   "Juri Ishmaak invite + Fed Navy rank Midshipman + 50 Aberrant Shield Pattern Analysis",
                                   ("Collector Limpet (G5)", "Fuel Transfer Limpet (G5)",
                                    "Hatch Breaker Limpet (G5)", "Prospector Limpet (G5)",
                                    "Cannon (G5)", "Rail Gun (G3)"),
                                   "Farm Federation combat bonds at Conflict Zones"),
    "Ram Tah":            _EngData("Electronic Countermeasures", "Phoenix Base",    "Meene",
                                   "Lei Cheung invite + Explorer rank Surveyor + 50 Classified Scan Databanks",
                                   ("Electronic Countermeasure (G5)", "Point Defence (G5)",
                                    "Heat Sink Launcher (G5)", "Chaff Launcher (G5)",
                                    "Collector Limpet (G4)", "Fuel Transfer Limpet (G4)",
                                    "Prospector Limpet (G4)", "Hatch Breaker Limpet (G3)"),
                                   "Spam G1 Lightweight Sensors — Iron only"),
    "Bill Turner":        _EngData("Plasma Charger",    "Turner Metallics Inc",     "Alioth",
                                   "Selene Jean invite + Alioth permit + Friendly w/ Alioth Independents + 50 Bromellite",
                                   ("Plasma Accelerator (G5)", "Sensors (G5)",
                                    "Detailed Surface Scanner (G5)", "Life Support (G3)",
                                    "Refinery (G3)", "AFMU (G3)", "Fuel Scoop (G3)",
                                    "Wake Scanner (G3)", "Kill Warrant Scanner (G3)", "Manifest Scanner (G3)"),
                                   "Spam G1 Efficient Weapon on Plasma Accelerator — Sulphur only"),
    "Lori Jameson":       _EngData("Sensors / Utilities","Jameson Base",            "Shinrarta Dezhra",
                                   "Marco Qwent invite + Combat rank Dangerous + 25 Kongga Ale",
                                   ("Sensors (G5)", "Detailed Surface Scanner (G5)",
                                    "Refinery (G4)", "Fuel Scoop (G4)", "AFMU (G4)", "Life Support (G4)",
                                    "Wake Scanner (G3)", "Kill Warrant Scanner (G3)",
                                    "Manifest Scanner (G3)", "Shield Cell Bank (G3)"),
                                   "Spam G1 Lightweight Sensors — Iron only"),
    "Marsha Hicks":       _EngData("Limpets / Weapons", "The Watchtower",           "Tir",
                                   "The Dweller invite + Explorer rank Surveyor + 10 Osmium",
                                   ("Collector Limpet (G5)", "Fuel Transfer Limpet (G5)",
                                    "Hatch Breaker Limpet (G5)", "Prospector Limpet (G5)",
                                    "Refinery (G5)", "Fuel Scoop (G5)",
                                    "Cannon (G5)", "Multi-cannon (G5)", "Fragment Cannon (G5)"),
                                   "Spam G1 Lightweight Collector Limpet — Iron only"),
    "Mel Brandon":        _EngData("Various",           "The Brig",                 "Luchtaine",
                                   "Elvira Martuuk invite + Colonia Council invite + 100k Cr bounties",
                                   ("Frame Shift Drive (G5)", "Thrusters (G5)", "Shield Generator (G5)",
                                    "Burst Laser (G5)", "Pulse Laser (G5)", "Beam Laser (G5)",
                                    "FSD Interdictor (G5)", "Shield Booster (G5)", "Shield Cell Bank (G4)"),
                                   "Spam G1 FSD Increased Range — Iron only (Colonia)"),
    "Etienne Dorn":       _EngData("Various",           "Kraken's Retreat",         "Los",
                                   "Liz Ryder invite + Trade rank Dealer + 25 Occupied Escape Pods",
                                   ("Plasma Accelerator (G5)", "Sensors (G5)", "Detailed Surface Scanner (G5)",
                                    "Life Support (G5)", "Power Plant (G5)", "Power Distributor (G5)",
                                    "Wake Scanner (G5)", "Kill Warrant Scanner (G5)",
                                    "Manifest Scanner (G5)", "Rail Gun (G5)"),
                                   "Spam G1 Overcharged Power Plant — Sulphur only (Colonia)"),
    "Petra Olmanova":     _EngData("Armour / Countermeasures", "Sanctuary",         "Asura",
                                   "Tod McQuinn invite + Combat rank Expert + 200 Progenitor Cells",
                                   ("Hull Reinforcement Package (G5)", "Mine Launcher (G5)",
                                    "Seeker Missile Rack (G5)", "Torpedo Pylon (G5)", "Armour (G5)",
                                    "Missile Rack (G5)", "Chaff Launcher (G5)", "ECM (G5)",
                                    "Heat Sink Launcher (G5)", "Point Defence (G5)", "AFMU (G5)"),
                                   "Spam G1 Blast Resistant Hull — Nickel only (Colonia)"),
    # ── Odyssey (on-foot equipment) ───────────────────────────────────────────
    "Jude Navarro":       _EngData("Suit / Weapon",     "Marshall's Drift",         "Aurai",
                                   "Complete 10 Restore or Reactivation missions",
                                   ("Reload speed", "Magazine size", "Extra ammo capacity",
                                    "Damage resistance", "Added melee damage"),
                                   "Run Restore/Reactivation missions — quick and solo-friendly"),
    "Domino Green":       _EngData("Weapon",            "The Jackrabbit",           "Orishis",
                                   "Travel 100+ ly in shuttles",
                                   ("Greater range", "Stability", "Enhanced tracking",
                                    "Extra backpack capacity", "Reduced tool battery consumption"),
                                   "Take apex shuttles between distant systems — fastest unlock"),
    "Hero Ferrari":       _EngData("Suit",              "Nevermore Terrace",        "Siris",
                                   "Complete 10 surface conflict zones",
                                   ("Faster handling", "Noise suppressor", "Increased sprint duration",
                                    "Improved jump assist", "Increased air reserves"),
                                   "Farm surface CZs — low-tier ones count, fastest in groups"),
    "Terra Velasquez":    _EngData("Suit",              "Rascal's Choice",          "Shou Xing",
                                   "Jude Navarro invite + 6 covert theft/heist missions",
                                   ("Improved hip fire accuracy", "Noise suppressor",
                                    "Increased sprint duration", "Combat movement speed",
                                    "Increased air reserves"),
                                   "Run Covert Theft/Heist missions — Odyssey mission boards"),
    "Uma Laszlo":         _EngData("Weapon",            "Laszlo's Resolve",         "Xuane",
                                   "Wellington Beck invite + reach Unfriendly with Sirius Corp",
                                   ("Reload speed", "Stowed reloading", "Headshot damage",
                                    "Damage resistance", "Faster shield regen"),
                                   "Sell Sirius data/goods to rivals until Sirius rep = Unfriendly"),
    "Oden Geiger":        _EngData("Suit",              "Ankh's Promise",           "Candiaei",
                                   "Terra Velasquez invite + 20 biological/genetic data to bartenders",
                                   ("Stability", "Scope", "Enhanced tracking",
                                    "Improved battery capacity", "Night vision"),
                                   "Sell Biological Data to bartenders at stations — easy via exobio"),
    "Baltanos":           _EngData("Suit",              "The Divine Apparatus",     "Deriso",
                                   "Friendly with Colonia Council",
                                   ("Noise suppressor", "Improved hip fire accuracy", "Faster handling",
                                    "Improved jump assist", "Increased air reserves",
                                    "Increased sprint duration", "Combat movement speed"),
                                   "Run missions for Colonia Council factions until Friendly"),
    "Yi Shen":            _EngData("Weapon",            "Eidolon Hold",             "Einheriar",
                                   "Baltanos, Eleanor Bresa, or Rosa Dayette invite + referral tasks",
                                   ("Audio masking", "Headshot damage", "Quieter footsteps", "Night vision"),
                                   "Complete referral tasks given by Baltanos/Rosa/Eleanor"),
    "Rosa Dayette":       _EngData("Suit / Weapon",     "Rosa's Shop",              "Kojeara",
                                   "Sell 10 recipe items to Colonia stations",
                                   ("Greater range", "Scope", "Stability", "Extra backpack capacity",
                                    "Enhanced tracking", "Reduced tool battery consumption",
                                    "Improved battery capacity"),
                                   "Sell crafted suit/weapon recipe items to Colonia bartenders"),
    "Eleanor Bresa":      _EngData("Suit / Weapon",     "Bresa Modifications",      "Desy",
                                   "Visit 5 settlements in Colonia",
                                   ("Magazine size", "Reload speed", "Stowed reloading",
                                    "Added melee damage", "Damage resistance",
                                    "Extra ammo capacity", "Faster shield regen"),
                                   "Land at 5 different Colonia settlements — quick flyby counts"),
    "Kit Fowler":         _EngData("Weapon",            "The Last Call",            "Capoya",
                                   "Domino Green invite + sell 5 Opinion Polls to bartenders",
                                   ("Added melee damage", "Extra ammo capacity", "Faster shield regen",
                                    "Magazine size", "Stowed reloading"),
                                   "Buy Opinion Polls at stations and sell to bartenders"),
    "Wellington Beck":    _EngData("Suit",              "Beck Facility",            "Jolapa",
                                   "Hero Ferrari invite + sell 15 entertainment items to bartenders",
                                   ("Extra backpack capacity", "Improved battery capacity",
                                    "Reduced tool battery consumption", "Greater range", "Scope"),
                                   "Buy entertainment items at stations and sell to bartenders"),
    "Yarden Bond":        _EngData("Suit",              "Salamander Bank",          "Bayan",
                                   "Kit Fowler invite + sell 5 Smear Campaign Plans to bartenders",
                                   ("Faster handling", "Improved hip fire accuracy", "Audio masking",
                                    "Improved jump assist", "Combat movement speed", "Quieter footsteps"),
                                   "Buy Smear Campaign Plans at stations and sell to bartenders"),
}



def _build_eng_list(s: AppState) -> list[tuple[str, str, int, float, str]]:
    """Return flattened [(era_tag, name, rank, rp, prog)] sorted by era, status, rank desc, name."""
    _STATUS_ORDER = {"Unlocked": 0, "Invited": 1, "Acquainted": 1, "Known": 1, "Unknown": 3}

    result: list[tuple[str, str, int, float, str]] = []
    seen_names: set[str] = set()

    for _, info in s.engineers.items():
        if isinstance(info, EngineerInfo):
            name, prog, rank, rp = info.name, info.progress, info.rank, info.rank_progress
        else:
            rank, prog = info; rp = 0.0; name = ""
        if not name:
            continue
        seen_names.add(name)
        era = "O" if name in _ODY_ENGINEERS else "H"
        result.append((era, name, rank, rp, prog))

    for name in _ENGINEER_STATIC:
        if name not in seen_names:
            era = "O" if name in _ODY_ENGINEERS else "H"
            result.append((era, name, 0, 0.0, "Unknown"))

    def _sort_key(e: tuple) -> tuple:
        era, nm, rnk, _rp, pg = e
        return (0 if era == "H" else 1, _STATUS_ORDER.get(pg, 2), -rnk, nm)

    result.sort(key=_sort_key)
    return result



def _eng_rank_pips(rank: int, rp: float, prog: str, is_ody: bool) -> tuple[str, str, str, str]:
    """Return (pips_str, pips_style, grade_str, grade_style) for one engineer."""
    if prog == "Unlocked":
        if is_ody:
            return "●", P.HUD_GREEN, "", ""
        max_r = 5
        eff_r = min(rank, max_r)
        pips  = "●" * eff_r + "○" * (max_r - eff_r)
        return pips, P.HUD_GREEN, "", ""
    if prog in ("Invited", "Acquainted", "Known"):
        if rp > 0:
            filled = int(rp / 100.0 * 5)
            pips   = "▓" * filled + "░" * (5 - filled)
            return pips, P.AMBER, f"{rp:.0f}%", P.AMBER
        return "○○○○○", P.AMBER, "", ""
    if prog == "Unknown":
        return "·····", "dim", "", "dim"
    return "·····", "dim", "", "dim"



def _render_engineer_detail(name: str, rank: int, rp: float, prog: str, mp: dict | None = None) -> RenderableType:
    """Box-style full-panel detail view for one engineer (Space to enter, Backspace to exit)."""
    mp = mp or P.mp("ship")
    is_ody  = name in _ODY_ENGINEERS
    eng     = _ENGINEER_STATIC.get(name)
    spec    = eng.specialty if eng else ""
    station = eng.station   if eng else ""
    system  = eng.system    if eng else ""
    unlock  = eng.unlock    if eng else ""
    modules = eng.modules   if eng else ()
    hint    = eng.hint      if eng else ""

    pips, pip_style, grade, grade_style = _eng_rank_pips(rank, rp, prog, is_ody)

    inner = Text()

    # Name + rank row
    inner.append(f"{name}\n", style="bold white")

    # Rank pips row
    inner.append(pips, style=pip_style)
    if grade:
        inner.append(f"  {grade}", style=grade_style)
    inner.append("\n")

    # Location
    if system or station or spec:
        inner.append("\n")
        if spec:
            inner.append(spec, style=P.LABEL)
        if system:
            inner.append("  ·  " if spec else "", style=P.LABEL)
            inner.append(system, style=P.HUD_CYAN)
        if station:
            inner.append("  ·  " if (spec or system) else "", style=P.LABEL)
            inner.append(station, style=P.LABEL)
        inner.append("\n")

    # Unlock
    if unlock:
        inner.append("\n")
        inner.append("UNLOCK", style=f"bold {mp['h1']}")
        if prog == "Unlocked":
            inner.append("  ✓", style=P.HUD_GREEN)
        inner.append("\n")
        inner.append(f"{unlock}\n", style="white")

    # Modules
    if modules:
        inner.append("\n")
        inner.append("MODULES\n", style=f"bold {mp['h1']}")
        for mod in modules:
            # Split "Module Name (G5)" into name + grade for alignment
            if " (" in mod and mod.endswith(")"):
                mod_name, mod_grade = mod.rsplit(" (", 1)
                mod_grade = mod_grade.rstrip(")")
                inner.append(f"  {mod_name:<28}", style="white")
                inner.append(mod_grade + "\n",    style=P.LABEL)
            else:
                inner.append(f"  {mod}\n", style="white")

    # Leveling hint
    if hint:
        inner.append("\n")
        inner.append("HINT\n", style=f"bold {mp['h1']}")
        inner.append(f"{hint}\n", style="white")

    parts: list[RenderableType] = [inner]
    nav = Text()
    nav.append("  [Enter] back", style="dim")
    parts.append(nav)
    return Group(*parts)



def _render_engineers(s: AppState, scroll: int = 0, cursor: int = 0, detail: bool = False, mp: dict | None = None) -> RenderableType:
    mp = mp or P.mp("ship")
    all_engs = _build_eng_list(s)

    if not all_engs:
        t = Text()
        t.append("No engineer data.", style=P.LABEL)
        return t

    # Detail view: full box-panel for the selected engineer
    if detail and 0 <= cursor < len(all_engs):
        _era, name, rank, rp, prog = all_engs[cursor]
        return _render_engineer_detail(name, rank, rp, prog, mp=mp)

    effective_scroll = min(scroll, max(0, len(all_engs) - 1))

    tbl = Table(
        show_header=False, show_edge=False, show_lines=False,
        padding=(0, 0), box=None,
        row_styles=["", f"on {P.ROW_ALT}"],
    )
    tbl.add_column("#", width=3)
    tbl.add_column(">", width=2)
    tbl.add_column("Era", width=4)
    tbl.add_column("Name", width=20, no_wrap=True)
    tbl.add_column("Pips", width=5)
    tbl.add_column("Grade", width=3)
    tbl.add_column("Specialty", width=23, no_wrap=True)
    tbl.add_column("", width=1)
    tbl.add_column("System", width=19, no_wrap=True)

    for flat_idx, (era_tag, name, rank, rp, prog) in enumerate(all_engs[effective_scroll:], start=effective_scroll):
        is_ody   = name in _ODY_ENGINEERS
        eng      = _ENGINEER_STATIC.get(name)
        spec     = eng.specialty if eng else ""
        system   = eng.system    if eng else ""
        selected = flat_idx == cursor

        pips, pip_style, grade, grade_style = _eng_rank_pips(rank, rp, prog, is_ody)

        display_name = name if len(name) <= 19 else name[:18] + "…"

        cursor_text = Text("▶ ", style=P.HUD_GREEN) if selected else Text("  ")
        name_text   = Text(f"{display_name:<20}", style="bold white" if selected else "white")

        if is_ody:
            pip_text = Text(pips[0] if pips else "·", style=pip_style)
            pip_text.append("    ")
        else:
            pip_text = Text(pips, style=pip_style)

        grade_text = Text(f"{grade:<3}", style=grade_style)
        spec_text  = Text(spec, style="white" if selected else P.LABEL)
        sys_text   = Text(system, style=P.HUD_CYAN)

        tbl.add_row(
            Text(str(flat_idx + 1)),
            cursor_text,
            Text(f"[{era_tag}] ", style="dim"),
            name_text,
            pip_text,
            grade_text,
            spec_text,
            Text(""),
            sys_text,
        )

    hint = Text()
    hint.append("  [Enter] details  [↑↓] move", style="dim")

    return Group(_section_header("ENGINEERS", mp["h1"], mp["bg"]), hint, tbl)


