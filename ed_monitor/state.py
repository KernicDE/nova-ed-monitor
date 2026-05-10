from __future__ import annotations

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
    first_footfall:      bool  = False # True when WasFootfalled=false in Scan event
    mass_em:             float = 0.0   # MassEM (planets) or StellarMass (stars) from Scan event
    efficiency_bonus:    bool  = False # True when DSS probes_used <= efficiency_target
    has_rings:           bool  = False # True if body has at least one ring
    ring_count:          int   = 0     # number of rings
    tidal_lock:          bool  = False # True if body is tidally locked to parent


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
    mission_id:    int
    name:          str
    destination:   str    # "System / Station" or just system
    expiry:        str    # ISO timestamp string, "" if none
    mission_type:  str  = ""     # "Massacre", "Delivery", "Courier", etc.
    faction:       str  = ""     # issuing faction
    reward:        int  = 0
    wing:          bool = False
    cargo_type:    str  = ""     # Commodity_Localised
    cargo_count:   int  = 0
    influence:     str  = ""     # "+", "++", "+++"


# ── App state ──────────────────────────────────────────────────────────────────

@dataclass
class AppState:
    # System
    system:              str   = "—"
    primary_star_class:  str   = ""
    population:          int   = 0
    economy:             str   = ""
    security:            str   = ""
    government:          str   = ""
    allegiance:          str   = ""
    jump_dist:           float = 0.0
    jump_dist_total: float = 0.0
    star_pos:   Optional[tuple] = None
    discovery_announced: bool = False
    fss_honk_pending:    bool = False  # True from FSSDiscoveryScan until FSSAllBodiesFound fires

    # Commander & Ship
    commander:  str = ""
    ship_type:  str = ""
    ship_name:  str = ""
    ship_ident: str = ""

    # Ship status
    hull:           float = 1.0
    shields_up:     bool  = True
    fuel:               float = 0.0
    fuel_max:           float = 0.0
    heat:               float = 0.0
    fuel_announced:     bool  = False
    fuel_low_announced: bool  = False
    fuel_reservoir:     float = 0.0
    fuel_warning_percent: int = 25
    home_system:          str = ""
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
    route_arrived:        bool = False
    route_next:           str  = ""
    route_next_star:      str  = ""
    route_next_scoopable: bool = False
    route_dist:           float = 0.0
    route_next_dist:      float = 0.0
    route_list:           list[dict] = field(default_factory=list)

    # Body approach (ApproachBody / LeaveBody)
    approach_body: str = ""

    # Current destination target
    target_body:        str = ""
    target_body_system: str = ""  # if target is in another system (from Status.json)
    target_body_body:   str = ""  # surface settlement's parent body (from Status.json)

    # Ship target (ShipTargeted journal event)
    target_ship:         str   = ""    # ship type
    target_ship_pilot:   str   = ""    # pilot name
    target_ship_rank:    str   = ""    # pilot rank
    target_ship_faction: str   = ""    # faction
    target_ship_legal:   str   = ""    # LegalStatus
    target_ship_shield:  float = -1.0  # 0-100, -1 = unknown
    target_ship_hull:    float = -1.0  # 0-100, -1 = unknown
    target_ship_bounty:  int   = 0
    target_ship_stage:   int   = 0     # scan stage 0-3

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
    # Monotonically-increasing counter; bumped on every upsert or clear so UI
    # can detect changes without comparing the full list.
    bodies_version: int = 0
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
    session_start_ts:   float = 0.0
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
    # Pending threading.Timer objects scheduled by the ≥3 G handler. Tracked
    # so LeaveBody / SupercruiseEntry / jumps can cancel them — otherwise
    # they fire on a body the player has already left.
    high_g_timers: list = field(default_factory=list, repr=False)

    # Under-attack warning cooldown & flash
    under_attack_flash_until: float = 0.0
    last_under_attack_at:     float = 0.0
    last_under_attack_name:   str   = ""

    # Wallet / cross-galaxy inventory
    credits:      int  = 0
    stored_ships: list = field(default_factory=list)   # list[dict] from StoredShips event
    suit_loadout: dict = field(default_factory=dict)   # from SuitLoadout event
    backpack:     dict = field(default_factory=dict)   # from Backpack/BackpackChange events
    ship_locker:  dict = field(default_factory=dict)   # from ShipLocker event

    # Neutron route plotter
    jump_range:           float = 0.0   # MaxJumpRange from Loadout (unladen theoretical max)
    jump_range_last:      float = 0.0   # last actual JumpDist from FSDJump (laden reality)
    neutron_route:        list  = field(default_factory=list)  # list of jump dicts
    neutron_route_to:     str   = ""
    neutron_route_status: str   = ""   # "", "plotting", "done", "error"

    # Event log
    events: deque = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    # Monotonically-increasing counter; bumped on every push_event() call so UI
    # can detect new log entries without comparing deque contents.
    events_version: int = 0

    # Volume 0–100; muted flag + pre-mute restore value
    volume:          int  = 50
    muted:           bool = False
    pre_mute_volume: int  = 50

    # Chat TTS mutes (runtime-toggled; also set from config at startup)
    chat_tts_muted:    bool = False  # mutes all chat sources (in-game, Twitch, YouTube)
    twitch_tts_muted:  bool = False  # mutes Twitch chat TTS only
    youtube_tts_muted: bool = False  # mutes YouTube chat TTS only

    # Service status (EDSM connectivity indicator shown in footer)
    edsm_status: ServiceStatus = field(default_factory=ServiceStatus)

    # EDSM system lookup result: None = pending, True = known, False = not in EDSM
    system_edsm_known: Optional[bool] = None

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
    nearest_populated_stations:   list  = field(default_factory=list)  # list[dict] from EDSM
    current_system_stations:      list  = field(default_factory=list)  # list[dict] from EDSM
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

    # FSD hyperspace jump in progress (StartJump → FSDJump)
    in_hyperspace: bool = False

    # Background thread heartbeats (updated each loop iteration; 0.0 = never seen)
    journal_heartbeat: float = 0.0
    status_heartbeat:  float = 0.0

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

    # Timestamp of last FSDJump/CarrierJump (unix time); used for auto-switch to OVERVIEW
    last_jump_at: float = 0.0

    # Event-driven auto-panel trigger: daemon threads set these to request a one-shot
    # panel switch; the UI consumes the trigger by comparing the version to last seen.
    # The UI never writes back — it tracks the last-seen version locally.
    auto_panel_trigger:         str = ""   # panel abbrev to switch to (e.g. "route", "overview")
    auto_panel_trigger_version: int = 0    # bumped on each new trigger

    # Current UI mode — set by app.py each tick from status flags.
    # Values: "ship" | "combat" | "on_foot" | "srv" | "offline"
    # Used by panels to pick the correct mode palette (P.mp(snap.ui_mode)).
    ui_mode: str = "ship"

    def push_event(self, ev: LogEvent) -> None:
        self.events.appendleft(ev)
        self.events_version += 1

    def clear_bodies(self) -> None:
        """Clear bodies list and both lookup indices."""
        self.bodies.clear()
        self._bodies_by_name.clear()
        self._bodies_by_id.clear()
        self.bodies_version += 1

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
            if first:    b.first_discovered = True
            if existing.first_mapped:   b.first_mapped   = True
            if existing.first_footfall: b.first_footfall = True
            if b.bio_value_min == 0: b.bio_value_min = bvmin
            if b.bio_value_max == 0: b.bio_value_max = bvmax
            if not b.materials and mats:    b.materials    = mats
            if not b.unusual_body and unusual: b.unusual_body = unusual
            if existing.efficiency_bonus:   b.efficiency_bonus = True
            if existing.terraform:          b.terraform        = True
            # Update id index in case body_id changed (rare)
            self._bodies_by_id[b.body_id] = i
            self.bodies_version += 1
            return
        # New body — insert sorted by body_id. Locate insertion point without
        # materialising an ids list: a small linear walk is faster than
        # allocating a parallel list for every insert, and these lists are
        # bounded in size (a star system has at most a few hundred bodies).
        pos = 0
        target = info.body_id
        for idx, existing_b in enumerate(self.bodies):
            if existing_b.body_id >= target:
                pos = idx
                break
        else:
            pos = len(self.bodies)
        self.bodies.insert(pos, info)
        # Shift every index that moved (pos .. end) in place — O(K) where K is
        # the number of entries at or after pos, avoiding a full O(N) rebuild.
        for idx in range(pos + 1, len(self.bodies)):
            b2 = self.bodies[idx]
            self._bodies_by_name[b2.name]  = idx
            self._bodies_by_id[b2.body_id] = idx
        self._bodies_by_name[info.name]    = pos
        self._bodies_by_id[info.body_id]   = pos
        self.bodies_version += 1

    def remove_mission(self, mission_id: int) -> None:
        self.missions = [m for m in self.missions if m.mission_id != mission_id]


