from __future__ import annotations

import copy
import queue
import threading
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static
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
            ("Tab",              "Cycle situational panel mode"),
            ("r",                "Toggle galaxy map scale (galactic ↔ regional)"),
            ("↑ / k",            "Scroll event log up"),
            ("↓ / j",            "Scroll event log down"),
            ("PgUp / PgDn",      "Scroll event log by 20 lines"),
            ("Home / g",         "Jump to latest events"),
            ("+ / =",            "Volume up"),
            ("−",                "Volume down"),
        ]:
            kb.add_row(Text(key, style=GOLD), Text(desc, style=WHITE))

        # ── Situational modes ──────────────────────────────────────────────
        sm = Table(show_header=False, show_edge=False, box=None, padding=(0, 2))
        sm.add_column(width=14)
        sm.add_column()
        for mode, desc in [
            ("Auto",        "Bio → Missions → Overview; Stats when offline"),
            ("Overview",    "System diagram, notable bodies, session stats"),
            ("Bio",         "Active bio scans with distances and bearings"),
            ("Missions",    "Active mission list"),
            ("Inventory",   "Cargo and materials"),
            ("Engineers",   "Engineer unlock progress"),
            ("Galaxy",      "Braille top-down galaxy map"),
            ("Stats",       "Persistent statistics"),
        ]:
            sm.add_row(Text(mode, style=GOLD), Text(desc, style=WHITE))

        # ── Config path ────────────────────────────────────────────────────
        cfg = Text()
        cfg.append("Linux   ", style=GOLD)
        cfg.append("~/.config/nova/config.toml\n", style=WHITE)
        cfg.append("Windows ", style=GOLD)
        cfg.append("%USERPROFILE%\\.config\\nova\\config.toml", style=WHITE)

        content = Panel(
            Group(
                header, Text(""),
                Text("Keyboard Shortcuts", style=GOLD), kb, Text(""),
                Text("Situational Panel Modes", style=GOLD), sm, Text(""),
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
    }

    EventLogPanel {
        height: 2fr;
    }

    ChatLogPanel {
        height: 1fr;
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
    ) -> None:
        super().__init__()
        self._state    = state
        self._lock     = lock
        self._volume   = volume
        self._vol_lock = vol_lock
        self._tts_q    = tts_q
        self._stop_evt = stop_evt
        self._scroll   = 0
        self._max_scroll = 0

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
            # Shallow copy is enough for most fields
            snap = copy.copy(self._state)
            # Only deep copy things that are likely to change and cause threading issues during render
            snap.events  = copy.copy(self._state.events)
            snap.bodies  = list(self._state.bodies)
            snap.bio_scans = list(self._state.bio_scans)
            # Factions, cargo, mats etc are left as references - they change rarely 
            # and the render methods treat them as read-only.
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

    def on_key(self, event: events.Key) -> None:
        key = event.key

        if key == "question_mark":
            self.push_screen(HelpScreen())
            return

        if key in ("q", "escape"):
            self.exit()

        elif key in ("down", "j"):
            self._scroll = min(self._scroll + 1, self._max_scroll)

        elif key in ("up", "k"):
            self._scroll = max(self._scroll - 1, 0)

        elif key == "pagedown":
            self._scroll = min(self._scroll + 20, self._max_scroll)

        elif key == "pageup":
            self._scroll = max(self._scroll - 20, 0)

        elif key in ("home", "g"):
            self._scroll = 0

        elif key == "tab":
            self.query_one(SituationalPanel).cycle()

        elif key == "r":
            self.query_one(SituationalPanel).toggle_galaxy_scale()

        elif key in ("plus", "equal", "+", "="):
            with self._vol_lock:
                self._volume[0] = min(self._volume[0] + 5, 100)
            with self._lock:
                self._state.volume = self._volume[0]

        elif key in ("minus", "-"):
            with self._vol_lock:
                self._volume[0] = max(self._volume[0] - 5, 0)
            with self._lock:
                self._state.volume = self._volume[0]
