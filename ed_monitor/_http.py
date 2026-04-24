"""Shared HTTP constants used by every outbound service call.

Keeps the User-Agent header in one place so an operator running EDSM/Spansh/
YouTube can identify NOVA traffic without NOVA having to agree what its own
name is across five different modules.

Also centralises recommended timeout defaults per call class. Modules should
pass one of the TIMEOUT_* constants rather than hard-coding raw numbers.
"""
from __future__ import annotations

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("nova-ed-monitor")
except Exception:  # pragma: no cover - best-effort fallback
    _VERSION = "?"

# Single canonical user-agent. Form: "nova-ed-monitor/<version> (comment)".
USER_AGENT: str = (
    f"nova-ed-monitor/{_VERSION} "
    "(Elite Dangerous companion; github.com/KernicDE/nova-ed-monitor)"
)

# Recommended timeouts per call class. Modules pick the smallest that fits.
TIMEOUT_SHORT: float = 10.0    # quick JSON lookups (Spansh stations, EDSM station list)
TIMEOUT_MEDIUM: float = 15.0   # per-system EDSM body / route submit
TIMEOUT_LONG: float = 30.0     # heavier endpoints
TIMEOUT_DUMP: float = 120.0    # streaming gzip nightly dumps
