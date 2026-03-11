from __future__ import annotations

import bisect
import enum
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

MAX_EVENTS = 500


# ── Service status ─────────────────────────────────────────────────────────────

@dataclass
class ServiceStatus:
    enabled:    bool            = False
    connected:  Optional[bool]  = None
    last_tx:    Optional[str]   = None
    last_rx:    Optional[str]   = None
    last_error: Optional[str]   = None


# ── Event category ─────────────────────────────────────────────────────────────

class EventCategory(enum.Enum):
    Nav     = "NAV"
    Combat  = "COMBAT"
    Explore = "EXPLORE"
    Mission = "MISSION"
    Trade   = "TRADE"
    Status  = "STATUS"
    System  = "SYSTEM"
    Warn    = "WARN"
    Chat    = "CHAT"

    def label(self) -> str:
        return self.value

    def icon(self) -> str:
        return {
            EventCategory.Nav:     "◈",
            EventCategory.Combat:  "⚔",
            EventCategory.Explore: "◉",
            EventCategory.Mission: "◆",
            EventCategory.Trade:   "◇",
            EventCategory.Status:  "●",
            EventCategory.System:  "◈",
            EventCategory.Warn:    "⚠",
            EventCategory.Chat:    "◐",
        }[self]

    def color(self) -> tuple[int, int, int]:
        return {
            EventCategory.Nav:     (0,   175, 185),
            EventCategory.Combat:  (185, 40,  40),
            EventCategory.Explore: (0,   170, 60),
            EventCategory.Mission: (195, 150, 0),
            EventCategory.Trade:   (160, 32,  240),
            EventCategory.Status:  (60,  100, 200),
            EventCategory.System:  (128, 128, 128),
            EventCategory.Warn:    (185, 40,  40),
            EventCategory.Chat:    (0,   160, 210),
        }[self]

    def rich_color(self) -> str:
        r, g, b = self.color()
        return f"rgb({r},{g},{b})"


# ── Event log ──────────────────────────────────────────────────────────────────

@dataclass
class LogEvent:
    time:     str
    category: EventCategory
    message:  str

    @classmethod
    def new(cls, category: EventCategory, message: str) -> "LogEvent":
        return cls(
            time=datetime.now().strftime("%H:%M:%S"),
            category=category,
            message=message,
        )


# ── Body / scan data ───────────────────────────────────────────────────────────

@dataclass
class BodyInfo:
    name:             str
    body_id:          int
    level:            int    # 0=star, 1=planet, 2=moon
    planet_class:     str
    star_type:        str
    atmosphere:       str
    terraform:        bool
    landable:         bool
    bio_signals:      int
    geo_signals:      int
    bio_genuses:      list[str]
    dist_ls:          float
    value:            int
    first_discovered: bool
    first_mapped:     bool
    mapped:           bool   # True = DSS complete
    fss_scanned:      bool   # True = player FSS'd this body
    radius:           float


@dataclass
class BioScan:
    species:           str
    species_localised: str
    genus_localised:   str
    body:              str
    samples:           int
    min_dist:          float
    last_lat:          Optional[float]
    last_lon:          Optional[float]
    body_radius:       float
    current_dist:      Optional[float]
    value:             int
    alerted:           bool
    complete:          bool
    first_discovered:  bool
    sample_lats:       list  = field(default_factory=list)  # lat of each sample taken
    sample_lons:       list  = field(default_factory=list)  # lon of each sample taken
    current_bearing:   Optional[str]  = None  # compass direction away from nearest sample
    first_footfall:    bool  = False


# ── Mission ────────────────────────────────────────────────────────────────────

@dataclass
class MissionInfo:
    mission_id:  int
    name:        str
    destination: str   # "System / Station" or just system
    expiry:      str   # ISO timestamp string, "" if none


