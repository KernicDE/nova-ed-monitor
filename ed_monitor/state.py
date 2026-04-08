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
    bio_value_min:       int    = 0   # estimated min bio value (from genus range)
    bio_value_max:       int    = 0   # estimated max bio value (from genus range)
    bio_genuses_predicted: list = field(default_factory=list)  # predicted genera before DSS
    semi_major_axis:     float = 0.0   # metres
    orbital_period:      float = 0.0   # seconds
    mean_anomaly:        float = 0.0   # degrees at scan time
    eccentricity:        float = 0.0
    orbital_inclination: float = 0.0   # degrees
    surface_gravity:     float = 0.0   # m/s², from SurfaceGravity in Scan event
    surface_temp:        float = 0.0   # K, from SurfaceTemperature in Scan event
    volcanism:           str   = ""    # raw volcanism string from Scan event
    materials:           dict  = field(default_factory=dict)   # {name_lower: pct} from Scan Materials
    unusual_body:        str   = ""    # non-empty = unusual (e.g. "Tiny <300 km", "Eccentric")


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
    sample_lats:       list  = field(default_factory=list)  # lat of each on-foot sample
    sample_lons:       list  = field(default_factory=list)  # lon of each on-foot sample
    comp_lats:         list  = field(default_factory=list)  # lat from COMP scanner (ship Log events)
    comp_lons:         list  = field(default_factory=list)  # lon from COMP scanner (ship Log events)
    current_bearing:   Optional[str]  = None  # compass direction toward nearest sample (unused, kept for compat)
    sample_bearings:   list  = field(default_factory=list)  # compass direction toward each nav target
    first_footfall:    bool  = False


# ── Engineer ──────────────────────────────────────────────────────────────────

