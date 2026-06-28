# Settings Overlay TUI + Config File Monitoring (Issue #97) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a keyboard-accessible settings overlay to the NOVA TUI and a background watcher that hot-reloads config and voicelines files when they change on disk.

**Architecture:** A new `SettingsScreen` (Textual `Screen` subclass, same pattern as `HelpScreen` and `NeutronInputScreen`) lives in a new file `ed_monitor/ui/settings_screen.py`. It fetches the edge-tts voice catalog once on mount, renders a scrollable list of setting rows, and writes back to `config.toml` on SAVE. A new daemon thread (`config_watcher.py`) uses the `watchdog` package (already a dependency) to watch `~/.config/nova/` for file changes and calls reload callbacks. Key `s` opens the overlay in `NOVAApp`.

**Tech Stack:** Textual (widgets: `Screen`, `Input`, `Label`, `Static`), `edge_tts.list_voices()` (async, run in thread), `watchdog` (already used in `journal.py`), Python 3.11+.

---

## File Map

| File | Change |
|------|--------|
| `ed_monitor/config.py` | Add `save(cfg, path)` function |
| `ed_monitor/ui/settings_screen.py` | **Create** — `SettingsScreen`, row widgets, voice catalog helper |
| `ed_monitor/ui/app.py` | Add `s` keybind, import + push `SettingsScreen` |
| `ed_monitor/config_watcher.py` | **Create** — daemon thread watching config/voiceline files |
| `ed_monitor/__main__.py` | Spawn `config_watcher` thread |
| `tests/test_config_save.py` | New — unit tests for `config.save()` |
| `tests/test_settings_screen.py` | New — unit tests for row logic and voice catalog parsing |

---

## Design: Settings Rows

The overlay shows these rows (in order), navigated with ↑/↓:

```
TTS Language:          [  en  ]   ← select: en de fr it es pt ru
Voice Language:        [  en  ]   ← which lang's voice to configure (same options)
Voice Locale:          [  GB  ]   ← filtered locales for selected Voice Language
Voice Name:            [ SoniaNeural ]  ← filtered voices for selected locale
TTS Rate:              [ +10% ]   ← text input
Volume:                [  50  ]   ← text input (0–100)
Notable Value (Cr):    [ 500000 ] ← text input
Fleet Carrier Lookup:  [ false ]  ← toggle: true/false
                       [ SAVE ]   ← button row
```

- `[value]` cells cycle left/right with ← / →.
- Text rows open an inline `Input` widget on Enter, confirmed with Enter, cancelled with Escape.
- ESC when no text input is focused cancels the whole overlay (no write).
- SAVE writes to `config.toml` and live-reloads running state.

## Design: Voice Catalog

`edge_tts.list_voices()` is an `async` coroutine. Run it once at screen mount via `asyncio.run()` in a thread, then populate the select options. Example voice entry:
```json
{"ShortName": "en-GB-SoniaNeural", "LocalName": "Sonia", "Gender": "Female"}
```
Parse: `lang = "en"`, `locale = "GB"`, `voice_name = "SoniaNeural"`.
Build: `catalog: dict[str, dict[str, list[str]]]` → `{"en": {"GB": ["SoniaNeural", ...], "US": [...]}, "de": {...}}`.

## Design: Config Save

`config.py` uses a hand-rolled k=v parser (not standard TOML). The `save()` function **rewrites the file** using the `DEFAULT_CONFIG` template structure but with active values interpolated. This intentionally does not preserve arbitrary user comments, but does preserve the comment structure of the default template (explaining each setting). This is the simplest correct approach.

---

### Task 1: Add `config.save()` function

**Files:**
- Modify: `ed_monitor/config.py`
- Create: `tests/test_config_save.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_save.py`:

```python
"""Tests for config.save() — writes Config back to a TOML-like file."""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from ed_monitor.config import Config, save, load


def _dummy_cfg(**overrides) -> Config:
    base = Config(
        journal_dir=Path("/tmp/journals"),
        tts_lang="en",
        tts_rate="+10%",
        default_volume=50,
        notable_value_threshold=500_000,
        carrier_lookup=False,
    )
    for k, v in overrides.items():
        object.__setattr__(base, k, v)
    return base


class TestConfigSave:
    def test_save_creates_file(self, tmp_path):
        cfg = _dummy_cfg()
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert path.exists()

    def test_save_roundtrips_tts_lang(self, tmp_path):
        cfg = _dummy_cfg(tts_lang="de")
        path = tmp_path / "config.toml"
        save(cfg, path)
        text = path.read_text()
        assert "tts_lang = de" in text

    def test_save_roundtrips_volume(self, tmp_path):
        cfg = _dummy_cfg(default_volume=75)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "default_volume = 75" in path.read_text()

    def test_save_roundtrips_tts_rate(self, tmp_path):
        cfg = _dummy_cfg(tts_rate="-5%")
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "tts_rate = -5%" in path.read_text()

    def test_save_roundtrips_carrier_lookup_true(self, tmp_path):
        cfg = _dummy_cfg(carrier_lookup=True)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "carrier_lookup = true" in path.read_text()

    def test_save_roundtrips_tts_voice(self, tmp_path):
        cfg = _dummy_cfg()
        cfg.tts_voices["en"] = "en-US-GuyNeural"
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "tts_voice_en = en-US-GuyNeural" in path.read_text()

    def test_save_roundtrips_notable_value(self, tmp_path):
        cfg = _dummy_cfg(notable_value_threshold=1_000_000)
        path = tmp_path / "config.toml"
        save(cfg, path)
        assert "notable_value_threshold = 1000000" in path.read_text()
```

- [ ] **Step 2: Run to confirm failure**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_config_save.py -v
```

Expected: `FAILED` — `ImportError: cannot import name 'save' from 'ed_monitor.config'`

- [ ] **Step 3: Add `save()` to config.py**

Add at the end of `ed_monitor/config.py` (after all existing functions):

```python
def save(cfg: "Config", path: "Path | None" = None) -> None:
    """Write *cfg* back to *path* (default: ``~/.config/nova/config.toml``).

    Produces a minimal k=v file containing only the settings supported by the
    Settings overlay. Preserves no user comments; existing content is replaced.
    """
    if path is None:
        path = config_dir() / "config.toml"

    lines: list[str] = [
        "# NOVA — saved by Settings overlay\n",
        "\n",
    ]

    if cfg.journal_dir:
        lines.append(f"journal_dir = {cfg.journal_dir}\n")
    if cfg.twitch_channel:
        lines.append(f"twitch_channel = {cfg.twitch_channel}\n")
    if cfg.youtube_channel:
        lines.append(f"youtube_channel = {cfg.youtube_channel}\n")

    lines.append(f"tts_lang = {cfg.tts_lang}\n")
    lines.append(f"tts_rate = {cfg.tts_rate}\n")

    for lang, voice in cfg.tts_voices.items():
        lines.append(f"tts_voice_{lang} = {voice}\n")

    lines.append(f"default_volume = {cfg.default_volume}\n")
    lines.append(f"notable_value_threshold = {cfg.notable_value_threshold}\n")
    lines.append(f"carrier_lookup = {'true' if cfg.carrier_lookup else 'false'}\n")

    if cfg.debug_log:
        lines.append("debug_log = true\n")
    if cfg.screenshot_dir:
        lines.append(f"screenshot_dir = {cfg.screenshot_dir}\n")
    if cfg.screenshot_dest:
        lines.append(f"screenshot_dest = {cfg.screenshot_dest}\n")
    if cfg.chat_lang:
        lines.append(f"chat_lang = {cfg.chat_lang}\n")
    if cfg.situational_panels:
        _mode_to_abbrev = {
            "overview": "OVR", "bio": "BIO", "galaxy": "MAP",
            "missions": "MIS", "engineers": "ENG", "bgs": "BGS",
            "colonisation": "COL", "route": "ROU", "neutron": "NTR",
            "wealth": "WLT", "inventory": "INV", "docking": "DKG", "stats": "STS",
        }
        abbrevs = " ".join(_mode_to_abbrev.get(m, m.upper()) for m in cfg.situational_panels)
        lines.append(f"situational_panels = {abbrevs}\n")

    try:
        path.write_text("".join(lines), encoding="utf-8")
    except OSError:
        pass
```

- [ ] **Step 4: Run tests**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_config_save.py -v
```

Expected: All 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/config.py tests/test_config_save.py
git commit -m "feat: add config.save() for Settings overlay write-back"
```

---

### Task 2: Voice catalog helper

**Files:**
- Create: `ed_monitor/ui/settings_screen.py` (just the catalog helper for now)
- Create: `tests/test_settings_screen.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_screen.py`:

```python
"""Tests for SettingsScreen helpers — voice catalog and row logic."""
from __future__ import annotations