# Default body radius used when a Scan hasn't provided one yet (placeholder
# planets inserted by FSSBodySignals, bio scans that fire before the matching
# Scan event). Mars-sized; picked to match the Frontier default surface radius
# used by the journal for placeholder bodies.
_DEFAULT_BODY_RADIUS_M: float = 3_389_500.0


# ── Body value formula (Frontier forum formula by MattG) ──────────────────────
# https://forums.frontier.co.uk/threads/exploration-value-formulae.232000/

_Q                         = 0.56591828
_MASS_POW                  = 0.2
_MIN_VALUE                 = 500
_BASIC_VALUE               = 300
_BASIC_BONUS_TERRAFORMABLE = 93328
_EFFICIENCY_MULTIPLIER     = 1.25
_ODYSSEY_MAPPING_BONUS     = 0.3   # 30 % extra on mapped value for first footfall

_SPECIFIC_VALUES: dict[str, int] = {
    "Metal rich body":              21790,
    "High metal content body":       9654,
    "Ammonia world":                96932,
    "Water world":                  64831,
    "Earthlike body":               64831,
    "Sudarsky class I gas giant":    1656,
    "Sudarsky class II gas giant":   9654,
}

_SPECIFIC_BONUS: dict[str, int] = {
    "Metal rich body":         105678,
    "High metal content body": 100677,
    "Water world":             116295,
    "Earthlike body":          116295,
}

