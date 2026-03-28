from __future__ import annotations

import threading
import time
from pathlib import Path

from .config import Config
from .state import AppState


def monitor(state: AppState, lock: threading.RLock, cfg: Config) -> None:
    """Writes individual .txt files to the overlay directory for OBS/Streamlabs.

    Each file contains exactly one piece of game state.  OBS Text (GDI+) sources
    can reference these files directly and update live as the game progresses.

    Files written to overlay_dir (default: ~/.config/nova/overlay/):
      commander.txt       — Commander name
      ship_name.txt       — Ship name
      ship_type.txt       — Ship type (e.g. "Krait Phantom")
      ship_ident.txt      — Ship call sign / identifier
      system.txt          — Current star system
      position.txt        — Station / approach body / "Deep Space"
      station.txt         — Docked station name (empty when not docked)
      approach_body.txt   — Body currently being approached (empty otherwise)
      route_destination.txt — Final route destination (empty if no route)
      route_next.txt      — Next jump target (empty if no route)
      jumps_left.txt      — Remaining route jumps (empty when 0)
      hull.txt            — Hull integrity percentage (e.g. "98%")
      fuel.txt            — Current fuel in tonnes (e.g. "28.4 t")
      fuel_max.txt        — Max fuel capacity (e.g. "32 t")
      fuel_reservoir.txt  — Fuel reservoir level in tonnes
      cargo.txt           — Cargo load / capacity (e.g. "12/64 t")
      heat.txt            — Ship heat level percentage
      shields.txt         — Shield status: "UP" or "DOWN"
      status.txt          — Flight status label (DOCKED/LANDED/SUPERCRUISE/…)
      supercruise.txt     — "1" if in supercruise, else "0"
      docked.txt          — "1" if docked, else "0"
      landed.txt          — "1" if landed on surface, else "0"
      power.txt           — Power Play controlling power (empty if none)
      power_state.txt     — Power Play state (e.g. "Exploited")
      allegiance.txt      — System allegiance
      economy.txt         — System economy type
      security.txt        — System security level
      government.txt      — System government type
      population.txt      — System population (formatted), "Uninhabited" if 0
      nearest_inhabited.txt — Nearest inhabited system when in uninhabited space
      heading.txt         — Compass heading in degrees (empty if unavailable)
      altitude.txt        — Altitude in metres (empty if unavailable)
      coordinates.txt     — Lat/lon coordinates (empty if unavailable)
    """
    overlay_path = Path(cfg.overlay_dir).expanduser()
    try:
        overlay_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    last_values: dict[str, str] = {}

    while True:
        try:
            with lock:
                on_foot = not state.in_main_ship and not state.in_srv
                if not state.client_online:
                    status_label = "OFFLINE"
                elif state.supercruise and state.in_main_ship:
                    status_label = "SUPERCRUISE"
                elif state.docked:
                    status_label = "DOCKED"
                elif state.landed or (state.in_srv and not state.in_main_ship):
                    status_label = "LANDED"
                elif on_foot:
                    status_label = "ON FOOT"
                elif state.in_main_ship:
                    status_label = "FLYING"
                else:
                    status_label = ""

                position = (
                    state.station       or
                    state.approach_body or
                    state.target_body   or
                    state.nearest_body  or
                    "Deep Space"
                )

                values: dict[str, str] = {
                    "commander":          state.commander   or "",
                    "ship_name":          state.ship_name   or "",
                    "ship_type":          state.ship_type   or "",
                    "ship_ident":         state.ship_ident  or "",
                    "system":             state.system      or "",
                    "position":           position,
                    "station":            state.station     or "",
                    "approach_body":      state.approach_body or "",
                    "route_destination":  state.route_destination or "",
                    "route_next":         state.route_next  or "",
                    "jumps_left":         str(state.route_hops) if state.route_hops > 0 else "",
                    "hull":               f"{round(state.hull * 100)}%",
                    "fuel":               f"{state.fuel:.1f} t" if state.fuel > 0 else "",
                    "fuel_max":           f"{state.fuel_max:.0f} t" if state.fuel_max > 0 else "",
                    "fuel_reservoir":     f"{state.fuel_reservoir:.2f} t" if state.fuel_reservoir > 0 else "",
                    "cargo":              (
                        f"{state.cargo}/{state.cargo_capacity} t"
                        if state.cargo_capacity > 0
                        else (str(state.cargo) if state.cargo > 0 else "")
                    ),
                    "heat":               f"{round(state.heat * 100)}%" if state.heat > 0 else "",
                    "shields":            "UP" if state.shields_up else "DOWN",
                    "status":             status_label,
                    "supercruise":        "1" if state.supercruise else "0",
                    "docked":             "1" if state.docked else "0",
                    "landed":             "1" if state.landed else "0",
                    "power":              state.system_power or "",
                    "power_state":        state.system_power_state or "",
                    "allegiance":         state.allegiance  or "",
                    "economy":            state.economy     or "",
                    "security":           state.security    or "",
                    "government":         state.government  or "",
                    "population":         (
                        f"{state.population:,}".replace(",", "\u202F")
                        if state.population > 0
                        else "Uninhabited"
                    ),
                    "nearest_inhabited":  (
                        f"{state.nearest_populated_name} ({state.nearest_populated_dist:.0f} ly)"
                        if state.nearest_populated_name and state.population == 0
                        else ""
                    ),
                    "heading":            f"{state.heading:.0f}°" if state.heading is not None else "",
                    "altitude":           f"{state.altitude:.0f} m" if state.altitude is not None else "",
                    "coordinates":        (
                        f"{state.lat:.4f}, {state.lon:.4f}"
                        if state.lat is not None and state.lon is not None
                        else ""
                    ),
                }

            for name, val in values.items():
                if last_values.get(name) != val:
                    try:
                        (overlay_path / f"{name}.txt").write_text(val, encoding="utf-8")
                    except OSError:
                        pass
                    last_values[name] = val

        except Exception:
            pass

        time.sleep(1.0)