import pytest
from ed_monitor.ui.settings_screen import _parse_voice_catalog


class TestParseCatalog:
    def test_basic_parsing(self):
        voices = [
            {"ShortName": "en-GB-SoniaNeural"},
            {"ShortName": "en-US-GuyNeural"},
            {"ShortName": "de-DE-KatjaNeural"},
        ]
        catalog = _parse_voice_catalog(voices)
        assert "en" in catalog
        assert "GB" in catalog["en"]
        assert "SoniaNeural" in catalog["en"]["GB"]
        assert "US" in catalog["en"]
        assert "GuyNeural" in catalog["en"]["US"]
        assert "de" in catalog
        assert "DE" in catalog["de"]
        assert "KatjaNeural" in catalog["de"]["DE"]

    def test_voices_sorted(self):
        voices = [
            {"ShortName": "en-GB-ZoeNeural"},
            {"ShortName": "en-GB-AbbieNeural"},
            {"ShortName": "en-GB-SoniaNeural"},
        ]
        catalog = _parse_voice_catalog(voices)
        assert catalog["en"]["GB"] == ["AbbieNeural", "SoniaNeural", "ZoeNeural"]

    def test_empty_input(self):
        assert _parse_voice_catalog([]) == {}

    def test_malformed_short_name_skipped(self):
        voices = [{"ShortName": "en-GB"}]  # only 2 parts, not 3
        catalog = _parse_voice_catalog(voices)
        assert catalog == {}
```

- [ ] **Step 2: Run to confirm failure**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_settings_screen.py::TestParseCatalog -v
```

Expected: `FAILED` — `ImportError`

- [ ] **Step 3: Create `ed_monitor/ui/settings_screen.py` with catalog helper**

```python
"""Settings overlay screen for NOVA TUI (issue #97).

Shows a scrollable list of settings rows. Navigate with ↑/↓.
Toggle/select values with ← / →. Text values with Enter to edit.
ESC cancels without saving. SAVE button writes config.toml.
"""
from __future__ import annotations

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
```

- [ ] **Step 4: Run tests**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_settings_screen.py::TestParseCatalog -v
```

Expected: All 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/ui/settings_screen.py tests/test_settings_screen.py
git commit -m "feat: add voice catalog helper for settings overlay"
```

---

### Task 3: SettingsScreen — row data model and navigation

**Files:**
- Modify: `ed_monitor/ui/settings_screen.py`
- Modify: `tests/test_settings_screen.py`

- [ ] **Step 1: Write failing tests for row model**

Append to `tests/test_settings_screen.py`:

```python
from ed_monitor.ui.settings_screen import ToggleRow, TextRow, SelectRow


class TestToggleRow:
    def test_cycle_right(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", False)
        row.cycle(+1)
        assert row.value is True

    def test_cycle_wraps(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", True)
        row.cycle(+1)
        assert row.value is False

    def test_display(self):
        row = ToggleRow("carrier_lookup", "Fleet Carrier Lookup", True)
        assert row.display_value() == "true"


class TestSelectRow:
    def test_cycle_right(self):
        row = SelectRow("tts_lang", "TTS Language", "en", ["en", "de", "fr"])
        row.cycle(+1)
        assert row.value == "de"

    def test_cycle_wraps_at_end(self):
        row = SelectRow("tts_lang", "TTS Language", "fr", ["en", "de", "fr"])
        row.cycle(+1)
        assert row.value == "en"

    def test_cycle_left(self):
        row = SelectRow("tts_lang", "TTS Language", "de", ["en", "de", "fr"])
        row.cycle(-1)
        assert row.value == "en"


class TestTextRow:
    def test_initial_value(self):
        row = TextRow("tts_rate", "TTS Rate", "+10%")
        assert row.value == "+10%"

    def test_set_value(self):
        row = TextRow("tts_rate", "TTS Rate", "+10%")
        row.value = "-5%"
        assert row.value == "-5%"
```

- [ ] **Step 2: Run to confirm failure**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_settings_screen.py::TestToggleRow tests/test_settings_screen.py::TestSelectRow tests/test_settings_screen.py::TestTextRow -v
```

Expected: `FAILED` — `ImportError: cannot import name 'ToggleRow'`

- [ ] **Step 3: Add row data classes to `settings_screen.py`**

Add after `_parse_voice_catalog()`:

```python
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run the row tests**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_settings_screen.py -v
```

Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/ui/settings_screen.py tests/test_settings_screen.py
git commit -m "feat: add settings row data classes (ToggleRow, SelectRow, TextRow)"
```

