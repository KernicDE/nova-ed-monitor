"""Settings overlay screen for NOVA TUI (issue #97).

Shows a scrollable list of settings rows. Navigate with ↑/↓.
Toggle/select values with ← / →. Text values with Enter to edit.
ESC cancels without saving (or closes the text editor if one is open).
SAVE button writes config.toml and applies changes live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _parse_voice_catalog(
    voices: list[dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """Parse edge-tts voice list into a nested catalog.

    Returns ``{lang: {locale: [voice_name, ...]}}`` where
    ``lang`` = e.g. ``"en"``, ``locale`` = e.g. ``"GB"``,
    ``voice_name`` = e.g. ``"SoniaNeural"``.
    Voices within each locale are sorted alphabetically.
    """
    catalog: dict[str, dict[str, list[str]]] = {}
    for v in voices:
        parts = v.get("ShortName", "").split("-")
        if len(parts) < 3:
            continue
        lang   = parts[0]
        locale = parts[1]
        name   = "-".join(parts[2:])  # handles multi-hyphen names
        catalog.setdefault(lang, {}).setdefault(locale, []).append(name)
    # Sort voice names within each locale
    for lang_dict in catalog.values():
        for locale in lang_dict:
            lang_dict[locale].sort()
    return catalog


@dataclass
class ToggleRow:
    """A boolean setting row (true/false), cycled with ← / →."""
    key:   str
    label: str
    value: bool

    def cycle(self, direction: int) -> None:
        self.value = not self.value

    def display_value(self) -> str:
        return "true" if self.value else "false"


@dataclass
class SelectRow:
    """A setting row with a fixed list of options, cycled with ← / →."""
    key:     str
    label:   str
    value:   str
    options: list[str]

    def cycle(self, direction: int) -> None:
        if not self.options:
            return
        idx = self.options.index(self.value) if self.value in self.options else 0
        self.value = self.options[(idx + direction) % len(self.options)]

    def display_value(self) -> str:
        return self.value


@dataclass
class TextRow:
    """A setting row with a free-text value, edited via inline Input."""
    key:   str
    label: str
    value: str

    def display_value(self) -> str:
        return self.value


# ── Screen ────────────────────────────────────────────────────────────────────

import asyncio
import threading

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, Label, Static
from textual.containers import Vertical

from .. import config as _config
from ..config import Config

_SUPPORTED_LANGS = ["en", "de", "fr", "it", "es", "pt", "ru"]
# "auto" = empty string in config (language auto-detected from message content)
_CHAT_LANGS = ["auto"] + _SUPPORTED_LANGS

# Volume options in steps of 5
_VOLUME_OPTIONS = [str(v) for v in range(0, 101, 5)]

# TTS rate options
_RATE_OPTIONS = [
    "-50%", "-40%", "-30%", "-20%", "-10%", "-5%",
    "+0%", "+5%", "+10%", "+15%", "+20%", "+30%", "+40%", "+50%",
]

_HINT_NAV  = "↑↓ navigate   ← → change   Enter edit text   Esc cancel"
_HINT_EDIT = "Enter = confirm   Esc = cancel edit"


def _snap_volume(vol: int) -> str:
    """Snap an arbitrary volume value to the nearest 5-step option."""
    snapped = str(round(max(0, min(100, vol)) / 5) * 5)
    return snapped if snapped in _VOLUME_OPTIONS else "50"


def _snap_rate(rate: str) -> str:
    """Return rate if it's in the options list, else nearest or default."""
    if rate in _RATE_OPTIONS:
        return rate
    return "+0%"


