from __future__ import annotations

import copy
import queue
import threading
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Static
from textual import events

from ..state import AppState
from .settings_screen import SettingsScreen
from . import palette as P
from .panels import (
    BodiesPanel,
    ChatLogPanel,
    EventLogPanel,
    FooterBar,
    RoutePanel,
    ShipPanel,
    SituationalPanel,
    SystemPanel,
)


class HelpScreen(Screen):
    CSS = """
    HelpScreen {
        background: rgb(18,18,18);  /* P.BG_DARK */
        align: center middle;
    }
    #help-scroll {
        width: 80;
        height: 90%;
        background: rgb(18,18,18);
    }
    #help-static {
        width: 76;
        height: auto;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        try:
            from importlib.metadata import version as _pkg_ver
            ver = _pkg_ver("nova-ed-monitor")
        except Exception:
            ver = "?"

        from rich.table import Table
        from rich.text import Text
        from rich.panel import Panel
        from rich.console import Group

        GOLD  = f"bold {P.HEADER}"
        WHITE = P.WHITE
        DIM   = P.LABEL

        # ── Header ────────────────────────────────────────────────────────────
        header = Text()
        header.append("NOVA", style="bold white")
        header.append(f"  v{ver}", style=DIM)
        header.append("  Navigation, Operations & Vessel Assistance", style=DIM)

        # ── Keyboard shortcuts ─────────────────────────────────────────────
        kb = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        kb.add_column(width=18)
        kb.add_column()
        for key, desc in [
            ("q / Esc",          "Quit"),
            ("?",                "This help screen"),
            ("Tab",              "Cycle focused panel forward (1→6)"),
            ("Shift+Tab",        "Cycle focused panel backward (6→1)"),
            ("a",                "Toggle auto panel switching on/off"),
            ("↑ / k",            "Scroll situational panel up (MAP mode: previous sub-view)"),
            ("↓ / j",            "Scroll situational panel down (MAP mode: next sub-view)"),
            ("PgUp / PgDn",      "Scroll focused panel (or situational when none focused)"),
            ("Home / End",       "Jump to top / bottom of focused panel"),
            ("← / →",            "Cycle situational panel modes"),
            ("s",                "Open settings overlay"),
            ("n",                "Neutron route destination input (Neutron mode only)"),
            ("m",                "Mute / unmute all TTS"),
            ("Enter",            "Engineers: open detail / return to list"),
            ("g",                "Toggle in-game chat TTS"),
            ("t",                "Toggle Twitch chat TTS"),
            ("y",                "Toggle YouTube chat TTS"),
            ("p",                "Toggle all chat TTS at once"),
            ("+ / =",            "Volume up"),
            ("−",                "Volume down"),
        ]:
            kb.add_row(Text(key, style=GOLD), Text(desc, style=WHITE))

        # ── Situational modes ──────────────────────────────────────────────
        sm = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        sm.add_column(width=14)
        sm.add_column()
        for mode, desc in [
            ("*** / Auto",       "Auto-switches by context; a = toggle lock"),
            ("OVR / Overview",   "Route + position · notable bodies · PP/BGS · nearest inhabited"),
            ("BIO / Biological", "Active bio scans with distances and bearings"),
            ("MAP / Maps",       "System diagram → regional → galaxy map (↑/↓ to cycle)"),
            ("MIS / Mission",    "Active missions and massacre kill progress"),
            ("ENG / Engineers",  "Engineer unlock progress and rank"),
            ("BGS",              "BGS activity log — per-faction activity counts"),
            ("COL / Colonisation","Construction site commodity progress"),
            ("ROU / Route",      "Nav route with star class, distances, EDSM body/bio data"),
            ("NTR / Neutron",    "Local neutron route planner (n = new route)"),
            ("WLT / Wallet",     "Balance · fleet · cargo · suit loadout · backpack"),
            ("INV / Inventory",  "Cargo and raw / manufactured / encoded materials"),
            ("DKG / Docking",    "Station pad diagram (top-down)"),
            ("STS / Statistics", "Persistent statistics: today / week / month / year / total"),
        ]:
            sm.add_row(Text(mode, style=GOLD), Text(desc, style=WHITE))

        # ── Config path ────────────────────────────────────────────────────
        from ..config import config_dir as _config_dir
        cfg = Text()
        cfg.append(str(_config_dir() / "config.toml"), style=WHITE)

        edsm_note = Text()
        edsm_note.append("Power Play state and nearest inhabited system shown in Position panel.\n", style=DIM)
        edsm_note.append("Stations at next route waypoint shown in Route situational panel.\n", style=DIM)
        edsm_note.append("Data sourced from EDSM nightly dumps, refreshed automatically once per day.", style=DIM)

        content = Panel(
            Group(
                header, Text(""),
                Text("Keyboard Shortcuts", style=GOLD), kb, Text(""),
                Text("Situational Panel Modes", style=GOLD), sm, Text(""),
                Text("EDSM Data", style=GOLD), edsm_note, Text(""),
                Text("Config File", style=GOLD), cfg, Text(""),
                Text("https://github.com/KernicDE/nova-ed-monitor", style=DIM),
                Text("Press Esc to close", style=DIM),
            ),
            title="NOVA — Help & About",
            title_align="left",
            border_style=P.HEADER,
            padding=(1, 2),
        )
        yield VerticalScroll(
            Static(content, id="help-static"),
            id="help-scroll",
        )

    def on_mount(self) -> None:
        self.query_one("#help-scroll").focus()

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "question_mark"):
            event.stop()
            self.app.pop_screen()


class NeutronInputScreen(Screen):
    """Overlay for entering a neutron route destination."""

    CSS = """
    NeutronInputScreen {
        background: rgba(10,10,10,0.9);
        align: center middle;
    }
    #neutron-box {
        width: 60;
        height: auto;
        background: rgb(28,28,28);       /* near P.BG_DARK, slightly lighter */
        border: solid rgb(195,160,55);   /* P.HEADER */
        padding: 1 2;
    }
    #neutron-label {
        color: rgb(195,160,55);          /* P.HEADER */
        text-style: bold;
        margin-bottom: 1;
    }
    Input {
        margin-top: 1;
    }
    #neutron-hint {
        color: rgb(100,100,100);         /* P.LABEL_DIM */
        margin-top: 1;
    }
    """

    def __init__(self, neutron_q, current_system: str = "") -> None:
        super().__init__()
        self._neutron_q      = neutron_q
        self._current_system = current_system

    def compose(self) -> ComposeResult:
        with Vertical(id="neutron-box"):
            yield Label("◈ Neutron Route Plotter", id="neutron-label")
            yield Label(f"From: {self._current_system or '(current system)'}")
            yield Input(placeholder="Enter destination system name…", id="neutron-dest")
            yield Label("Enter to plot  ·  Esc to cancel", id="neutron-hint")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        target = event.value.strip()
        if target and self._neutron_q is not None:
            self._neutron_q.put(("plot", target))
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.app.pop_screen()


class NOVAApp(App):
    CSS = """
    Screen {
        background: rgb(18,18,18);  /* P.BG_DARK */
    }

    #top-row {
        height: auto;
        width: 100%;
    }

    #middle-row {
        width: 100%;
        height: 1fr;
    }

    #left-col {
        width: 4fr;
    }

    #center-col {
        width: 5fr;
    }

    #right-col {
        width: 3fr;
    }

    BodiesPanel {
        height: 1fr;
    }

    SituationalPanel {
        height: 1fr;
    }

    SystemPanel {
        width: 4fr;
    }

    ShipPanel {
        width: 5fr;
    }

    RoutePanel {
        width: 3fr;
        max-height: 40;
    }

    EventLogPanel {
        height: 2fr;
    }

    ChatLogPanel {
        height: 1fr;
    }

    /* Focused panel: bright white border with underlined title — overrides all mode borders */
    .focused {
        border: heavy white !important;
        border-title-color: white !important;
        border-title-style: bold underline !important;
    }

    FooterBar {
        height: 1;
    }
    
    /* Ship / analysis mode — ED orange (default when in-ship, docked, supercruise, or analysis) */
    Screen.ship-mode SystemPanel,
    Screen.ship-mode ShipPanel,
    Screen.ship-mode RoutePanel,
    Screen.ship-mode BodiesPanel,
    Screen.ship-mode SituationalPanel,
    Screen.ship-mode EventLogPanel,
    Screen.ship-mode ChatLogPanel {
        border: solid rgb(255,128,0) !important;
        border-title-color: rgb(255,128,0) !important;
    }

    /* Combat mode overrides */
    Screen.combat-mode SystemPanel,
    Screen.combat-mode ShipPanel,
    Screen.combat-mode RoutePanel,
    Screen.combat-mode BodiesPanel,
    Screen.combat-mode SituationalPanel,
    Screen.combat-mode EventLogPanel,
    Screen.combat-mode ChatLogPanel {
        border: solid rgb(200,55,35) !important;
        border-title-color: rgb(200,55,35) !important;
    }

    /* On-foot (EVA) mode overrides */
    Screen.on-foot-mode SystemPanel,
    Screen.on-foot-mode ShipPanel,
    Screen.on-foot-mode RoutePanel,
    Screen.on-foot-mode BodiesPanel,
    Screen.on-foot-mode SituationalPanel,
    Screen.on-foot-mode EventLogPanel,
    Screen.on-foot-mode ChatLogPanel {
        border: solid rgb(80,160,235) !important;
        border-title-color: rgb(80,160,235) !important;
    }

    /* SRV mode overrides */
    Screen.srv-mode SystemPanel,
    Screen.srv-mode ShipPanel,
    Screen.srv-mode RoutePanel,
    Screen.srv-mode BodiesPanel,
    Screen.srv-mode SituationalPanel,
    Screen.srv-mode EventLogPanel,
    Screen.srv-mode ChatLogPanel {
        border: solid rgb(45,115,185) !important;
        border-title-color: rgb(45,115,185) !important;
    }

    /* Analysis mode overrides — same orange as ship mode */
    Screen.analysis-mode SystemPanel,
    Screen.analysis-mode ShipPanel,
    Screen.analysis-mode RoutePanel,
    Screen.analysis-mode BodiesPanel,
    Screen.analysis-mode SituationalPanel,
    Screen.analysis-mode EventLogPanel,
    Screen.analysis-mode ChatLogPanel {
        border: solid rgb(255,128,0) !important;
        border-title-color: rgb(255,128,0) !important;
    }

    /* Offline mode overrides */
    Screen.offline-mode SystemPanel,
    Screen.offline-mode ShipPanel,
    Screen.offline-mode RoutePanel,
    Screen.offline-mode BodiesPanel,
    Screen.offline-mode SituationalPanel,
    Screen.offline-mode EventLogPanel,
    Screen.offline-mode ChatLogPanel {
        border: solid rgb(70,70,70) !important;
        border-title-color: rgb(90,90,90) !important;
    }

    Screen.alert-flash {
        background: rgb(80, 0, 0);  /* deep combat red */
    }

    /* High-G extreme warning flash */
    Screen.high-g-flash SystemPanel,
    Screen.high-g-flash ShipPanel,
    Screen.high-g-flash RoutePanel,
    Screen.high-g-flash BodiesPanel,
    Screen.high-g-flash SituationalPanel,
    Screen.high-g-flash EventLogPanel,
    Screen.high-g-flash ChatLogPanel {
        border: solid rgb(220,100,0) !important;            /* P.HIGH_G_FLASH */
        border-title-color: rgb(220,100,0) !important;
    }

    Screen.high-g-flash {
        background: rgb(50, 20, 0);  /* deep amber warning */
    }
    """

    TITLE        = "NOVA (Navigation, Operations, and Vessel Assistance)"
    CURSOR_BLINK = False

    def __init__(
        self,
        state:    AppState,
        lock:     threading.RLock,
        volume:   list[int],
        vol_lock: threading.Lock,
        tts_q:    queue.Queue,
        stop_evt: threading.Event | None = None,
        neutron_q: queue.Queue | None = None,
        cfg: "object | None" = None,
    ) -> None:
        super().__init__()
        self._state     = state
        self._lock      = lock
        self._volume    = volume
        self._vol_lock  = vol_lock
        self._tts_q     = tts_q
        self._stop_evt  = stop_evt
        self._neutron_q = neutron_q
        self._cfg       = cfg
        self._focused_panel = 0  # 0=none, 1=System, 2=Ship, 3=Route, 4=Bodies, 5=Events, 6=Chat
        self._prev_css: dict[str, bool] = {}  # last applied CSS class states — skip set_class when unchanged
        self._prev_fingerprint: tuple = ()    # global state fingerprint — skip panel updates when unchanged

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-row"):
            yield SystemPanel()
            yield ShipPanel()
            yield RoutePanel()
        with Horizontal(id="middle-row"):
            with Vertical(id="left-col"):
                yield BodiesPanel()
            with Vertical(id="center-col"):
                yield SituationalPanel()
            with Vertical(id="right-col"):
                yield EventLogPanel()
                yield ChatLogPanel()
        yield FooterBar()

    def on_mount(self) -> None:
        # Refresh every 0.5s is plenty for ED data and saves massive CPU
        self.set_interval(0.5, self._refresh_all)
        # Force-hide the terminal cursor (Textual hides it in the driver, but
        # some terminals / focus events can restore it; belt-and-suspenders fix)
        try:
            self._driver.write("\x1b[?25l")
            self._driver.flush()
        except Exception:
            pass

    def _snapshot_light(self) -> AppState:
        """Shallow state copy. Primitive fields + shared references only — no
        collection clones. Safe for FooterBar, CSS-class flipping, and the
        fingerprint early-out. Panels that iterate collections must use the
        full snapshot instead.
        """
        with self._lock:
            return copy.copy(self._state)

    def _snapshot_full(self) -> AppState:
        """Full state snapshot with cloned collections. Only taken when the
        fingerprint has changed since the last render."""
        with self._lock:
            snap = copy.copy(self._state)
            snap.events         = copy.copy(self._state.events)
            snap.bodies         = list(self._state.bodies)
            snap.bio_scans      = list(self._state.bio_scans)
            snap.neutron_route  = list(self._state.neutron_route)
            snap.stored_ships   = list(self._state.stored_ships)
            snap.route_list     = list(self._state.route_list)
            snap.route_list_edsm   = dict(self._state.route_list_edsm)
            snap.route_bodies_edsm = dict(self._state.route_bodies_edsm)
            snap.carriers_current_system = list(self._state.carriers_current_system)
            snap.nearest_populated_stations = list(self._state.nearest_populated_stations)
            snap.current_system_stations = list(self._state.current_system_stations)
            snap.route_next_stations = list(self._state.route_next_stations)
        return snap

    # Back-compat: external callers may still refer to ._snapshot().
    _snapshot = _snapshot_full

    def _refresh_all(self) -> None:
        # Re-hide cursor every cycle (terminals may restore it on focus/resize)
        try:
            self._driver.write("\x1b[?25l")
            self._driver.flush()
        except Exception:
            pass

        # ── Cheap tick path ────────────────────────────────────────────────
        # Every tick (2 Hz) we need FooterBar, CSS class flips, and the
        # fingerprint early-out — all of which only touch primitive fields on
        # the state. The expensive collection copies are deferred until the
        # fingerprint actually changes, so idle seconds no longer clone the
        # bodies / events / route lists at 2 Hz.
        snap_light = self._snapshot_light()

        # ── CSS flash classes (time-based — must run every tick regardless of data) ──
        # Apply mode border class to the main screen — only call set_class when value changes
        # (set_class triggers CSS recalculation; guarding it eliminates ~8 DOM mutations per tick)
        offline  = not snap_light.client_online
        srv      = snap_light.in_srv and not offline
        on_foot  = not snap_light.in_main_ship and not snap_light.in_srv and not offline
        analysis = snap_light.analysis_mode and snap_light.in_main_ship and not offline
        combat   = not snap_light.analysis_mode and snap_light.in_main_ship and not offline
        ship     = not offline and not srv and not on_foot and not combat and not analysis

        # Derive ui_mode string and write it back so renderers can pick the right palette
        if offline:      _ui_mode = "offline"
        elif srv:        _ui_mode = "srv"
        elif on_foot:    _ui_mode = "on_foot"
        elif combat:     _ui_mode = "combat"
        elif analysis:   _ui_mode = "analysis"
        else:            _ui_mode = "ship"
        with self._lock:
            self._state.ui_mode = _ui_mode

        _css = self._prev_css
        def _sc(name: str, val: bool) -> None:
            if _css.get(name) != val:
                _css[name] = val
                self.screen.set_class(val, name)

        _sc("offline-mode",   offline)
        _sc("ship-mode",      ship)
        _sc("analysis-mode",  analysis)
        _sc("combat-mode",    combat)
        _sc("on-foot-mode",   on_foot)
        _sc("srv-mode",       srv)

        # Flash classes toggle every second when active — still guard to avoid 2× updates per second
        has_hazard = (
            snap_light.overheating
            or (0 < snap_light.hull < 0.25)
            or (snap_light.under_attack_flash_until > time.time())
        )
        flash_on   = has_hazard and (int(time.time()) % 2 == 0)
        _sc("alert-flash", flash_on)

        # High-G extreme approach flash (orange; stops when landed)
        high_g_flash = (
            snap_light.high_g_extreme
            and not snap_light.landed
            and not snap_light.in_srv
            and (int(time.time()) % 2 == 0)
        )
        _sc("high-g-flash", high_g_flash)

        # ── Global fingerprint early-out ───────────────────────────────────────────
        # Compare a cheap tuple of the most-changed fields. When nothing has changed
        # since the last tick, skip all panel .update() calls. Each panel's own
        # _key_changed() guard provides a second layer for when only some panels need
        # to redraw. FooterBar always runs — it's cheap and shows wall-clock stall info.
        #
        # Include int(time.time()) so the fingerprint ticks once per second, ensuring
        # FooterBar stall warnings and flash states re-evaluate at 1 Hz even when idle.
        _tick_s = int(time.time())
        fingerprint = (
            snap_light.system, snap_light.population,
            snap_light.hull, snap_light.fuel, snap_light.heat,
            snap_light.pips_sys, snap_light.pips_eng, snap_light.pips_wep,
            snap_light.lat, snap_light.lon,
            snap_light.bodies_version, snap_light.events_version,
            snap_light.route_hops, snap_light.route_destination,
            snap_light.client_online, snap_light.docked, snap_light.landed,
            snap_light.supercruise, snap_light.analysis_mode,
            snap_light.in_main_ship, snap_light.in_srv,
            snap_light.credits, snap_light.cargo,
            snap_light.neutron_route_status,
            snap_light.auto_panel_trigger_version,
            snap_light.chat_tts_muted, snap_light.twitch_tts_muted, snap_light.youtube_tts_muted,
            _tick_s,
        )

        # FooterBar only reads primitives + edsm_status (a shared ServiceStatus
        # reference) — the light snapshot is sufficient.
        self.query_one(FooterBar).update(snap_light)

        if fingerprint == self._prev_fingerprint:
            return
        self._prev_fingerprint = fingerprint

        # Fingerprint changed — now pay for the full snapshot and update panels.
        snap = self._snapshot_full()
        self.query_one(SystemPanel).update(snap)
        self.query_one(ShipPanel).update(snap)
        self.query_one(RoutePanel).update(snap)
        self.query_one(BodiesPanel).update(snap)
        self.query_one(SituationalPanel).update(snap)
        self.query_one(EventLogPanel).update(snap)
        self.query_one(ChatLogPanel).update(snap)

    def on_unmount(self) -> None:
        if self._stop_evt is not None:
            self._stop_evt.set()

    def on_settings_screen_saved(self, event: "SettingsScreen.Saved") -> None:
        """Apply live-reloadable settings from the overlay."""
        cfg = event.cfg
        self._cfg = cfg
        from .. import events as _ev
        _ev.set_tts_lang(cfg.tts_lang)
        _ev.set_voices(cfg.tts_voices)
        with self._vol_lock:
            self._volume[0] = cfg.default_volume
        with self._lock:
            self._state.volume = cfg.default_volume
            self._state.notable_value_threshold = cfg.notable_value_threshold
        from .. import voicelines as _vl
        _vl.reload_all()

    # Panel focus order: 1=System, 2=Ship, 3=Route, 4=Bodies, 5=Events, 6=Chat
    _FOCUS_PANELS = [SystemPanel, ShipPanel, RoutePanel, BodiesPanel, EventLogPanel, ChatLogPanel]

    def _set_focus(self, n: int) -> None:
        """Focus panel n (1-6) or clear focus (0). Adds/removes 'focused' CSS class."""
        for i, cls in enumerate(self._FOCUS_PANELS, start=1):
            try:
                p = self.query_one(cls)
                if i == n:
                    p.add_class("focused")
                else:
                    p.remove_class("focused")
            except Exception:
                pass
        self._focused_panel = n

    def _scroll_focused(self, delta: int) -> None:
        """Scroll up/down in the currently focused numbered panel."""
        n = self._focused_panel
        if n == 4:
            self.query_one(BodiesPanel).scroll_bodies(delta)
        elif n == 5:
            self.query_one(EventLogPanel).scroll_log(delta)
        elif n == 6:
            self.query_one(ChatLogPanel).scroll_chat(delta)

    def on_key(self, event: events.Key) -> None:
        # When the settings overlay is active it handles all its own keys.
        # Returning here prevents left/right/up/down from firing panel actions
        # behind the overlay while the user is navigating settings.
        if isinstance(self.screen, SettingsScreen):
            return

        key = event.key

        if key == "question_mark":
            self.push_screen(HelpScreen())
            return

        if key == "q":
            self.exit()

        elif key == "escape":
            # Clear panel focus if any, otherwise quit
            if self._focused_panel != 0:
                self._set_focus(0)
            else:
                self.exit()

        # ── Panel focus: number keys 1-6 ──────────────────────────────────────
        elif key in ("1", "2", "3", "4", "5", "6"):
            self._set_focus(int(key))

        elif key == "0":
            self._set_focus(0)

        # ── Tab: cycle focused panels (1→2→3→…→6→1) ──────────────────────────
        elif key == "tab":
            n = self._focused_panel
            if n == 0:
                self._set_focus(1)
            else:
                self._set_focus((n % 6) + 1)

        elif key == "shift+tab":
            n = self._focused_panel
            if n == 0:
                self._set_focus(6)
            else:
                self._set_focus(((n - 2) % 6) + 1)

        # ── Left/Right: cycle situational panel modes ─────────────────────────
        elif key == "left":
            self.query_one(SituationalPanel).back_cycle()

        elif key == "right":
            self.query_one(SituationalPanel).cycle()

        # ── Up/Down: always scroll situational panel ──────────────────────────
        elif key in ("down", "j"):
            sit = self.query_one(SituationalPanel)
            if sit._active == "galaxy":
                sit.toggle_galaxy_scale()
            elif sit._active == "engineers":
                sit.eng_move(1)
            elif sit._active == "neutron":
                sit.scroll_neutron(1)
            elif sit._active == "bgs":
                sit.scroll_bgs(1)
            elif sit._active == "colonisation":
                sit.scroll_colonisation(1)
            elif sit._active == "route":
                sit.scroll_route(1)
            else:
                sit.scroll_general(1)

        elif key in ("up", "k"):
            sit = self.query_one(SituationalPanel)
            if sit._active == "galaxy":
                sit.toggle_galaxy_scale_back()
            elif sit._active == "engineers":
                sit.eng_move(-1)
            elif sit._active == "neutron":
                sit.scroll_neutron(-1)
            elif sit._active == "bgs":
                sit.scroll_bgs(-1)
            elif sit._active == "colonisation":
                sit.scroll_colonisation(-1)
            elif sit._active == "route":
                sit.scroll_route(-1)
            else:
                sit.scroll_general(-1)

        # ── PgUp/PgDn: scroll focused panel when focused, else situational ───
        elif key == "pagedown":
            if self._focused_panel != 0:
                self._scroll_focused(5)
            else:
                sit = self.query_one(SituationalPanel)
                if sit._active == "neutron":
                    sit.scroll_neutron(5)
                elif sit._active == "bgs":
                    sit.scroll_bgs(5)
                elif sit._active == "colonisation":
                    sit.scroll_colonisation(5)
                elif sit._active == "route":
                    sit.scroll_route(5)
                else:
                    sit.scroll_general(5)

        elif key == "pageup":
            if self._focused_panel != 0:
                self._scroll_focused(-5)
            else:
                sit = self.query_one(SituationalPanel)
                if sit._active == "neutron":
                    sit.scroll_neutron(-5)
                elif sit._active == "bgs":
                    sit.scroll_bgs(-5)
                elif sit._active == "colonisation":
                    sit.scroll_colonisation(-5)
                elif sit._active == "route":
                    sit.scroll_route(-5)
                else:
                    sit.scroll_general(-5)

        elif key == "home":
            n = self._focused_panel
            if n == 1:
                self.query_one(SystemPanel).jump_top()
            elif n == 2:
                self.query_one(ShipPanel).jump_top()
            elif n == 3:
                self.query_one(RoutePanel).jump_top()
            elif n == 4:
                self.query_one(BodiesPanel).jump_top()
            elif n == 5:
                self.query_one(EventLogPanel).jump_top()
            elif n == 6:
                self.query_one(ChatLogPanel).jump_top()

        elif key == "end":
            n = self._focused_panel
            if n == 1:
                self.query_one(SystemPanel).jump_bottom()
            elif n == 2:
                self.query_one(ShipPanel).jump_bottom()
            elif n == 3:
                self.query_one(RoutePanel).jump_bottom()
            elif n == 4:
                self.query_one(BodiesPanel).jump_bottom()
            elif n == 5:
                self.query_one(EventLogPanel).jump_bottom()
            elif n == 6:
                self.query_one(ChatLogPanel).jump_bottom()

        elif key == "g":
            with self._lock:
                self._state.chat_tts_muted = not self._state.chat_tts_muted

        elif key == "t":
            with self._lock:
                self._state.twitch_tts_muted = not self._state.twitch_tts_muted

        elif key == "y":
            with self._lock:
                self._state.youtube_tts_muted = not self._state.youtube_tts_muted

        elif key == "p":
            with self._lock:
                # If all three are muted → unmute all; otherwise mute all.
                all_muted = (
                    self._state.chat_tts_muted
                    and self._state.twitch_tts_muted
                    and self._state.youtube_tts_muted
                )
                self._state.chat_tts_muted    = not all_muted
                self._state.twitch_tts_muted  = not all_muted
                self._state.youtube_tts_muted = not all_muted

        elif key == "s":
            if self._cfg is not None:
                self.push_screen(SettingsScreen(self._cfg))
            return

        elif key == "a":
            self.query_one(SituationalPanel).toggle_auto_lock()

        elif key == "m":
            with self._vol_lock:
                with self._lock:
                    if self._state.muted:
                        # Unmute: restore pre-mute volume
                        self._volume[0] = self._state.pre_mute_volume
                        self._state.volume = self._volume[0]
                        self._state.muted = False
                    else:
                        # Mute: save current volume, set to 0
                        self._state.pre_mute_volume = self._volume[0]
                        self._state.muted = True
                        self._volume[0] = 0
                        self._state.volume = 0

        elif key in ("plus", "equal", "+", "="):
            with self._vol_lock:
                with self._lock:
                    if self._state.muted:
                        # Unmute on volume-up
                        self._state.muted = False
                        self._state.pre_mute_volume = self._volume[0]
                    self._volume[0] = min(self._volume[0] + 5, 100)
                    self._state.volume = self._volume[0]

        elif key in ("minus", "-"):
            with self._vol_lock:
                with self._lock:
                    self._volume[0] = max(self._volume[0] - 5, 0)
                    self._state.volume = self._volume[0]

        elif key == "enter":
            sit = self.query_one(SituationalPanel)
            if sit._active == "engineers":
                if sit._eng_detail:
                    sit.eng_back()
                else:
                    sit.eng_select()

        elif key == "n":
            # Open neutron route input screen
            sit = self.query_one(SituationalPanel)
            if sit._active == "neutron" or sit._mode == "neutron":
                with self._lock:
                    cur = self._state.system
                self.push_screen(NeutronInputScreen(self._neutron_q, cur))