---

### Task 4: SettingsScreen — full Textual Screen implementation

**Files:**
- Modify: `ed_monitor/ui/settings_screen.py`

This task has no unit tests (Textual screens require a full app runner). Manual testing instructions are in Step 5.

- [ ] **Step 1: Add `SettingsScreen` class to `settings_screen.py`**

Append the full screen implementation to `ed_monitor/ui/settings_screen.py`:

```python
import asyncio
import threading
from typing import Optional

from textual import events
from textual.app import ComposeResult
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
            TextRow("volume",     "Volume (0–100)",        str(cfg.default_volume)),
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
                # Update locale/voice options for current voice_lang
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
        # Update save-row focus
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
            return  # Input widget handles keys while editing
        key = event.key
        n_rows = len(self._rows)

        if key == "escape":
            event.stop()
            self.app.pop_screen()

        elif key == "up":
            self._cursor = max(0, self._cursor - 1)
            self._render_rows()

        elif key == "down":
            self._cursor = min(n_rows, self._cursor + 1)  # n_rows = SAVE row
            self._render_rows()

        elif key in ("left", "right"):
            direction = +1 if key == "right" else -1
            if self._cursor < n_rows:
                row = self._rows[self._cursor]
                if hasattr(row, "cycle"):
                    row.cycle(direction)
                    # Cascade voice option updates
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
        # Mount over the current row widget
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

    def on_input_key(self, event) -> None:
        pass  # handled by Textual's Input widget

    def _do_save(self) -> None:
        """Apply row values back to a Config copy and write to disk."""
        cfg = self._cfg
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
        self.app.pop_screen()
```

- [ ] **Step 2: Run syntax test**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_syntax.py -v
```

Expected: All PASSED (syntax test covers all `.py` files).

- [ ] **Step 3: Commit**

```bash
git add ed_monitor/ui/settings_screen.py
git commit -m "feat: add SettingsScreen TUI overlay (issue #97)"
```

---

### Task 5: Wire SettingsScreen into NOVAApp

**Files:**
- Modify: `ed_monitor/ui/app.py`

- [ ] **Step 1: Add import and keybind**

In `ed_monitor/ui/app.py`, add the import near the other local imports at the top:

```python
from .settings_screen import SettingsScreen
```

In `NOVAApp.on_key()`, add a handler for the `s` key. Insert after the `question_mark` block (around line 531):

```python
        if key == "question_mark":
            self.push_screen(HelpScreen())
            return

        if key == "s":
            import copy as _copy
            with self._lock:
                cfg_copy = _copy.deepcopy(self._state._cfg) if hasattr(self._state, '_cfg') else None
            # Pass a snapshot of the current config to the overlay
            # We need the Config object — store it on NOVAApp at __init__
            self.push_screen(SettingsScreen(self._cfg))
            return
```

Also store `cfg` on `NOVAApp.__init__`. Add `cfg: Config` parameter and store it:

In `NOVAApp.__init__`, add `cfg` as a new parameter before `state`:

```python
    def __init__(
        self,
        cfg:      "Config",          # ← add this
        state:    AppState,
        lock:     threading.RLock,
        volume:   list[int],
        vol_lock: threading.Lock,
        tts_q:    queue.Queue,
        stop_evt: threading.Event | None = None,
        neutron_q: queue.Queue | None = None,
    ) -> None:
        super().__init__()
        self._cfg       = cfg          # ← add this
        self._state     = state
        # ... rest unchanged
```

In `__main__.py`, update the `NOVAApp(...)` call to pass `cfg` first:

```python
    NOVAApp(cfg, state, lock, volume, vol_lock, tts_q, stop_evt, neutron_q).run()
```

After SAVE in `SettingsScreen._do_save()`, the app needs to apply the new config live. Add a message dispatch at the end of `_do_save()`:

```python
        _config.save(cfg)
        self.app.post_message(SettingsScreen.Saved(cfg))
        self.app.pop_screen()
```

Add the message class to `SettingsScreen`:

```python
    class Saved(Message):
        def __init__(self, cfg: "Config") -> None:
            super().__init__()
            self.cfg = cfg
