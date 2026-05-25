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
    _Panel,
    _data_table, _section_header, _kv_row, _kv_line, _two_column_table,
    _short_name, _natural_key,
    _body_color, _abbrev_type, _body_value, _body_value_color,
    _fmt_cr_compact, _fmt_value, _fmt_ls_compact, _fmt_metres,
    _fmt_notable_val, _de,
)
from .assets import _render_assets
from ...materials_catalog import (
    RAW_CATEGORIES, MANUFACTURED_CATEGORIES, ENCODED_CATEGORIES,
)
from .bgs import _render_bgs
from .bio import _render_bio
from .colonisation import _render_colonisation
from .engineers import _render_engineers, _build_eng_list
from .maps import _render_galaxy, _render_system_map
from .missions import _render_missions
from .neutron import _render_neutron
from .overview import _render_overview
from .route import _render_route
from .stats import _render_stats


class SituationalPanel(_Panel):
    """Context-aware panel: auto-switches between Bio / Missions / Inventory.
    Tab cycles through modes manually."""

    _MODES = (
        "auto", "overview", "bio", "galaxy", "missions", "engineers",
        "bgs", "colonisation", "route", "neutron", "assets", "stats",
    )
    _mode:            str   = "overview"  # current shown panel (user or auto-triggered)
    _active:          str   = "overview" # resolved panel being rendered (always == _mode)
    _auto:            bool  = True       # auto-switching enabled (A key toggles)
    _last_trigger_version: int = 0  # last auto_panel_trigger_version we acted on
    _last_auto_target:     str = ""  # panel that was last auto-switched to; same target is skipped
    _galaxy_submode:      str  = "system"   # "system" | "regional" | "galaxy"
    _neutron_scroll:      int  = 0
    _bgs_scroll:          int  = 0
    _colonisation_scroll: int  = 0
    _route_scroll:        int  = 0
    _general_scroll:      int  = 0
    _eng_cursor:          int  = 0
    _eng_detail:          bool = False
    _visible_modes:       list = []  # populated in update() from snap.situational_panels
    # System map cache — rebuilt only when bodies or system change
    _map_cache:           object = None
    _map_cache_version:   int    = -1
    _map_cache_system:    str    = ""
    _map_standalone_cache: object = None

    _MODE_ABBREVS = {
        "auto": "***", "overview": "Overview", "bio": "Bio", "galaxy": "Maps",
        "missions": "Mission", "engineers": "Engineer", "bgs": "BGS", "colonisation": "Colony",
        "route": "Route", "neutron": "Plot", "assets": "Assets",
        "stats": "Stats",
    }

    _MODE_FULLNAMES = {
        "auto": "AUTO", "overview": "OVERVIEW", "bio": "BIOLOGICAL", "galaxy": "MAPS",
        "missions": "MISSION", "engineers": "ENGINEERS", "bgs": "BGS", "colonisation": "COLONISATION",
        "route": "ROUTE", "neutron": "NEUTRON", "assets": "ASSETS",
        "stats": "STATISTICS",
    }

    DEFAULT_CSS = P.css("""
    SituationalPanel {
        border: solid [[PANEL_BORDER]];
        border-title-color: [[PANEL_BORDER]];
        border-title-style: bold;
        height: 1fr;
    }
    """)

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
        self._eng_cursor = 0
        self._eng_detail = False
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
        self._eng_cursor = 0
        self._eng_detail = False
        self.border_title = self._make_title()
        self.refresh()

    def toggle_auto_lock(self) -> None:
        """Toggle automatic panel switching on/off."""
        self._auto = not self._auto
        # When re-enabling auto, sync trigger state so pending triggers don't
        # immediately fire — only genuinely new events cause a switch.
        if self._auto and self._snap is not None:
            self._last_trigger_version = self._snap.auto_panel_trigger_version
            self._last_auto_target = self._snap.auto_panel_trigger
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

    def eng_move(self, delta: int) -> None:
        if self._eng_detail or self._snap is None:
            return
        total = len(_build_eng_list(self._snap))
        self._eng_cursor = max(0, min(self._eng_cursor + delta, max(0, total - 1)))
        self.refresh()

    def eng_select(self) -> None:
        self._eng_detail = True
        self.refresh()

    def eng_back(self) -> None:
        self._eng_detail = False
        self.refresh()

    _NON_SCROLLABLE = frozenset({"overview", "stats", "galaxy"})

    def scroll_general(self, delta: int) -> None:
        """Scroll the current situational panel up/down (for all non-specialised modes)."""
        if self._active in self._NON_SCROLLABLE:
            return
        self._general_scroll = max(0, self._general_scroll + delta)
        self.refresh()

    def _make_title(self) -> str:
        _mp = P.mp(self._snap.ui_mode if self._snap else "ship")
        # *** indicator: bright = auto ON, dim = auto OFF
        if self._auto:
            auto_tag = f"[bold {_mp['h1']}]***[/]"
        else:
            auto_tag = "[dim]***[/]"

        # All modes shown as readable short names — current highlighted, others dim.
        parts = []
        for m in self._active_modes():
            abbr = self._MODE_ABBREVS[m]
            if m == self._mode:
                col = _mp["h1"] if self._auto else "white"
                parts.append(f"[bold {col}]{abbr}[/]")
            else:
                parts.append(f"[dim]{abbr}[/]")

        joined = auto_tag + "  " + " ".join(parts)
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

        # Auto-switching: one-shot triggers from events.py via auto_panel_trigger_version.
        # Rules:
        #   • Each trigger fires at most once (version counter).
        #   • A trigger for the same panel as the last auto-switch is ignored —
        #     NOVA stays wherever it is until a *different* panel is triggered.
        #   • Manual cycles (left/right) are never overridden; they simply move
        #     _mode and the next auto-switch only fires for a different target.
        if self._auto and snap.auto_panel_trigger_version != self._last_trigger_version:
            self._last_trigger_version = snap.auto_panel_trigger_version
            target = snap.auto_panel_trigger
            if target and target in self._visible_modes and target != self._last_auto_target:
                self._mode = target
                self._last_auto_target = target
                self._general_scroll = 0
                self._eng_cursor = 0
                self._eng_detail = False

        new_active = self._mode
        if new_active != self._active:
            self._general_scroll = 0
            self._eng_cursor = 0
            self._eng_detail = False
        self._active = new_active

        # Build a mode-specific key so only the active sub-panel's data triggers a redraw.
        # Always refresh when the active mode itself changes (new_active != self._active above).
        mode = new_active
        if mode == "overview":
            mode_key = (
                snap.system, snap.bodies_version, snap.route_hops, snap.route_destination,
                snap.population, snap.nearest_populated_name, snap.nearest_populated_dist,
                snap.system_power, snap.system_power_state,
                len(snap.carriers_current_system),
                snap.controlling_faction, snap.controlling_state, len(snap.factions),
                snap.pp_power, snap.pp_total_merits,
                snap.session_jumps, snap.session_first_disc, snap.session_mapped,
                snap.session_value, snap.credits, snap.cargo, len(snap.missions),
            )
        elif mode == "bio":
            mode_key = (
                snap.bodies_version,
                len(snap.bio_scans),
                tuple((sc.body, sc.samples, sc.complete, sc.current_dist) for sc in snap.bio_scans),
                snap.lat, snap.lon,
            )
        elif mode == "galaxy":
            mode_key = (snap.system, snap.bodies_version, self._galaxy_submode)
        elif mode == "route":
            mode_key = (
                snap.route_destination, snap.route_hops, snap.route_next,
                snap.route_next_star, snap.route_next_scoopable,
                snap.route_dist, snap.route_next_dist,
                len(snap.route_list), len(snap.route_next_stations),
                snap.neutron_route_to, snap.neutron_route_status,
            )
        elif mode == "missions":
            mode_key = (snap.system, len(snap.missions), tuple(m.mission_id for m in snap.missions))
        elif mode == "bgs":
            mode_key = (snap.system, len(snap.bgs_log), snap.controlling_faction, snap.controlling_state)
        elif mode == "colonisation":
            mode_key = (snap.system, len(snap.colonisation_sites))
        elif mode == "engineers":
            mode_key = (
                tuple((info.name, info.rank, info.rank_progress, info.progress)
                      for info in snap.engineers.values()
                      if isinstance(info, EngineerInfo)),
                self._eng_cursor,
                self._eng_detail,
            )
        elif mode == "neutron":
            mode_key = (
                snap.neutron_route_to, snap.neutron_route_status,
                len(snap.neutron_route), snap.route_hops,
                snap.system, snap.jump_range,
            )
        elif mode == "assets":
            mode_key = (
                snap.credits, snap.cargo, len(snap.stored_ships),
                len(snap.cargo_items),
                len(snap.materials_raw), len(snap.materials_mfg), len(snap.materials_enc),
                len(snap.backpack), len(snap.ship_locker),
            )
        elif mode == "stats":
            mode_key = (snap.events_version, snap.bodies_version)
        else:
            mode_key = (snap.events_version, snap.bodies_version)

        key = (mode, snap.auto_panel_trigger_version) + mode_key
        if self._key_changed(key):
            self.refresh()

    def render(self) -> RenderableType:
        s = self._snap
        if s is None:
            return Text("")

        mode    = self._active
        panel_h = self.size.height or 20
        panel_w = self.size.width  or 40

        _mp = P.mp(s.ui_mode)

        # ── Galaxy: sub-view indicator only, no scroll ────────────────────
        if mode == "galaxy":
            _subs = ("system", "regional", "galaxy")
            idx   = _subs.index(self._galaxy_submode) + 1 if self._galaxy_submode in _subs else 1
            self.border_title    = self._make_title()
            self.border_subtitle = f"{idx}/3  "
            sub = self._galaxy_submode
            if sub == "system":
                # Re-render only when bodies or system change
                if (s.bodies_version != self._map_cache_version or
                        s.system != self._map_cache_system):
                    self._map_standalone_cache = _render_system_map(s, standalone=True, mp=_mp)
                    self._map_cache_version = s.bodies_version
                    self._map_cache_system  = s.system
                result = self._map_standalone_cache
                return result if result is not None else Text("No bodies scanned yet.", style=P.LABEL)
            return _render_galaxy(s, regional=(sub == "regional"),
                                  panel_w=panel_w, panel_h=panel_h, mp=_mp)

        # ── Compute per-mode item count + clamp scroll ────────────────────
        max_rows_route = max(5, panel_h - 5)  # matches _render_route
        _eng_vis = max(1, panel_h - 2)

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
            scroll = max(0, min(self._general_scroll, max(0, total - max(1, panel_h - 2))))
            self._general_scroll = scroll

        elif mode == "missions":
            total  = len(s.missions)
            scroll = max(0, min(self._general_scroll, max(0, total - max(1, panel_h - 2))))
            self._general_scroll = scroll

        elif mode == "engineers":
            if self._eng_detail:
                total  = 0
                scroll = 0
            else:
                all_engs = _build_eng_list(s)
                total  = len(all_engs)
                _eng_list_vis = max(1, _eng_vis - 1)
                scroll = max(self._eng_cursor - _eng_list_vis + 1, 0)
                scroll = max(0, min(scroll, max(0, total - _eng_list_vis)))
                self._general_scroll = scroll

        elif mode == "assets":
            # Unified assets scroll count — exact match to _render_assets
            _asset_rows = 0
            # Balance (always present: header + value row)
            _asset_rows += 2
            # Fleet (header + current ship + stored ships or placeholder)
            _asset_rows += 1
            if s.ship_type or s.ship_name:
                _asset_rows += 1
            if s.stored_ships:
                _asset_rows += len(s.stored_ships)
            else:
                _asset_rows += 1
            # Cargo
            if s.cargo_items:
                _asset_rows += 1 + len(s.cargo_items)
            # Suit loadout (header + suit name + weapons)
            if s.suit_loadout:
                _asset_rows += 2 + len(s.suit_loadout.get("weapons", []))
            # Odyssey
            _has_bp = any(s.backpack.get(k) for k in ("items", "components", "consumables", "data"))
            _has_lk = any(s.ship_locker.get(k) for k in ("items", "components", "consumables", "data"))
            if _has_bp or _has_lk:
                _asset_rows += 1  # divider
                for _ok in ("items", "components", "consumables", "data"):
                    _bi = s.backpack.get(_ok) or []
                    if _bi: _asset_rows += 1 + len(_bi)
                    _li = s.ship_locker.get(_ok) or []
                    if _li: _asset_rows += 1 + len(_li)
            # Materials (vertical list — 1 header + all individual materials)
            for _md, _cats in (
                (s.materials_raw, RAW_CATEGORIES),
                (s.materials_mfg, MANUFACTURED_CATEGORIES),
                (s.materials_enc, ENCODED_CATEGORIES),
            ):
                if _md:
                    _asset_rows += 1 + sum(len(mats) for _, mats in _cats)
            total    = _asset_rows
            vis_rows = max(1, panel_h - 2)
            scroll   = max(0, min(self._general_scroll, max(0, total - vis_rows)))
            self._general_scroll = scroll

        elif mode == "bgs":
            total  = sum(len(facs) for facs in s.bgs_log.values()) if s.bgs_log else 0
            scroll = max(0, min(self._bgs_scroll, max(0, total - max(1, panel_h - 2))))
            self._bgs_scroll = scroll

        elif mode == "colonisation":
            total  = len(s.colonisation_sites) if s.colonisation_sites else 0
            scroll = max(0, min(self._colonisation_scroll, max(0, total - max(1, panel_h - 2))))
            self._colonisation_scroll = scroll

        elif mode == "neutron":
            total  = len(s.neutron_route) if s.neutron_route else 0
            scroll = max(0, min(self._neutron_scroll, max(0, total - max(1, panel_h - 2))))
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
        elif mode == "engineers":
            below = 0 if self._eng_detail else max(0, total - scroll - _eng_vis)
        else:
            below = max(0, total - scroll - max(1, panel_h - 2))

        # ── Set border indicators (both in bottom border, independent of title) ──
        self.border_title = self._make_title()
        if above > 0 and below > 0:
            self.border_subtitle = f"▲{above}  ▼{below}"
        elif above > 0:
            self.border_subtitle = f"▲{above}"
        elif below > 0:
            self.border_subtitle = f"▼{below}"
        else:
            self.border_subtitle = ""

        # ── Dispatch to render functions ──────────────────────────────────
        if mode == "bio":
            return _render_bio(s, scroll=scroll, mp=_mp)
        if mode == "missions":
            return _render_missions(s, scroll=scroll, mp=_mp)
        if mode == "engineers":
            return _render_engineers(s, scroll=scroll, cursor=self._eng_cursor, detail=self._eng_detail, mp=_mp)
        if mode == "assets":
            return _render_assets(s, scroll=scroll, panel_w=panel_w, mp=_mp)
        if mode == "neutron":
            return _render_neutron(s, scroll=scroll, mp=_mp)
        if mode == "stats":
            return _render_stats(s, mp=_mp)
        if mode == "bgs":
            return _render_bgs(s, scroll=scroll, mp=_mp)
        if mode == "colonisation":
            return _render_colonisation(s, scroll=scroll, mp=_mp)
        if mode == "route":
            return _render_route(s, scroll=scroll, panel_height=panel_h, mp=_mp)
        return _render_overview(s, panel_h=panel_h, panel_w=panel_w, mp=_mp)


