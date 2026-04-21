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
