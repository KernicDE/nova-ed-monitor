"""Ensure all ed_monitor modules parse without syntax errors."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_PKG = Path(__file__).parent.parent / "ed_monitor"
_MODULES = sorted(_PKG.rglob("*.py"))


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.relative_to(_PKG.parent).as_posix())
def test_syntax(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    ast.parse(src, filename=str(path))


def test_import_package() -> None:
    """Full package import must succeed (catches missing deps at import time)."""
    import ed_monitor  # noqa: F401
