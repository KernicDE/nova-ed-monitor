from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from .state import BioScan, BodyInfo, LogEvent


def _safe_cmdr(cmdr: str) -> str:
    """Sanitise a commander name for use as a config key suffix."""
    return "".join(c if c.isalnum() else "_" for c in cmdr)


class Database:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._init()
        self._migrate()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript("""
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous  = NORMAL;
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    category   TEXT    NOT NULL,
                    message    TEXT    NOT NULL,
                    system     TEXT    NOT NULL DEFAULT '',
                    event_date TEXT    NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS config (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bodies (
                    system           TEXT    NOT NULL,
                    body_name        TEXT    NOT NULL,
                    body_id          INTEGER NOT NULL DEFAULT 0,
                    level            INTEGER NOT NULL DEFAULT 1,
                    planet_class     TEXT    NOT NULL DEFAULT '',
                    star_type        TEXT    NOT NULL DEFAULT '',
                    atmosphere       TEXT    NOT NULL DEFAULT '',
                    terraform        INTEGER NOT NULL DEFAULT 0,
                    landable         INTEGER NOT NULL DEFAULT 0,
                    bio_signals      INTEGER NOT NULL DEFAULT 0,
                    geo_signals      INTEGER NOT NULL DEFAULT 0,
                    bio_genuses      TEXT    NOT NULL DEFAULT '',
                    dist_ls          REAL    NOT NULL DEFAULT 0,
                    value            INTEGER NOT NULL DEFAULT 0,
                    first_discovered INTEGER NOT NULL DEFAULT 0,
                    first_mapped     INTEGER NOT NULL DEFAULT 0,
                    mapped           INTEGER NOT NULL DEFAULT 0,
                    radius           REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (system, body_name)
                );
            """)

    def _migrate(self) -> None:
        """Idempotent schema migrations."""
        migrations = [
            "ALTER TABLE events ADD COLUMN event_date TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bodies ADD COLUMN fss_scanned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN bio_value_min INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN bio_value_max INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN semi_major_axis REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN orbital_period REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN mean_anomaly REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN eccentricity REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN orbital_inclination REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN surface_gravity REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN materials TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bodies ADD COLUMN surface_temp REAL NOT NULL DEFAULT 0",
            "ALTER TABLE bodies ADD COLUMN volcanism TEXT NOT NULL DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS stats (
                date  TEXT NOT NULL,
                stat  TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (date, stat)
            )""",
            """CREATE TABLE IF NOT EXISTS bio_scans (
                system            TEXT    NOT NULL,
                body              TEXT    NOT NULL,
                species           TEXT    NOT NULL,
                species_localised TEXT    NOT NULL DEFAULT '',
                genus_localised   TEXT    NOT NULL DEFAULT '',
                samples           INTEGER NOT NULL DEFAULT 1,
                min_dist          REAL    NOT NULL DEFAULT 0,
                body_radius       REAL    NOT NULL DEFAULT 0,
                value             INTEGER NOT NULL DEFAULT 0,
                complete          INTEGER NOT NULL DEFAULT 0,
                first_discovered  INTEGER NOT NULL DEFAULT 0,
                first_footfall    INTEGER NOT NULL DEFAULT 0,
                sample_lats       TEXT    NOT NULL DEFAULT '',
                sample_lons       TEXT    NOT NULL DEFAULT '',
                last_lat          REAL,
                last_lon          REAL,
                PRIMARY KEY (system, body, species)
            )""",
            "ALTER TABLE bio_scans ADD COLUMN comp_lats TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bio_scans ADD COLUMN comp_lons TEXT NOT NULL DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS idx_stats_date ON stats(date)",
            "CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)",
            # EDSM dump tables
            """CREATE TABLE IF NOT EXISTS edsm_systems (
                id64        INTEGER PRIMARY KEY,
                name        TEXT    NOT NULL,
                x           REAL    NOT NULL DEFAULT 0,
                y           REAL    NOT NULL DEFAULT 0,
                z           REAL    NOT NULL DEFAULT 0,
                allegiance  TEXT    NOT NULL DEFAULT '',
                government  TEXT    NOT NULL DEFAULT '',
                economy     TEXT    NOT NULL DEFAULT '',
                population  INTEGER NOT NULL DEFAULT 0,
                security    TEXT    NOT NULL DEFAULT '',
                power       TEXT    NOT NULL DEFAULT '',
                power_state TEXT    NOT NULL DEFAULT ''
            )""",
            "CREATE INDEX IF NOT EXISTS idx_edsm_systems_name ON edsm_systems(name)",
            """CREATE TABLE IF NOT EXISTS edsm_stations (
                id           INTEGER PRIMARY KEY,
                name         TEXT    NOT NULL,
                system_id64  INTEGER NOT NULL DEFAULT 0,
                system_name  TEXT    NOT NULL DEFAULT '',
                type         TEXT    NOT NULL DEFAULT '',
                dist_ls      REAL    NOT NULL DEFAULT 0,
                allegiance   TEXT    NOT NULL DEFAULT '',
                government   TEXT    NOT NULL DEFAULT '',
                economy      TEXT    NOT NULL DEFAULT '',
                has_market   INTEGER NOT NULL DEFAULT 0,
                has_shipyard INTEGER NOT NULL DEFAULT 0,
                has_outfitting INTEGER NOT NULL DEFAULT 0,
                other_services TEXT  NOT NULL DEFAULT ''
            )""",
            "CREATE INDEX IF NOT EXISTS idx_edsm_stations_system ON edsm_stations(system_name)",
            # Route EDSM live-lookup cache
            """CREATE TABLE IF NOT EXISTS edsm_route_cache (
                name       TEXT PRIMARY KEY,
                known      INTEGER NOT NULL DEFAULT 0,
                scoopable  INTEGER NOT NULL DEFAULT -1,
                cached_at  TEXT    NOT NULL DEFAULT ''
            )""",
            # Route bodies cache: bio/geo signal sums + body count per system
            """CREATE TABLE IF NOT EXISTS edsm_route_bodies_cache (
                system_name TEXT PRIMARY KEY,
                bio_count   INTEGER NOT NULL DEFAULT 0,
                geo_count   INTEGER NOT NULL DEFAULT 0,
                body_count  INTEGER NOT NULL DEFAULT 0,
                cached_at   TEXT    NOT NULL DEFAULT ''
            )""",
            "ALTER TABLE edsm_route_bodies_cache ADD COLUMN body_count INTEGER NOT NULL DEFAULT 0",
            # Multi-commander support: add commander column to per-commander tables
            "ALTER TABLE events ADD COLUMN commander TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bio_scans ADD COLUMN commander TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stats ADD COLUMN commander TEXT NOT NULL DEFAULT ''",
        ]
        with self._lock:
            for sql in migrations:
                try:
                    self._conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()
        # Recreate bio_scans and stats with commander in primary key (run once each)
        self._migrate_stats_v2()
        self._migrate_bio_scans_v2()

    def _migrate_stats_v2(self) -> None:
        """Recreate stats with (date, stat, commander) primary key — one-time migration."""
        if self.get_config("_migration_stats_v2") == "1":
            return
        with self._lock:
            try:
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS stats_v2 (
                        date      TEXT NOT NULL,
                        stat      TEXT NOT NULL,
                        commander TEXT NOT NULL DEFAULT '',
                        value     REAL NOT NULL DEFAULT 0,
                        PRIMARY KEY (date, stat, commander)
                    );
                    INSERT OR IGNORE INTO stats_v2 (date, stat, commander, value)
                        SELECT date, stat, IFNULL(commander, ''), value FROM stats;
                    DROP TABLE stats;
                    ALTER TABLE stats_v2 RENAME TO stats;
                    CREATE INDEX IF NOT EXISTS idx_stats_date ON stats(date);
                """)
                self._conn.execute(
                    "INSERT OR REPLACE INTO config(key, value) VALUES('_migration_stats_v2', '1')"
                )
                self._conn.commit()
            except Exception:
                pass

    def _migrate_bio_scans_v2(self) -> None:
        """Recreate bio_scans with (system, body, species, commander) primary key — one-time migration."""
        if self.get_config("_migration_bio_scans_v2") == "1":
            return
        with self._lock:
            try:
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS bio_scans_v2 (
                        system            TEXT    NOT NULL,
                        body              TEXT    NOT NULL,
                        species           TEXT    NOT NULL,
                        commander         TEXT    NOT NULL DEFAULT '',
                        species_localised TEXT    NOT NULL DEFAULT '',
                        genus_localised   TEXT    NOT NULL DEFAULT '',
                        samples           INTEGER NOT NULL DEFAULT 1,
                        min_dist          REAL    NOT NULL DEFAULT 0,
                        body_radius       REAL    NOT NULL DEFAULT 0,
                        value             INTEGER NOT NULL DEFAULT 0,
                        complete          INTEGER NOT NULL DEFAULT 0,
                        first_discovered  INTEGER NOT NULL DEFAULT 0,
                        first_footfall    INTEGER NOT NULL DEFAULT 0,
                        sample_lats       TEXT    NOT NULL DEFAULT '',
                        sample_lons       TEXT    NOT NULL DEFAULT '',
                        last_lat          REAL,
                        last_lon          REAL,
                        comp_lats         TEXT    NOT NULL DEFAULT '',
                        comp_lons         TEXT    NOT NULL DEFAULT '',
                        PRIMARY KEY (system, body, species, commander)
                    );
                    INSERT OR IGNORE INTO bio_scans_v2
                        SELECT system, body, species, IFNULL(commander, ''),
                               species_localised, genus_localised,
                               samples, min_dist, body_radius, value, complete,
                               first_discovered, first_footfall,
                               sample_lats, sample_lons, last_lat, last_lon,
                               comp_lats, comp_lons
                        FROM bio_scans;
                    DROP TABLE bio_scans;
                    ALTER TABLE bio_scans_v2 RENAME TO bio_scans;
                """)
                self._conn.execute(
                    "INSERT OR REPLACE INTO config(key, value) VALUES('_migration_bio_scans_v2', '1')"
                )
                self._conn.commit()
            except Exception:
                pass

    def insert(self, ev: LogEvent, system: str, commander: str = "") -> None:
        event_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (timestamp, category, message, system, event_date, commander)"
                " VALUES (?,?,?,?,?,?)",
                (ev.time, ev.category.label(), ev.message, system, event_date, commander),
            )
            self._conn.commit()

    def prune_events(self, days: int = 180) -> int:
        """Delete events older than `days` days. Returns number of rows deleted."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE event_date != '' AND event_date < ?",
                (cutoff,),
            )
            self._conn.commit()
        return cur.rowcount

    def get_recent_events(self, limit: int, commander: str = "") -> list[LogEvent]:
        from .state import EventCategory
        label_to_cat = {c.value: c for c in EventCategory}

        with self._lock:
            if commander:
                rows = self._conn.execute(
                    "SELECT timestamp, category, message FROM events"
                    " WHERE (commander = ? OR commander = '') ORDER BY id DESC LIMIT ?",
                    (commander, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT timestamp, category, message FROM events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        result = []
        for ts, cat_label, msg in reversed(rows):
            cat = label_to_cat.get(cat_label, EventCategory.System)
            result.append(LogEvent(time=ts, category=cat, message=msg))
        return result

    def get_hull(self) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM config WHERE key = 'hull'"
            ).fetchone()
        if row:
            try:
                return float(row[0])
            except ValueError:
                pass
        return 1.0

    def set_hull(self, hull: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO config(key, value) VALUES('hull', ?)",
                (str(hull),),
            )
            self._conn.commit()

    def get_config(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)",
                (key, value),
            )
            self._conn.commit()

    def save_body(self, system: str, body: BodyInfo) -> None:
        self.save_bodies_batch(system, [body])

    def save_bodies_batch(self, system: str, bodies: list) -> None:
        """Insert/replace all bodies in a single transaction."""
        import json as _json
        _SQL = (
            "INSERT OR REPLACE INTO bodies"
            " (system, body_name, body_id, level, planet_class, star_type, atmosphere,"
            "  terraform, landable, bio_signals, geo_signals, bio_genuses, dist_ls, value,"
            "  first_discovered, first_mapped, mapped, fss_scanned, radius,"
            "  bio_value_min, bio_value_max,"
            "  semi_major_axis, orbital_period, mean_anomaly, eccentricity, orbital_inclination,"
            "  surface_gravity, materials, surface_temp, volcanism)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        params = [
            (
                system, b.name, b.body_id, b.level,
                b.planet_class, b.star_type, b.atmosphere,
                int(b.terraform), int(b.landable),
                b.bio_signals, b.geo_signals, "|".join(b.bio_genuses),
                b.dist_ls, b.value,
                int(b.first_discovered), int(b.first_mapped),
                int(b.mapped), int(b.fss_scanned), b.radius,
                b.bio_value_min, b.bio_value_max,
                b.semi_major_axis, b.orbital_period,
                b.mean_anomaly, b.eccentricity, b.orbital_inclination,
                b.surface_gravity,
                _json.dumps(b.materials) if b.materials else "",
                b.surface_temp, b.volcanism,
            )
            for b in bodies
        ]
        if not params:
            return
        with self._lock:
            self._conn.executemany(_SQL, params)
            self._conn.commit()

    def save_bio_scans(self, system: str, scans: list[BioScan], commander: str = "") -> None:
        _SQL = (
            "INSERT INTO bio_scans"
            " (system, body, species, commander, species_localised, genus_localised,"
            "  samples, min_dist, body_radius, value, complete,"
            "  first_discovered, first_footfall, sample_lats, sample_lons,"
            "  last_lat, last_lon, comp_lats, comp_lons)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        params = [
            (
                system, sc.body, sc.species, commander,
                sc.species_localised, sc.genus_localised,
                sc.samples, sc.min_dist, sc.body_radius, sc.value, int(sc.complete),
                int(sc.first_discovered), int(sc.first_footfall),
                "|".join(str(v) for v in sc.sample_lats),
                "|".join(str(v) for v in sc.sample_lons),
                sc.last_lat, sc.last_lon,
                "|".join(str(v) for v in sc.comp_lats),
                "|".join(str(v) for v in sc.comp_lons),
            )
            for sc in scans
        ]
        with self._lock:
            self._conn.execute(
                "DELETE FROM bio_scans WHERE system = ? AND commander = ?",
                (system, commander),
            )
            if params:
                self._conn.executemany(_SQL, params)
            self._conn.commit()

    def load_bio_scans(self, system: str, commander: str = "") -> list[BioScan]:
        with self._lock:
            if commander:
                rows = self._conn.execute(
                    """SELECT body, species, species_localised, genus_localised,
                              samples, min_dist, body_radius, value, complete,
                              first_discovered, first_footfall,
                              sample_lats, sample_lons, last_lat, last_lon,
                              comp_lats, comp_lons
                       FROM bio_scans
                       WHERE system = ? AND (commander = ? OR commander = '')""",
                    (system, commander),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT body, species, species_localised, genus_localised,
                              samples, min_dist, body_radius, value, complete,
                              first_discovered, first_footfall,
                              sample_lats, sample_lons, last_lat, last_lon,
                              comp_lats, comp_lons
                       FROM bio_scans WHERE system = ?""",
                    (system,),
                ).fetchall()
        result = []
        for row in rows:
            lats  = [float(v) for v in row[11].split("|") if v]
            lons  = [float(v) for v in row[12].split("|") if v]
            clats = [float(v) for v in row[15].split("|") if v]
            clons = [float(v) for v in row[16].split("|") if v]
            result.append(BioScan(
                body=row[0], species=row[1], species_localised=row[2], genus_localised=row[3],
                samples=int(row[4]), min_dist=float(row[5]), body_radius=float(row[6]),
                value=int(row[7]), complete=bool(row[8]),
                first_discovered=bool(row[9]), first_footfall=bool(row[10]),
                sample_lats=lats, sample_lons=lons,
                comp_lats=clats, comp_lons=clons,
                last_lat=row[13], last_lon=row[14],
                current_dist=None, alerted=False,
            ))
        return result

    def load_bodies(self, system: str) -> list[BodyInfo]:
        import json as _json
        with self._lock:
            rows = self._conn.execute(
                """SELECT body_name, body_id, level, planet_class, star_type, atmosphere,
                          terraform, landable, bio_signals, geo_signals, bio_genuses,
                          dist_ls, value, first_discovered, first_mapped, mapped, fss_scanned, radius,
                          bio_value_min, bio_value_max,
                          semi_major_axis, orbital_period, mean_anomaly, eccentricity, orbital_inclination,
                          surface_gravity,
                          COALESCE(materials, ''),
                          COALESCE(surface_temp, 0),
                          COALESCE(volcanism, '')
                   FROM bodies WHERE system = ?""",
                (system,),
            ).fetchall()
        from .events import predict_bio_genera as _pbg
        result = []
        for row in rows:
            genuses = [g for g in row[10].split("|") if g]
            mats_raw = row[26] or ""
            try:
                mats = _json.loads(mats_raw) if mats_raw else {}
            except Exception:
                mats = {}
            b = BodyInfo(
                name=row[0],      body_id=int(row[1]),   level=int(row[2]),
                planet_class=row[3], star_type=row[4],   atmosphere=row[5],
                terraform=bool(row[6]), landable=bool(row[7]),
                bio_signals=int(row[8]), geo_signals=int(row[9]),
                bio_genuses=genuses,
                dist_ls=float(row[11]), value=int(row[12]),
                first_discovered=bool(row[13]), first_mapped=bool(row[14]),
                mapped=bool(row[15]), fss_scanned=bool(row[16]), radius=float(row[17]),
                bio_value_min=int(row[18] or 0), bio_value_max=int(row[19] or 0),
                semi_major_axis=float(row[20] or 0), orbital_period=float(row[21] or 0),
                mean_anomaly=float(row[22] or 0), eccentricity=float(row[23] or 0),
                orbital_inclination=float(row[24] or 0),
                surface_gravity=float(row[25] or 0),
                materials=mats,
                surface_temp=float(row[27] or 0),
                volcanism=row[28] or "",
            )
            result.append(b)
        # Re-run bio prediction on load (not stored in DB; derived field)
        primary_star_type = next((b.star_type for b in result if b.star_type and b.level == 0), "")
        for b in result:
            if b.bio_signals > 0 and not b.bio_genuses and b.planet_class:
                b.bio_genuses_predicted = _pbg(
                    b.planet_class, b.atmosphere, b.surface_temp,
                    b.surface_gravity, b.volcanism, primary_star_type,
                )
        return result

    def increment_stat(self, stat: str, value: float = 1.0, commander: str = "") -> None:
        today = date.today().isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO stats (date, stat, value, commander) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(date, stat, commander) DO UPDATE SET value = value + excluded.value",
                (today, stat, float(value), commander),
            )
            self._conn.commit()

    # ── EDSM dump import ───────────────────────────────────────────────────────

    def import_edsm_systems_batch(self, rows: list) -> None:
        """INSERT OR REPLACE a batch of system rows into edsm_systems."""
        sql = (
            "INSERT OR REPLACE INTO edsm_systems"
            " (id64,name,x,y,z,allegiance,government,economy,population,security,power,power_state)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def upsert_edsm_powerplay_batch(self, rows: list) -> None:
        """Upsert power-play rows: insert new systems, update only power fields on existing ones."""
        sql = (
            "INSERT INTO edsm_systems"
            " (id64,name,x,y,z,allegiance,government,economy,population,security,power,power_state)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id64) DO UPDATE SET"
            "   power=excluded.power,"
            "   power_state=excluded.power_state"
            " WHERE excluded.power != ''"
        )
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def import_edsm_stations_batch(self, rows: list) -> None:
        """INSERT OR REPLACE a batch of station rows into edsm_stations."""
        sql = (
            "INSERT OR REPLACE INTO edsm_stations"
            " (id,name,system_id64,system_name,type,dist_ls,"
            "  allegiance,government,economy,"
            "  has_market,has_shipyard,has_outfitting,other_services)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    # ── EDSM dump queries ──────────────────────────────────────────────────────

    def get_system_power(self, name: str) -> tuple:
        """Return (power, power_state) for a system name, or ('', '')."""
        with self._lock:
            row = self._conn.execute(
                "SELECT power, power_state FROM edsm_systems WHERE name = ?",
                (name,),
            ).fetchone()
        return (row[0] or "", row[1] or "") if row else ("", "")

    def get_nearest_populated(
        self, x: float, y: float, z: float, exclude: str = ""
    ) -> Optional[tuple]:
        """Return (name, dist_ly, allegiance, government, economy, population) for
        the nearest populated system (population > 0) excluding *exclude*, or None."""
        with self._lock:
            row = self._conn.execute(
                """SELECT name,
                          (x-?1)*(x-?1)+(y-?2)*(y-?2)+(z-?3)*(z-?3) AS dist2,
                          allegiance, government, economy, population
                   FROM edsm_systems
                   WHERE name != ?4 AND population > 0
                   ORDER BY dist2
                   LIMIT 1""",
                (x, y, z, exclude),
            ).fetchone()
        if row:
            import math as _math
            dist = _math.sqrt(max(0.0, float(row[1])))
            return (row[0], round(dist, 1), row[2] or "", row[3] or "", row[4] or "", int(row[5]))
        return None

    def get_system_stations(self, system_name: str, limit: int = 4) -> list:
        """Return list of station dicts for a system, ordered by distance."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT name, type, dist_ls,
                          has_market, has_shipyard, has_outfitting, other_services
                   FROM edsm_stations
                   WHERE system_name = ?
                   ORDER BY dist_ls
                   LIMIT ?""",
                (system_name, limit),
            ).fetchall()
        return [
            {
                "name":       r[0],
                "type":       r[1],
                "dist_ls":    float(r[2]),
                "market":     bool(r[3]),
                "shipyard":   bool(r[4]),
                "outfitting": bool(r[5]),
                "services":   [s for s in r[6].split("|") if s] if r[6] else [],
            }
            for r in rows
        ]

    def get_systems_info_batch(self, names: list[str]) -> dict[str, dict]:
        """Return EDSM data for multiple system names. name → {x, y, z, population, allegiance}."""
        if not names:
            return {}
        placeholders = ",".join("?" * len(names))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT name, x, y, z, population, allegiance FROM edsm_systems WHERE name IN ({placeholders})",
                names,
            ).fetchall()
        return {
            row[0]: {
                "x":          float(row[1] or 0),
                "y":          float(row[2] or 0),
                "z":          float(row[3] or 0),
                "population": int(row[4] or 0),
                "allegiance": row[5] or "",
            }
            for row in rows
        }

    def get_route_edsm_cache(self, names: list[str]) -> dict[str, dict]:
        """Return cached EDSM live-lookup data for route systems. name → {known, scoopable, cached_at}."""
        if not names:
            return {}
        placeholders = ",".join("?" * len(names))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT name, known, scoopable, cached_at FROM edsm_route_cache WHERE name IN ({placeholders})",
                names,
            ).fetchall()
        return {
            row[0]: {"known": bool(row[1]), "scoopable": row[2], "cached_at": row[3]}
            for row in rows
        }

    def upsert_route_edsm_cache(self, entries: list[dict]) -> None:
        """Insert or replace route EDSM cache entries. Each entry: {name, known, scoopable, cached_at}."""
        if not entries:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO edsm_route_cache (name, known, scoopable, cached_at)"
                " VALUES (:name, :known, :scoopable, :cached_at)",
                entries,
            )
            self._conn.commit()

    def get_route_bodies_cache(self, names: list[str]) -> dict[str, dict]:
        """Return cached bio/geo/body data for route systems. name → {bio_count, geo_count, body_count, cached_at}."""
        if not names:
            return {}
        placeholders = ",".join("?" * len(names))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT system_name, bio_count, geo_count, body_count, cached_at"
                f" FROM edsm_route_bodies_cache WHERE system_name IN ({placeholders})",
                names,
            ).fetchall()
        return {
            row[0]: {"bio_count": row[1], "geo_count": row[2], "body_count": row[3], "cached_at": row[4]}
            for row in rows
        }

    def upsert_route_bodies_cache(self, entries: list[dict]) -> None:
        """Insert or replace route bodies cache. Each entry: {system_name, bio_count, geo_count, body_count, cached_at}."""
        if not entries:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO edsm_route_bodies_cache"
                " (system_name, bio_count, geo_count, body_count, cached_at)"
                " VALUES (:system_name, :bio_count, :geo_count, :body_count, :cached_at)",
                entries,
            )
            self._conn.commit()

    def get_stats(self, commander: str = "") -> dict:
        today       = date.today()
        week_ago    = (today - timedelta(days=6)).isoformat()
        month_start = today.replace(day=1).isoformat()
        year_start  = today.replace(month=1, day=1).isoformat()
        today_s     = today.isoformat()
        with self._lock:
            if commander:
                rows = self._conn.execute(
                    "SELECT date, stat, value FROM stats"
                    " WHERE (commander = ? OR commander = '')",
                    (commander,),
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT date, stat, value FROM stats").fetchall()
        result: dict = {}
        for date_s, stat, value in rows:
            if stat not in result:
                result[stat] = {"today": 0.0, "week": 0.0, "month": 0.0, "year": 0.0, "total": 0.0}
            r = result[stat]
            r["total"] += value
            if date_s >= year_start:  r["year"]  += value
            if date_s >= month_start: r["month"] += value
            if date_s >= week_ago:    r["week"]  += value
            if date_s == today_s:     r["today"] += value
        return result
