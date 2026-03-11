from __future__ import annotations

import threading
import time
from pathlib import Path
from .state import AppState


def monitor(state: AppState, lock: threading.RLock) -> None:
    """
    Periodically updates stream_info.txt in the current directory with 
    game state information for stream overlays.
    """
    output_path = Path("stream_info.txt")
    last_line   = ""

    while True:
        try:
            with lock:
                ship_type = state.ship_type or "—"
                ship_name = state.ship_name or "—"
                system    = state.system    or "—"
                
                # $position_in_system (what is nearest body or POI?)
                # Priority: Station > Approach Body > Target Body > Nearest Body
                pos = "Deep Space"
                if state.station:
                    pos = state.station
                elif state.approach_body:
                    pos = state.approach_body
                elif state.target_body:
                    pos = state.target_body
                elif state.nearest_body:
                    pos = state.nearest_body
                
                # $next_route_system (if available)
                next_route = ""
                if state.route_hops > 0 and state.route_next:
                    next_route = state.route_next

                # $remaining_jumps_in_route
                remaining_hops = state.route_hops

            parts = [
                "KERNIC.NET",
                f"SHIP: {ship_name} ({ship_type})",
                f"POSITION: {system} {pos}",
            ]
            if remaining_hops > 0:
                parts.append(f"JUMPS LEFT: {remaining_hops}")
                
            line = "     ////     ".join(parts + [""]).upper()
            
            # Only write to disk if the content actually changed to avoid 
            # unnecessary SSD wear and help OBX/Streamlabs detect updates.
            if line != last_line:
                output_path.write_text(line, encoding="utf-8")
                last_line = line
                
        except Exception:
            # We don't want to crash the monitor thread on transient file errors
            pass
            
        time.sleep(1.0)