@dataclass
class EngineerInfo:
    name:          str
    rank:          int   = 0
    rank_progress: float = 0.0  # 0–100
    progress:      str   = ""   # "Unlocked", "Invited", "Known", "Unknown", etc.
    engineer_id:   int   = 0


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
    orbital_cruise:    bool = False

    # Power distribution pips (from Status.json Pips; each 0.0–4.0 in 0.5 steps)
    pips_sys: float = 4.0
    pips_eng: float = 2.0
    pips_wep: float = 2.0

    # On-foot / suit status (from Status.json; only valid when not in_main_ship and not in_srv)
    suit_health:     float = 1.0
    suit_oxygen:     float = 1.0
    selected_weapon: str   = ""
    on_foot_gravity: float = 0.0
    low_oxygen:      bool  = False
    low_health_suit: bool  = False
    suit_cold:       bool  = False
    suit_hot:        bool  = False

    # SRV-specific flags (from Status.json Flags; only meaningful when in_srv)
    srv_handbrake:        bool = False
    srv_turret_view:      bool = False
    srv_turret_retracted: bool = False
    srv_drive_assist:     bool = False

    # Position
    station:      str            = ""
    lat:          Optional[float] = None
    lon:          Optional[float] = None
    altitude:     Optional[float] = None
    nearest_body: str            = ""
    heading:      Optional[float] = None
    first_footfall_body:    str = ""  # body name where player has first footfall
    first_footfall_body_id: int = -1  # body ID (more reliable than name matching)
    first_footfall_bodies:  set = field(default_factory=set)  # body names where footfall was already announced

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
    # Internal indices for O(1) body lookups (not serialised; maintained by upsert_body/clear_bodies)
    _bodies_by_name: dict = field(default_factory=dict, repr=False)  # name  → list index
    _bodies_by_id:   dict = field(default_factory=dict, repr=False)  # body_id → list index

    # FSS progress
    fss_body_count: int = 0  # total bodies in system (from FSSDiscoveryScan)

    # Client online state
    client_online:           bool = False  # True after LoadGame/Location, False after Shutdown
    client_shutdown_pending: bool = False  # True after Shutdown, prevents status.py from restoring online

    # Session stats (since app launch, live events only)
    session_start:      str = ""
    session_jumps:      int = 0
    session_first_disc: int = 0
    session_mapped:     int = 0
    session_value:      int = 0

    # Persistent statistics (from DB, keyed by stat_name → {today,week,month,year,total})
    stats: dict = field(default_factory=dict)

    # Cargo inventory (from Cargo.json)
    cargo_items: list = field(default_factory=list)  # list[dict] {name, count, stolen}

    # Materials (localised_name -> count)
    materials_raw: dict = field(default_factory=dict)
    materials_mfg: dict = field(default_factory=dict)
    materials_enc: dict = field(default_factory=dict)

    # Missions
    missions: list = field(default_factory=list)  # list[MissionInfo]

    # Engineers: name -> EngineerInfo
    engineers: dict = field(default_factory=dict)

    # High-G approach warning
    high_g_extreme: bool = False

    # Wallet / cross-galaxy inventory
    credits:      int  = 0
    stored_ships: list = field(default_factory=list)   # list[dict] from StoredShips event
    suit_loadout: dict = field(default_factory=dict)   # from SuitLoadout event
    backpack:     dict = field(default_factory=dict)   # from Backpack/BackpackChange events

    # Neutron route plotter
    jump_range:           float = 0.0   # MaxJumpRange from Loadout (unladen theoretical max)
    jump_range_last:      float = 0.0   # last actual JumpDist from FSDJump (laden reality)
    neutron_route:        list  = field(default_factory=list)  # list of jump dicts
    neutron_route_to:     str   = ""
    neutron_route_status: str   = ""   # "", "plotting", "done", "error"

    # Event log
    events: deque = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))

    # Volume 0–100
    volume: int = 50

    # Service status (EDSM connectivity indicator shown in footer)
    edsm_status: ServiceStatus = field(default_factory=ServiceStatus)

    # DSS suppression: body names where SAAScanComplete fired, awaiting the
    # subsequent game-triggered Scan event to suppress its duplicate message.
    dss_recently_completed: set = field(default_factory=set)

    # Notable body value threshold (from config, controls Overview filter)
    notable_value_threshold: int = 500_000

    # EDSM dump lookups (populated by journal.py after each system change)
    system_power:                 str   = ""
    system_power_state:           str   = ""
    nearest_populated_name:       str   = ""
    nearest_populated_dist:       float = 0.0
    nearest_populated_allegiance: str   = ""
    route_next_stations:          list  = field(default_factory=list)  # list[dict]

    # Spansh carrier lookup (populated by spansh.py after each system change)
    carriers_current_system: list = field(default_factory=list)  # list[dict]

    # Docking helper (from DockingGranted; cleared on Undocked/FSDJump)
    docked_pad:          int  = 0
    docked_station_type: str  = ""
    docked_station_name: str  = ""

    # Massacre mission kill tracking: {mission_id: {"faction": str, "needed": int, "done": int}}
    massacre_kills: dict = field(default_factory=dict)

    # BGS activity log: {system_name: {faction_name: {activity: count}}}
    # Reset daily at midnight UTC (approximate tick boundary)
    bgs_log:      dict = field(default_factory=dict)
    bgs_log_date: str  = ""   # ISO date string of last reset (YYYY-MM-DD)

    # Colonisation construction sites: {market_id: site_dict}
    colonisation_sites: dict = field(default_factory=dict)

    # PowerPlay 2.0
    pp_power:          str = ""
    pp_total_merits:   int = 0
    pp_session_merits: int = 0
    pp_rank:           int = 0

    # Situational panel config (from config.toml; controls visibility/order)
    situational_panels: list = field(default_factory=list)  # ["overview", "bio", ...]; [] = default order

    # EDSM enrichment for nav route systems (populated by journal.py on route/system change)
    route_list_edsm:   dict = field(default_factory=dict)  # name → {x, y, z, population, allegiance}
    route_bodies_edsm: dict = field(default_factory=dict)  # name → {"bio": int, "geo": int}

    def push_event(self, ev: LogEvent) -> None:
        self.events.appendleft(ev)

    def clear_bodies(self) -> None:
        """Clear bodies list and both lookup indices."""
        self.bodies.clear()
        self._bodies_by_name.clear()
        self._bodies_by_id.clear()

    def _rebuild_body_index(self) -> None:
        """Rebuild name/id indices from current bodies list (call after bulk inserts)."""
        self._bodies_by_name = {b.name: i for i, b in enumerate(self.bodies)}
        self._bodies_by_id   = {b.body_id: i for i, b in enumerate(self.bodies)}

    def upsert_body(self, info: BodyInfo) -> None:
        i = self._bodies_by_name.get(info.name, -1)
        if i >= 0 and i < len(self.bodies) and self.bodies[i].name == info.name:
            existing = self.bodies[i]
            bio    = existing.bio_signals
            geo    = existing.geo_signals
            gen    = existing.bio_genuses[:]
            mapped = existing.mapped
            fss    = existing.fss_scanned
            first  = existing.first_discovered
            dist   = existing.dist_ls
            pc     = existing.planet_class
            st     = existing.star_type
            bvmin  = existing.bio_value_min
            bvmax  = existing.bio_value_max
            mats   = existing.materials.copy()
            unusual = existing.unusual_body
            self.bodies[i] = info
            b = self.bodies[i]
            if not b.planet_class and pc:        b.planet_class = pc
            if not b.star_type and st:           b.star_type    = st
            if b.bio_signals == 0:               b.bio_signals  = bio
            if b.geo_signals == 0:               b.geo_signals  = geo
            if not b.bio_genuses:                b.bio_genuses  = gen
            if b.dist_ls == 0.0 and dist > 0.0:  b.dist_ls      = dist
            b.mapped      = mapped or b.mapped
            b.fss_scanned = fss    or b.fss_scanned
            if first: b.first_discovered = True
            if b.bio_value_min == 0: b.bio_value_min = bvmin
            if b.bio_value_max == 0: b.bio_value_max = bvmax
            if not b.materials and mats:    b.materials    = mats
            if not b.unusual_body and unusual: b.unusual_body = unusual
            # Update id index in case body_id changed (rare)
            self._bodies_by_id[b.body_id] = i
            return
        # New body — insert sorted by body_id
        ids = [b.body_id for b in self.bodies]
        pos = bisect.bisect_left(ids, info.body_id)
        self.bodies.insert(pos, info)
        # All indices at pos and beyond shifted — rebuild both indices
        self._rebuild_body_index()

    def remove_mission(self, mission_id: int) -> None:
        self.missions = [m for m in self.missions if m.mission_id != mission_id]