class SettingsScreen(Screen):
    """Overlay for editing NOVA settings (keybind: s)."""

    CSS = """
    SettingsScreen {
        background: rgba(10,10,10,0.93);
        align: center middle;
    }
    #settings-box {
        width: 74;
        height: 90%;
        background: rgb(28,28,28);
        border: solid rgb(195,160,55);
        padding: 1 2;
        overflow-y: auto;
    }
    #settings-title {
        color: rgb(195,160,55);
        text-style: bold;
        margin-bottom: 1;
    }
    .setting-row {
        height: 1;
        padding: 0 0;
    }
    .setting-row.focused-row {
        background: rgb(45,45,45);
    }
    #save-row {
        height: 1;
        margin-top: 1;
        color: rgb(195,160,55);
        text-style: bold;
    }
    #save-row.focused-row {
        background: rgb(195,160,55);
        color: rgb(18,18,18);
    }
    #text-edit-input {
        margin-top: 1;
    }
    #settings-hint {
        color: rgb(100,100,100);
        margin-top: 1;
    }
    """

    class Saved(Message):
        def __init__(self, cfg: "Config") -> None:
            super().__init__()
            self.cfg = cfg

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg        = cfg
        self._catalog: dict = {}    # {lang: {locale: [voice_name]}}
        self._editing: bool = False
        self._editing_row: "TextRow | None" = None
        self._cursor: int   = 0

        # Decompose current voice for the active tts_lang
        voice_str  = cfg.tts_voices.get(cfg.tts_lang, "")
        parts      = voice_str.split("-") if voice_str else []
        v_lang     = cfg.tts_lang
        v_locale   = parts[1] if len(parts) >= 3 else ""
        v_name     = "-".join(parts[2:]) if len(parts) >= 3 else ""

        self._voice_lang_row   = SelectRow("_voice_lang",   "Voice Language", v_lang,   _SUPPORTED_LANGS)
        self._voice_locale_row = SelectRow("_voice_locale", "Voice Locale",   v_locale, [])
        self._voice_name_row   = SelectRow("_voice_name",   "Voice Name",     v_name,   [])

        # chat_lang "" → "auto" for display; mapped back on save
        chat_lang_val = cfg.chat_lang if cfg.chat_lang in _SUPPORTED_LANGS else "auto"

        self._rows: list = [
            # ── TTS ──────────────────────────────────────────────────────────
            SelectRow("tts_lang",    "TTS Language",             cfg.tts_lang,               _SUPPORTED_LANGS),
            SelectRow("tts_rate",    "TTS Rate",                 _snap_rate(cfg.tts_rate),   _RATE_OPTIONS),
            SelectRow("volume",      "Volume (0–100)",            _snap_volume(cfg.default_volume), _VOLUME_OPTIONS),
            # ── Voice selection ───────────────────────────────────────────────
            self._voice_lang_row,
            self._voice_locale_row,
            self._voice_name_row,
            # ── Chat & integrations ───────────────────────────────────────────
            TextRow("twitch",        "Twitch Channel",           cfg.twitch_channel),
            TextRow("youtube",       "YouTube Channel",          cfg.youtube_channel),
            SelectRow("chat_lang",   "Chat default language",    chat_lang_val,              _CHAT_LANGS),
            ToggleRow("tts_chat",    "Chat TTS",                 cfg.tts_chat),
            ToggleRow("tts_twitch",  "Twitch TTS",               cfg.tts_twitch),
            ToggleRow("tts_youtube", "YouTube TTS",              cfg.tts_youtube),
            # ── Bodies & display ─────────────────────────────────────────────
            TextRow("notable",       "Notable Value (Cr)",       str(cfg.notable_value_threshold)),
            ToggleRow("carrier",     "Fleet Carrier Lookup",     cfg.carrier_lookup),
        ]

    # ── Textual lifecycle ────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._fetch_catalog()
        self.call_after_refresh(self._render_rows)

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("◈ NOVA Settings", id="settings-title")
            for i, row in enumerate(self._rows):
                yield Static(self._row_text(row), id=f"row-{i}", classes="setting-row")
            yield Static("[ SAVE ]", id="save-row", classes="setting-row")
            # Note: Input is mounted dynamically in _open_editor — not here,
            # so it cannot steal focus during normal navigation.
            yield Label(_HINT_NAV, id="settings-hint")

    # ── Voice catalog ────────────────────────────────────────────────────────

    def _fetch_catalog(self) -> None:
        """Fetch edge-tts voice catalog in a background thread."""
        def _worker():
            try:
                import edge_tts
                voices = asyncio.run(edge_tts.list_voices())
                self._catalog = _parse_voice_catalog(voices)
                self.call_from_thread(self._update_voice_options)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _update_voice_options(self) -> None:
        lang    = self._voice_lang_row.value
        locales = sorted(self._catalog.get(lang, {}).keys())
        self._voice_locale_row.options = locales
        if self._voice_locale_row.value not in locales and locales:
            self._voice_locale_row.value = locales[0]
        self._update_voice_name_options()
        self._render_rows()

    def _update_voice_name_options(self) -> None:
        lang   = self._voice_lang_row.value
        locale = self._voice_locale_row.value
        names  = self._catalog.get(lang, {}).get(locale, [])
        self._voice_name_row.options = names
        if self._voice_name_row.value not in names and names:
            self._voice_name_row.value = names[0]

    # ── Rendering ────────────────────────────────────────────────────────────

    def _row_text(self, row) -> str:
        label = f"{row.label}:"
        val   = row.display_value() or "(none)"
        return f"{label:<30} [ {val} ]"

    def _render_rows(self) -> None:
        n_rows = len(self._rows)
        for i, row in enumerate(self._rows):
            try:
                w = self.query_one(f"#row-{i}", Static)
                w.update(self._row_text(row))
                if i == self._cursor:
                    w.add_class("focused-row")
                else:
                    w.remove_class("focused-row")
            except Exception:
                pass
        try:
            save_w = self.query_one("#save-row", Static)
            if self._cursor == n_rows:
                save_w.add_class("focused-row")
            else:
                save_w.remove_class("focused-row")
        except Exception:
            pass
        # Scroll cursor into view
        try:
            target_id = f"#row-{self._cursor}" if self._cursor < n_rows else "#save-row"
            self.query_one(target_id).scroll_visible(animate=False)
        except Exception:
            pass

    # ── Key handling ─────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        key = event.key

        # Escape always handled first — closes editor or the whole screen.
        if key == "escape":
            event.stop()
            if self._editing:
                self._close_editor()
            else:
                self.app.pop_screen()
            return

        # Stop all navigation keys from bubbling to the main app.
        # (This prevents the situational-panel switching from firing while
        #  the settings overlay is open.)
        if key in ("up", "down", "left", "right", "enter"):
            event.stop()

        # While a TextRow Input is active, let the Input handle all other keys.
        if self._editing:
            return

        n_rows = len(self._rows)

        if key == "up":
            self._cursor = max(0, self._cursor - 1)
            self._render_rows()

        elif key == "down":
            self._cursor = min(n_rows, self._cursor + 1)
            self._render_rows()

        elif key in ("left", "right"):
            direction = +1 if key == "right" else -1
            if self._cursor < n_rows:
                row = self._rows[self._cursor]
                if hasattr(row, "cycle"):
                    row.cycle(direction)
                    if row is self._voice_lang_row:
                        self._update_voice_options()
                    elif row is self._voice_locale_row:
                        self._update_voice_name_options()
                    self._render_rows()

        elif key == "enter":
            if self._cursor == n_rows:
                self._do_save()
            elif self._cursor < n_rows:
                row = self._rows[self._cursor]
                if isinstance(row, TextRow):
                    self._open_editor(row)

    # ── Text editing ─────────────────────────────────────────────────────────

    def _open_editor(self, row: TextRow) -> None:
        """Dynamically mount an Input widget for editing the row's text value."""
        self._editing_row = row
        inp = Input(value=row.value, placeholder=f"Editing: {row.label}", id="text-edit-input")
        try:
            self.query_one("#settings-box").mount(inp, before=self.query_one("#settings-hint"))
            self._editing = True
            self.query_one("#settings-hint", Label).update(_HINT_EDIT)
            self.call_after_refresh(inp.focus)
        except Exception:
            self._editing_row = None

    def _close_editor(self) -> None:
        """Remove the Input widget without saving its value."""
        try:
            self.query_one("#text-edit-input", Input).remove()
        except Exception:
            pass
        self._editing = False
        self._editing_row = None
        try:
            self.query_one("#settings-hint", Label).update(_HINT_NAV)
        except Exception:
            pass
        self._render_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "text-edit-input":
            return
        row = self._editing_row
        if isinstance(row, TextRow):
            row.value = event.value  # allow empty string (clears the field)
        try:
            event.input.remove()
        except Exception:
            pass
        self._editing = False
        self._editing_row = None
        try:
            self.query_one("#settings-hint", Label).update(_HINT_NAV)
        except Exception:
            pass
        self._render_rows()

    # ── Save ─────────────────────────────────────────────────────────────────

    def _do_save(self) -> None:
        """Apply all row values to a Config copy, write to disk, notify app."""
        import copy as _copy
        cfg = _copy.copy(self._cfg)
        cfg.tts_voices = dict(self._cfg.tts_voices)

        for row in self._rows:
            if isinstance(row, SelectRow):
                match row.key:
                    case "tts_lang":
                        cfg.tts_lang = row.value
                    case "tts_rate":
                        cfg.tts_rate = row.value
                    case "volume":
                        try:
                            cfg.default_volume = max(0, min(100, int(row.value)))
                        except ValueError:
                            pass
                    case "chat_lang":
                        cfg.chat_lang = "" if row.value == "auto" else row.value
            elif isinstance(row, TextRow):
                match row.key:
                    case "notable":
                        try:
                            cfg.notable_value_threshold = int(row.value)
                        except ValueError:
                            pass
                    case "twitch":
                        cfg.twitch_channel = row.value
                    case "youtube":
                        cfg.youtube_channel = row.value
            elif isinstance(row, ToggleRow):
                match row.key:
                    case "carrier":
                        cfg.carrier_lookup = row.value
                    case "tts_chat":
                        cfg.tts_chat = row.value
                    case "tts_twitch":
                        cfg.tts_twitch = row.value
                    case "tts_youtube":
                        cfg.tts_youtube = row.value

        # Voice: reconstruct full voice string from lang/locale/name selections
        v_lang   = self._voice_lang_row.value
        v_locale = self._voice_locale_row.value
        v_name   = self._voice_name_row.value
        if v_lang and v_locale and v_name:
            cfg.tts_voices[v_lang] = f"{v_lang}-{v_locale}-{v_name}"

        _config.save(cfg)
        self.post_message(SettingsScreen.Saved(cfg))
        self.app.pop_screen()