```

Add `from textual.message import Message` to the imports in `settings_screen.py`.

Handle the message in `NOVAApp`:

```python
    def on_settings_screen_saved(self, event: "SettingsScreen.Saved") -> None:
        """Apply live-reloadable settings from the overlay."""
        cfg = event.cfg
        self._cfg = cfg
        from . import events as _ev
        _ev.set_tts_lang(cfg.tts_lang)
        _ev.set_voices(cfg.tts_voices)
        with self._lock:
            self._state.volume               = cfg.default_volume
            self._state.notable_value_threshold = cfg.notable_value_threshold
        from .. import voicelines as _vl
        _vl.reload_all()
```

- [ ] **Step 2: Run syntax test**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_syntax.py -v
```

Expected: All PASSED.

- [ ] **Step 3: Manual smoke test**

Launch NOVA (`python -m ed_monitor` from the project root), press `s`. The overlay should appear with settings rows. Navigate with ↑/↓, change a toggle with ←/→, press SAVE. Verify `~/.config/nova/config.toml` was updated.

- [ ] **Step 4: Commit**

```bash
git add ed_monitor/ui/app.py ed_monitor/ui/settings_screen.py ed_monitor/__main__.py
git commit -m "feat: wire SettingsScreen into NOVAApp with 's' keybind and live reload"
```

---

### Task 6: Config and voiceline file watcher

**Files:**
- Create: `ed_monitor/config_watcher.py`
- Modify: `ed_monitor/__main__.py`
- Modify: `tests/test_syntax.py` (automatic — syntax test discovers all .py files)

- [ ] **Step 1: Create `ed_monitor/config_watcher.py`**

```python
"""Config and voiceline file watcher for NOVA.

Watches ~/.config/nova/config.toml and ~/.config/nova/voicelines/ for changes.
When a change is detected, reloads configuration and voiceline caches.

Usage:
    spawn(state, lock, cfg_dir, on_config_changed, on_voicelines_changed)

Both callbacks are called from the watcher thread (not the main thread) while
holding *lock*. Keep them short and non-blocking.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

_log = logging.getLogger("nova.config_watcher")

_POLL_INTERVAL = 2.0  # seconds (fallback when watchdog unavailable)


def spawn(
    cfg_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> threading.Thread:
    """Start the watcher daemon thread and return it."""
    t = threading.Thread(
        target=_monitor,
        args=(cfg_dir, on_config_changed, on_voicelines_changed),
        name="nova-config-watcher",
        daemon=True,
    )
    t.start()
    return t


def _monitor(
    cfg_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    config_path   = cfg_dir / "config.toml"
    voiceline_dir = cfg_dir / "voicelines"
    changed       = threading.Event()

    # Try watchdog first, fall back to polling
    try:
        from watchdog.observers import Observer          # type: ignore[import]
        from watchdog.events import FileSystemEventHandler  # type: ignore[import]

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:       # type: ignore[override]
                changed.set()
            def on_created(self, event) -> None:        # type: ignore[override]
                changed.set()

        obs = Observer()
        obs.schedule(_Handler(), str(cfg_dir), recursive=True)
        obs.daemon = True
        obs.start()
        _log.info("Config watcher: watchdog active")

        while True:
            changed.wait()
            changed.clear()
            time.sleep(0.3)  # debounce
            _dispatch(cfg_dir, config_path, voiceline_dir,
                      on_config_changed, on_voicelines_changed)

    except Exception as exc:
        _log.warning("Config watcher: watchdog failed (%s) — polling every %.0fs", exc, _POLL_INTERVAL)
        _poll(config_path, voiceline_dir, on_config_changed, on_voicelines_changed)


def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _max_voiceline_mtime(voiceline_dir: Path) -> float:
    try:
        return max(
            (_get_mtime(p) for p in voiceline_dir.glob("*.toml")),
            default=0.0,
        )
    except OSError:
        return 0.0


def _poll(
    config_path: Path,
    voiceline_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    last_config_mtime     = _get_mtime(config_path)
    last_voiceline_mtime  = _max_voiceline_mtime(voiceline_dir)
    while True:
        time.sleep(_POLL_INTERVAL)
        cur_config    = _get_mtime(config_path)
        cur_voiceline = _max_voiceline_mtime(voiceline_dir)
        if cur_config != last_config_mtime:
            last_config_mtime = cur_config
            try:
                on_config_changed()
            except Exception:
                _log.exception("Config reload callback failed")
        if cur_voiceline != last_voiceline_mtime:
            last_voiceline_mtime = cur_voiceline
            try:
                on_voicelines_changed()
            except Exception:
                _log.exception("Voiceline reload callback failed")


def _dispatch(
    cfg_dir: Path,
    config_path: Path,
    voiceline_dir: Path,
    on_config_changed: Callable[[], None],
    on_voicelines_changed: Callable[[], None],
) -> None:
    """Called after a watchdog event — determine which file type changed."""
    # We don't get fine-grained path info from the debounced event,
    # so check both and call both callbacks if either changed.
    try:
        on_config_changed()
    except Exception:
        _log.exception("Config reload callback failed")
    try:
        on_voicelines_changed()
    except Exception:
        _log.exception("Voiceline reload callback failed")
```