_BODY_EST_VALUES: dict[str, int] = {
    "Earthlike body":                      64_831,
    "Water world":                        130_000,
    "Ammonia world":                      200_000,
    "Metal rich body":                     35_000,
    "High metal content body":             22_000,
    "Rocky body":                           3_500,
    "Rocky ice body":                       4_000,
    "Icy body":                             2_500,
    "Sudarsky class I gas giant":           4_500,
    "Sudarsky class II gas giant":         25_000,
    "Sudarsky class III gas giant":         4_500,
    "Sudarsky class IV gas giant":          5_500,
    "Sudarsky class V gas giant":           6_000,
    "Helium rich gas giant":                3_500,
    "Gas giant with water-based life":     19_000,
    "Gas giant with water based life":     19_000,
    "Gas giant with ammonia-based life":   22_000,
    "Gas giant with ammonia based life":   22_000,
    "Water giant":                          4_000,
}


def estimate_value_base(b: "BodyInfo") -> int:
    """Raw base scan value before any mapping/discovery multipliers.

    When mass_em is known (from journal Scan), uses the exact Frontier formula:
      k * (1 + Q * M^0.2)
    Falls back to the _BODY_EST_VALUES table when mass is unavailable.
    Returns 0 for stars and unrecognised body types.
    """
    if b.mass_em > 0.0:
        k = _SPECIFIC_VALUES.get(b.planet_class, _BASIC_VALUE)
        if b.terraform:
            k += _SPECIFIC_BONUS.get(b.planet_class, _BASIC_BONUS_TERRAFORMABLE)
        return int(k * (1.0 + _Q * b.mass_em ** _MASS_POW))
    base = _BODY_EST_VALUES.get(b.planet_class, 0)
    if base > 0 and b.terraform:
        base += _SPECIFIC_BONUS.get(b.planet_class, _BASIC_BONUS_TERRAFORMABLE)
    return base


def estimate_value_mapped(b: "BodyInfo") -> int:
    """Projected or actual mapped value with all ED exploration bonuses.

    When b.mapped is True: actual payout (player already DSS'd the body).
    When b.fss_scanned and not mapped: projected mapped value (optimistic:
    always assumes efficiency bonus).
    When neither: raw base value or EDSM estimate (no mapping multipliers).

    Follows MattG's authoritative Frontier formula (Sep 2022):
    https://forums.frontier.co.uk/threads/exploration-value-formulae.232000/
    """
    if b.fss_scanned:
        base = estimate_value_base(b)
    elif b.value > 0:
        return b.value
    else:
        return estimate_value_base(b)

    if base <= 0:
        return 0

    # Mapping multiplier (MattG)
    if b.first_discovered and b.first_mapped:
        mult = 3.699622554
    elif b.first_mapped:
        mult = 8.0956
    else:
        mult = 3.3333333333

    value = base * mult

    # Odyssey / first footfall bonus — ADDITIVE, applied before efficiency
    if b.first_footfall:
        value += max(value * 0.3, 555)

    # Efficiency bonus
    if b.mapped:
        if b.efficiency_bonus:
            value *= _EFFICIENCY_MULTIPLIER
    else:
        # For FSS'd but not mapped: always assume efficiency (optimistic projection)
        value *= _EFFICIENCY_MULTIPLIER

    # 500-credit minimum — applied AFTER all mapping bonuses
    value = max(_MIN_VALUE, value)

    # First discoverer 2.6× — applied at the very end for ALL cases
    if b.first_discovered:
        value *= 2.6

    return int(value)
