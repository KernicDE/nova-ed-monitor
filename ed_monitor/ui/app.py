from __future__ import annotations

import copy
import queue
import threading
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, Static
from textual import events

from ..state import AppState
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
        background: rgb(18,18,18);
        align: center middle;
        padding: 2 4;
    }
    #help-static {
        width: 76;
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

        GOLD  = "bold rgb(195,160,55)"
        WHITE = "white"
        DIM   = "rgb(140,140,140)"

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
            ("Tab",              "Cycle situational panel forward"),
            ("Shift+Tab",        "Cycle situational panel backward"),
            ("a",                "Toggle auto panel switching on/off"),
            ("↑ / k",            "Scroll situational panel up"),
            ("↓ / j",            "Scroll situational panel down"),
            ("PgUp / PgDn",      "Scroll event log by 20 lines"),
            ("Home / g",         "Jump to latest events"),
            ("w / s",            "Scroll bodies panel up / down"),
            ("r",                "Toggle galaxy map scale (galactic ↔ regional)"),
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
            ("OVR / Overview",   "System diagram, notable bodies, session stats"),
            ("BIO / Biological", "Active bio scans with distances and bearings"),
            ("MAP / Galaxy Map", "Braille top-down galaxy map (r = scale toggle)"),
            ("MIS / Mission",    "Active mission list"),
            ("ENG / Engineers",  "Engineer unlock progress and rank"),
            ("BGS",              "BGS activity log"),
            ("COL / Colonisation","Construction site progress"),
            ("ROU / Route",      "Nav route with jump distances and EDSM info"),
            ("NTR / Neutron",    "Local neutron route planner (n = new route)"),
            ("WLT / Wallet",     "Credit balance, fleet, cargo, suit loadout"),
            ("INV / Inventory",  "Cargo and materials"),
            ("DKG / Docking",    "Docking pad diagram"),
            ("STS / Statistics", "Persistent session statistics"),
        ]:
            sm.add_row(Text(mode, style=GOLD), Text(desc, style=WHITE))

        # ── Config path ────────────────────────────────────────────────────
        cfg = Text()
        cfg.append("Linux   ", style=GOLD)
        cfg.append("~/.config/nova/config.toml\n", style=WHITE)
        cfg.append("Windows ", style=GOLD)
        cfg.append("%USERPROFILE%\\.config\\nova\\config.toml", style=WHITE)

        edsm_note = Text()
        edsm_note.append("Power Play state and nearest inhabited system shown in System panel.\n", style=DIM)
        edsm_note.append("Stations at next route waypoint shown in Route panel.\n", style=DIM)
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
            border_style="rgb(195,160,55)",
            padding=(1, 2),
        )
        yield Static(content, id="help-static")

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
        background: rgb(28,28,28);
        border: solid rgb(195,160,55);
        padding: 1 2;
    }
    #neutron-label {
        color: rgb(195,160,55);
        text-style: bold;
        margin-bottom: 1;
    }
    Input {
        margin-top: 1;
    }
    #neutron-hint {
        color: rgb(100,100,100);
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
        background: rgb(18,18,18);
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

    /* Focused panel: bright white border */
    .focused {
        border: heavy white;
        border-title-color: white;
    }

    FooterBar {
        height: 1;
    }
    
    /* Combat mode overrides */
    Screen.combat-mode SystemPanel,
    Screen.combat-mode ShipPanel,
    Screen.combat-mode RoutePanel,
    Screen.combat-mode BodiesPanel,
    Screen.combat-mode SituationalPanel,
    Screen.combat-mode EventLogPanel,
    Screen.combat-mode ChatLogPanel {
        border: solid rgb(185,40,40) !important;
        border-title-color: rgb(185,40,40) !important;
    }

    /* On-foot mode overrides */
    Screen.on-foot-mode SystemPanel,
    Screen.on-foot-mode ShipPanel,
    Screen.on-foot-mode RoutePanel,
    Screen.on-foot-mode BodiesPanel,
    Screen.on-foot-mode SituationalPanel,
    Screen.on-foot-mode EventLogPanel,
    Screen.on-foot-mode ChatLogPanel {
        border: solid rgb(175,85,220) !important;
        border-title-color: rgb(175,85,220) !important;
    }

    /* Analysis mode overrides */
    Screen.analysis-mode SystemPanel,
    Screen.analysis-mode ShipPanel,
    Screen.analysis-mode RoutePanel,
    Screen.analysis-mode BodiesPanel,
    Screen.analysis-mode SituationalPanel,
    Screen.analysis-mode EventLogPanel,
    Screen.analysis-mode ChatLogPanel {
        border: solid rgb(120,190,120) !important;
        border-title-color: rgb(120,190,120) !important;
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
        background: rgb(80, 0, 0);
    }

    /* High-G extreme warning flash */
    Screen.high-g-flash SystemPanel,
    Screen.high-g-flash ShipPanel,
    Screen.high-g-flash RoutePanel,
    Screen.high-g-flash BodiesPanel,
    Screen.high-g-flash SituationalPanel,
    Screen.high-g-flash EventLogPanel,
    Screen.high-g-flash ChatLogPanel {
        border: solid rgb(220,100,0) !important;
        border-title-color: rgb(220,100,0) !important;
    }

    Screen.high-g-flash {
        background: rgb(50, 20, 0);
    }

    Screen.combat-mode SystemPanel {
        border-title-color: rgb(185,40,40) !important;
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
    ) -> None:
        super().__init__()
        self._state     = state
        self._lock      = lock
        self._volume    = volume
        self._vol_lock  = vol_lock
        self._tts_q     = tts_q
        self._stop_evt  = stop_evt
        self._neutron_q = neutron_q
        self._scroll    = 0
        self._max_scroll = 0
        self._focused_panel = 0  # 0=none, 1=System, 2=Ship, 3=Route, 4=Bodies, 5=Events, 6=Chat

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
        self.set_interval(0.25, self._refresh_all)
        # Force-hide the terminal cursor (Textual hides it in the driver, but
        # some terminals / focus events can restore it; belt-and-suspenders fix)
        try:
            self._driver.write("\x1b[?25l")
            self._driver.flush()
        except Exception:
            pass

    def _snapshot(self) -> AppState:
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
        return snap

    def _refresh_all(self) -> None:
        # Re-hide cursor every cycle (terminals may restore it on focus/resize)
        try:
            self._driver.write("\x1b[?25l")
            self._driver.flush()
        except Exception:
            pass
        snap = self._snapshot()
        self._max_scroll = max(0, len(snap.events) - 1)
        self._scroll     = min(self._scroll, self._max_scroll)

        # Apply mode border class to the main screen
        offline = not snap.client_online
        on_foot = not snap.in_main_ship and not snap.in_srv and not offline
        self.screen.set_class(offline, "offline-mode")
        self.screen.set_class(snap.analysis_mode and not offline, "analysis-mode")
        self.screen.set_class(not snap.analysis_mode and snap.in_main_ship and not offline, "combat-mode")
        self.screen.set_class(on_foot, "on-foot-mode")
        
        # Apply alert flash for critical heat or hull
        has_hazard = snap.overheating or (0 < snap.hull < 0.25)
        flash_on   = has_hazard and (int(time.time()) % 2 == 0)
        self.screen.set_class(flash_on, "alert-flash")

        # High-G extreme approach flash (orange; stops when landed)
        high_g_flash = (
            snap.high_g_extreme
            and not snap.landed
            and not snap.in_srv
            and (int(time.time()) % 2 == 0)
        )
        self.screen.set_class(high_g_flash, "high-g-flash")

        self.query_one(SystemPanel).update(snap)
        self.query_one(ShipPanel).update(snap)
        self.query_one(RoutePanel).update(snap)
        self.query_one(BodiesPanel).update(snap)
        self.query_one(SituationalPanel).update(snap)
        self.query_one(FooterBar).update(snap)

        log = self.query_one(EventLogPanel)
        log.update(snap)
        log.set_scroll(self._scroll)
        self.query_one(ChatLogPanel).update(snap)

    def on_unmount(self) -> None:
        if self._stop_evt is not None:
            self._stop_evt.set()

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

        # ── Up/Down: scroll focused panel or situational panel ────────────────
        elif key in ("down", "j"):
            if self._focused_panel in (4, 5, 6):
                self._scroll_focused(1)
            else:
                sit = self.query_one(SituationalPanel)
                if sit._active == "neutron":
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
            if self._focused_panel in (4, 5, 6):
                self._scroll_focused(-1)
            else:
                sit = self.query_one(SituationalPanel)
                if sit._active == "neutron":
                    sit.scroll_neutron(-1)
                elif sit._active == "bgs":
                    sit.scroll_bgs(-1)
                elif sit._active == "colonisation":
                    sit.scroll_colonisation(-1)
                elif sit._active == "route":
                    sit.scroll_route(-1)
                else:
                    sit.scroll_general(-1)

        elif key == "pagedown":
            if self._focused_panel in (4, 5, 6):
                self._scroll_focused(5)
            else:
                self._scroll = min(self._scroll + 20, self._max_scroll)

        elif key == "pageup":
            if self._focused_panel in (4, 5, 6):
                self._scroll_focused(-5)
            else:
                self._scroll = max(self._scroll - 20, 0)

        elif key in ("home", "g"):
            self._scroll = 0

        elif key == "s":
            self.query_one(BodiesPanel).scroll_bodies(1)

        elif key == "w":
            self.query_one(BodiesPanel).scroll_bodies(-1)

        elif key == "a":
            self.query_one(SituationalPanel).toggle_auto_lock()

        elif key == "r":
            self.query_one(SituationalPanel).toggle_galaxy_scale()

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

        elif key == "n":
            # Open neutron route input screen
            sit = self.query_one(SituationalPanel)
            if sit._active == "neutron" or sit._mode == "neutron":
                with self._lock:
                    cur = self._state.system
                self.push_screen(NeutronInputScreen(self._neutron_q, cur))