# ── App state ──────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    # System
    system:     str   = "—"
    population: int   = 0
    economy:    str   = ""
    security:   str   = ""
    government: str   = ""
    allegiance: str   = ""
    jump_dist:  float = 0.0
    jump_dist_total: float = 0.0
    star_pos:   Optional[tuple] = None
    discovery_announced: bool = False

    # Commander & Ship
    commander:  str = ""
    ship_type:  str = ""
    ship_name:  str = ""
    ship_ident: str = ""

    # Ship status
    hull:           float = 1.0
    shields_up:     bool  = True
    fuel:           float = 0.0
    fuel_max:       float = 0.0
    heat:           float = 0.0
    fuel_announced: bool  = False
    fuel_reservoir: float = 0.0
    cargo:          int   = 0
    cargo_capacity: int   = 0

    # Status flags (from Status.json)
    docked:            bool = False
    landed:            bool = False
    supercruise:       bool = False
    low_fuel:          bool = False
    overheating:       bool = False
    hardpoints:        bool = False
    scooping:          bool = False
    landing_gear:      bool = False
    flight_assist_off: bool = False
    cargo_scoop:       bool = False
    silent_running:    bool = False
    lights_on:         bool = False
    night_vision:      bool = False
    in_srv:            bool = False
    analysis_mode:     bool = False
    mass_locked:       bool = False
    in_main_ship:      bool = False

    # Position
    station:      str            = ""
    lat:          Optional[float] = None
    lon:          Optional[float] = None
    altitude:     Optional[float] = None
    nearest_body: str            = ""
    heading:      Optional[float] = None

    # Route
    route_destination:    str  = ""
    route_hops:           int  = 0
    route_next:           str  = ""
    route_next_star:      str  = ""
    route_next_scoopable: bool = False
    route_dist:           float = 0.0
    route_next_dist:      float = 0.0
    route_list:           list[dict] = field(default_factory=list)

    # Body approach (ApproachBody / LeaveBody)
    approach_body: str = ""

    # Current destination target
    target_body: str = ""

    # Station details (populated on Docked, cleared on Undocked)
    station_type:       str  = ""
    station_economy:    str  = ""
    station_allegiance: str  = ""
    station_services:   list = field(default_factory=list)
    station_dist_ls:    float = 0.0

    # BGS
    controlling_faction: str  = ""
    controlling_state:   str  = ""
    factions:            list = field(default_factory=list)
    station_count:       int  = 0

    # Bodies
    bodies:    list = field(default_factory=list)  # list[BodyInfo]
    bio_scans: list = field(default_factory=list)  # list[BioScan]

    # FSS progress
    fss_body_count: int = 0  # total bodies in system (from FSSDiscoveryScan)

    # Session stats (since app launch, live events only)
    session_start:      str = ""
    session_jumps:      int = 0
    session_first_disc: int = 0
    session_mapped:     int = 0
    session_value:      int = 0

    # Cargo inventory (from Cargo.json)
    cargo_items: list = field(default_factory=list)  # list[dict] {name, count, stolen}

    # Materials (localised_name -> count)
    materials_raw: dict = field(default_factory=dict)
    materials_mfg: dict = field(default_factory=dict)
    materials_enc: dict = field(default_factory=dict)

    # Missions
    missions: list = field(default_factory=list)  # list[MissionInfo]

    # Engineers: name -> (rank, progress_str)
    engineers: dict = field(default_factory=dict)

    # Event log
    events: deque = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))

    # Volume 0–100
    volume: int = 50

    # Service status (EDSM connectivity indicator shown in footer)
    edsm_status: ServiceStatus = field(default_factory=ServiceStatus)

    # DSS suppression: body names where SAAScanComplete fired, awaiting the
    # subsequent game-triggered Scan event to suppress its duplicate message.
    dss_recently_completed: set = field(default_factory=set)

    def push_event(self, ev: LogEvent) -> None:
        self.events.appendleft(ev)

    def upsert_body(self, info: BodyInfo) -> None:
        for i, existing in enumerate(self.bodies):
            if existing.name == info.name:
                bio    = existing.bio_signals
                geo    = existing.geo_signals
                gen    = existing.bio_genuses[:]
                mapped = existing.mapped
                fss    = existing.fss_scanned
                first  = existing.first_discovered
                dist   = existing.dist_ls
                self.bodies[i] = info
                b = self.bodies[i]
                if b.bio_signals == 0:               b.bio_signals  = bio
                if b.geo_signals == 0:               b.geo_signals  = geo
                if not b.bio_genuses:                b.bio_genuses  = gen
                if b.dist_ls == 0.0 and dist > 0.0:  b.dist_ls      = dist
                b.mapped      = mapped or b.mapped
                b.fss_scanned = fss    or b.fss_scanned
                if first: b.first_discovered = True
                return
        ids = [b.body_id for b in self.bodies]
        pos = bisect.bisect_left(ids, info.body_id)
        self.bodies.insert(pos, info)

    def remove_mission(self, mission_id: int) -> None:
        self.missions = [m for m in self.missions if m.mission_id != mission_id]