- [ ] **Step 2: Wire into `__main__.py`**

In `ed_monitor/__main__.py`, add the import:

```python
from . import config_watcher
```

After the `NOVAApp(...)` construction but before `.run()`, define the reload callbacks and spawn the watcher. Insert just before the `NOVAApp(...).run()` line:

```python
    from . import events as _ev_mod, voicelines as _vl_mod

    def _on_config_changed():
        try:
            new_cfg = config.load()
            _ev_mod.set_tts_lang(new_cfg.tts_lang)
            _ev_mod.set_voices(new_cfg.tts_voices)
            _ev_mod.set_chat_lang(new_cfg.chat_lang)
            with lock:
                state.volume                  = new_cfg.default_volume
                state.notable_value_threshold = new_cfg.notable_value_threshold
        except Exception:
            pass

    def _on_voicelines_changed():
        try:
            _vl_mod.reload_all()
        except Exception:
            pass

    config_watcher.spawn(
        config.config_dir(),
        _on_config_changed,
        _on_voicelines_changed,
    )
```

- [ ] **Step 3: Run syntax test**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_syntax.py -v
```

Expected: All PASSED.

- [ ] **Step 4: Manual test**

Launch NOVA, then while it's running edit `~/.config/nova/config.toml` (change `default_volume`) and save. Within 2 seconds the change should be picked up. Edit a voiceline `.toml` file; the next TTS event for that key should use the new line.

- [ ] **Step 5: Commit**

```bash
git add ed_monitor/config_watcher.py ed_monitor/__main__.py
git commit -m "feat: watch config and voiceline files for hot-reload (#97)"
```

---

### Task 7: Version bump, push, release, close issue

- [ ] **Step 1: Update HelpScreen to mention `s` keybind**

In `ed_monitor/ui/app.py`, in `HelpScreen.compose()`, add a row for the settings keybind:

```python
("s",           "Open settings overlay"),
```

(Add it near the other single-key entries like `?` for help.)

- [ ] **Step 2: Bump version in `pyproject.toml`**

Change `version = "1.32.4"` → `version = "1.33.0"` (minor bump: new feature).

- [ ] **Step 3: Run full test suite**

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/ -v
```

Expected: All PASSED.

- [ ] **Step 4: Commit, tag, push, release**

```bash
git add pyproject.toml ed_monitor/ui/app.py
git commit -m "chore: bump to 1.33.0; document 's' keybind in help screen"
git tag v1.33.0
git push origin main v1.33.0
gh release create v1.33.0 --repo KernicDE/nova-ed-monitor \
  --title "Settings overlay TUI + config hot-reload" \
  --notes "## What's Changed

### Settings Overlay (#97)
- Press **\`s\`** to open the settings overlay from anywhere in NOVA.
- Navigate rows with ↑/↓; change toggles and selects with ←/→; edit text fields with Enter.
- Voice selection is hierarchical: language → locale → voice name (powered by edge-tts catalog).
- **ESC** closes without saving. **SAVE** writes \`~/.config/nova/config.toml\` and applies changes immediately (TTS language, voices, volume, notable-body threshold).

### Config + Voiceline Hot-Reload (#97)
- NOVA now watches \`~/.config/nova/config.toml\` and \`~/.config/nova/voicelines/\` for file changes.
- Editing config or voiceline files while NOVA is running takes effect within 2 seconds — no restart needed."
gh issue comment 97 --repo KernicDE/nova-ed-monitor \
  --body "Implemented in v1.33.0."
gh issue close 97 --repo KernicDE/nova-ed-monitor
```
