"""Central debug logging setup for NOVA.

Call setup() once at startup (before threads are spawned) when debug_log = true
is set in config.toml.  All nova.* loggers propagate to the 'nova' parent and
are written to ~/.config/nova/nova-debug.log.
"""
from __future__ import annotations

import logging
from pathlib import Path


def setup(enabled: bool, config_dir: Path) -> None:
    """Configure the 'nova' parent logger.

    When enabled, writes DEBUG+ to <config_dir>/nova-debug.log (overwritten
    each session so the file always reflects the latest run).
    When disabled, a NullHandler is attached so missing-handler warnings
    are suppressed.
    """
    nova = logging.getLogger("nova")
    if not enabled:
        nova.addHandler(logging.NullHandler())
        return

    log_path = config_dir / "nova-debug.log"
    handler = logging.FileHandler(str(log_path), mode="w", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(name)-24s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    nova.setLevel(logging.DEBUG)
    nova.addHandler(handler)
    nova.propagate = False

    # Re-enable propagation on the audio logger so TTS debug lines also
    # appear in the combined debug log (they always go to nova-audio-debug.log
    # regardless; propagating adds them to nova-debug.log as well).
    logging.getLogger("nova.audio").propagate = True
