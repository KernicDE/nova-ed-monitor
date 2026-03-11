from __future__ import annotations

import threading
import time
from pathlib import Path

from .config import Config
from .state import AppState


def monitor(state: AppState, lock: threading.RLock, cfg: Config) -> None:
    """Periodically writes stream_info.txt (or configured path) with game state.

    The output format is fully configurable via overlay_line_N keys in config.toml.
    Each line is formatted as a Python str.format_map() template with variables:

      {commander}  {ship_name}  {ship_type}  {system}   {position}
      {jumps_left} {route_next} {hull_pct}   {fuel_t}   {fuel_max_t}

    Lines containing {jumps_left} are skipped when jumps_left == 0.
    Lines containing {route_next} are skipped when route_next is empty.
    """
    output_path = Path(cfg.overlay_path)
    segments    = cfg.overlay_segments
    separator   = cfg.overlay_separator
    uppercase   = cfg.overlay_uppercase
    last_text   = ""

    while True:
        try:
            with lock:
                # Collect all variables
                position = (
                    state.station      or
                    state.approach_body or
                    state.target_body   or
                    state.nearest_body  or
                    "Deep Space"
                )
                vars_map = {
                    "commander":   state.commander   or "—",
                    "ship_name":   state.ship_name   or "—",
                    "ship_type":   state.ship_type   or "—",
                    "system":      state.system      or "—",
                    "position":    position,
                    "jumps_left":  state.route_hops,
                    "route_next":  state.route_next  or "",
                    "hull_pct":    f"{round(state.hull * 100)}%",
                    "fuel_t":      f"{state.fuel:.1f}t" if state.fuel > 0 else "—",
                    "fuel_max_t":  f"{state.fuel_max:.0f}t" if state.fuel_max > 0 else "—",
                }

            parts = []
            for template in segments:
                # Skip segments whose key variable is empty/zero
                if "{jumps_left}" in template and vars_map["jumps_left"] == 0:
                    continue
                if "{route_next}" in template and not vars_map["route_next"]:
                    continue
                try:
                    rendered = template.format_map(vars_map)
                except (KeyError, ValueError):
                    rendered = template  # show raw if format fails
                if rendered:
                    parts.append(rendered)

            text = separator.join(parts) + separator
            if uppercase:
                text = text.upper()

            if text != last_text:
                output_path.write_text(text, encoding="utf-8")
                last_text = text

        except Exception:
            pass

        time.sleep(1.0)
