"""Settings overlay screen for NOVA TUI (issue #97).

Shows a scrollable list of settings rows. Navigate with ↑/↓.
Toggle/select values with ← / →. Text values with Enter to edit.
ESC cancels without saving. SAVE button writes config.toml.
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

# Supported languages (must match voicelines and config validation)
_SUPPORTED_LANGS = ["en", "de", "fr", "it", "es", "pt", "ru"]


class SettingsScreen(Screen):
    """Overlay for editing NOVA settings (keybind: s)."""

    CSS = """
    SettingsScreen {
        background: rgba(10,10,10,0.93);
        align: center middle;
    }
    #settings-box {
        width: 70;
        height: auto;
        max-height: 90%;
        background: rgb(28,28,28);
        border: solid rgb(195,160,55);
        padding: 1 2;
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
    #settings-hint {
        color: rgb(100,100,100);
        margin-top: 1;
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
    """

    class Saved(Message):
        def __init__(self, cfg: "Config") -> None:
            super().__init__()
            self.cfg = cfg

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg        = cfg
        self._rows: list  = []
        self._cursor: int = 0
        self._catalog: dict = {}        # {lang: {locale: [voice_name]}}
        self._editing: bool = False     # True while an Input is active
        # Decompose the current voice for the configured tts_lang
        voice_str  = cfg.tts_voices.get(cfg.tts_lang, "")
        parts      = voice_str.split("-") if voice_str else []
        v_lang     = cfg.tts_lang
        v_locale   = parts[1] if len(parts) >= 3 else ""
        v_name     = "-".join(parts[2:]) if len(parts) >= 3 else ""
        self._voice_lang_row   = SelectRow("_voice_lang",   "Voice Language", v_lang,   _SUPPORTED_LANGS)
        self._voice_locale_row = SelectRow("_voice_locale", "Voice Locale",   v_locale, [])
        self._voice_name_row   = SelectRow("_voice_name",   "Voice Name",     v_name,   [])
        self._rows = [
            SelectRow("tts_lang",  "TTS Language",       cfg.tts_lang,  _SUPPORTED_LANGS),
            self._voice_lang_row,
            self._voice_locale_row,
            self._voice_name_row,
            TextRow("tts_rate",   "TTS Rate",             cfg.tts_rate),
            TextRow("volume",     "Volume (0-100)",        str(cfg.default_volume)),
            TextRow("notable",    "Notable Value (Cr)",    str(cfg.notable_value_threshold)),
            ToggleRow("carrier",  "Fleet Carrier Lookup",  cfg.carrier_lookup),
        ]

    def on_mount(self) -> None:
        self._fetch_catalog()
        self._render_rows()

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
        """Refresh locale and voice options from catalog based on _voice_lang_row.value."""
        lang    = self._voice_lang_row.value
        locales = sorted(self._catalog.get(lang, {}).keys())
        self._voice_locale_row.options = locales
        if self._voice_locale_row.value not in locales and locales:
            self._voice_locale_row.value = locales[0]
        self._update_voice_name_options()
        self._render_rows()

    def _update_voice_name_options(self) -> None:
        lang    = self._voice_lang_row.value
        locale  = self._voice_locale_row.value
        names   = self._catalog.get(lang, {}).get(locale, [])
        self._voice_name_row.options = names
        if self._voice_name_row.value not in names and names:
            self._voice_name_row.value = names[0]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-box"):
            yield Label("◈ NOVA Settings", id="settings-title")
            for i, row in enumerate(self._rows):
                yield Static(self._row_text(row), id=f"row-{i}", classes="setting-row")
            yield Static("[ SAVE ]", id="save-row", classes="setting-row")
            yield Label(
                "↑↓ navigate  ← → change  Enter edit text  Esc cancel",
                id="settings-hint",
            )

    def _row_text(self, row) -> str:
        label = f"{row.label}:"
        val   = f"[ {row.display_value()} ]"
        return f"{label:<28} {val}"

    def _render_rows(self) -> None:
        """Refresh all row widgets from current row data model."""
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

    def on_key(self, event: events.Key) -> None:
        if self._editing:
            return
        key = event.key
        n_rows = len(self._rows)

        if key == "escape":
            event.stop()
            self.app.pop_screen()

        elif key == "up":
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
                    self._open_text_edit(row)

    def _open_text_edit(self, row: "TextRow") -> None:
        """Mount a temporary Input widget on the current row for text editing."""
        self._editing = True
        inp = Input(value=row.value, id="text-edit-input")
        try:
            w = self.query_one(f"#row-{self._cursor}", Static)
            w.mount(inp)
            inp.focus()
        except Exception:
            self._editing = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "text-edit-input":
            row = self._rows[self._cursor]
            if isinstance(row, TextRow):
                row.value = event.value.strip() or row.value
            event.input.remove()
            self._editing = False
            self._render_rows()

    def _do_save(self) -> None:
        """Apply row values back to a Config copy and write to disk."""
        import copy as _copy
        cfg = _copy.copy(self._cfg)
        cfg.tts_voices = dict(self._cfg.tts_voices)
        # TTS Language
        tts_lang_row = self._rows[0]
        cfg.tts_lang = tts_lang_row.value
        # Voice: reconstruct full voice string from lang/locale/name
        v_lang   = self._voice_lang_row.value
        v_locale = self._voice_locale_row.value
        v_name   = self._voice_name_row.value
        if v_lang and v_locale and v_name:
            cfg.tts_voices[v_lang] = f"{v_lang}-{v_locale}-{v_name}"
        # Text rows
        for row in self._rows:
            if isinstance(row, TextRow):
                match row.key:
                    case "tts_rate":
                        cfg.tts_rate = row.value
                    case "volume":
                        try:
                            cfg.default_volume = max(0, min(100, int(row.value)))
                        except ValueError:
                            pass
                    case "notable":
                        try:
                            cfg.notable_value_threshold = int(row.value)
                        except ValueError:
                            pass
        # Toggle rows
        for row in self._rows:
            if isinstance(row, ToggleRow) and row.key == "carrier":
                cfg.carrier_lookup = row.value
        _config.save(cfg)
        self.post_message(SettingsScreen.Saved(cfg))
        self.app.pop_screen()
