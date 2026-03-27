from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from .state import BioScan, BodyInfo, LogEvent


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
            "CREATE INDEX IF NOT EXISTS idx_stats_date ON stats(date)",
            "CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)",
        ]
        with self._lock:
            for sql in migrations:
                try:
                    self._conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            self._conn.commit()

    def insert(self, ev: LogEvent, system: str) -> None:
        event_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (timestamp, category, message, system, event_date)"
                " VALUES (?,?,?,?,?)",
                (ev.time, ev.category.label(), ev.message, system, event_date),
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

    def get_recent_events(self, limit: int) -> list[LogEvent]:
        from .state import EventCategory
        label_to_cat = {c.value: c for c in EventCategory}

        with self._lock:
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
        _SQL = (
            "INSERT OR REPLACE INTO bodies"
            " (system, body_name, body_id, level, planet_class, star_type, atmosphere,"
            "  terraform, landable, bio_signals, geo_signals, bio_genuses, dist_ls, value,"
            "  first_discovered, first_mapped, mapped, fss_scanned, radius,"
            "  bio_value_min, bio_value_max,"
            "  semi_major_axis, orbital_period, mean_anomaly, eccentricity, orbital_inclination,"
            "  surface_gravity)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
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
            )
            for b in bodies
        ]
        if not params:
            return
        with self._lock:
            self._conn.executemany(_SQL, params)
            self._conn.commit()

    def save_bio_scans(self, system: str, scans: list[BioScan]) -> None:
        _SQL = (
            "INSERT INTO bio_scans"
            " (system, body, species, species_localised, genus_localised,"
            "  samples, min_dist, body_radius, value, complete,"
            "  first_discovered, first_footfall, sample_lats, sample_lons, last_lat, last_lon)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        params = [
            (
                system, sc.body, sc.species, sc.species_localised, sc.genus_localised,
                sc.samples, sc.min_dist, sc.body_radius, sc.value, int(sc.complete),
                int(sc.first_discovered), int(sc.first_footfall),
                "|".join(str(v) for v in sc.sample_lats),
                "|".join(str(v) for v in sc.sample_lons),
                sc.last_lat, sc.last_lon,
            )
            for sc in scans
        ]
        with self._lock:
            self._conn.execute("DELETE FROM bio_scans WHERE system = ?", (system,))
            if params:
                self._conn.executemany(_SQL, params)
            self._conn.commit()

    def load_bio_scans(self, system: str) -> list[BioScan]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT body, species, species_localised, genus_localised,
                          samples, min_dist, body_radius, value, complete,
                          first_discovered, first_footfall,
                          sample_lats, sample_lons, last_lat, last_lon
                   FROM bio_scans WHERE system = ?""",
                (system,),
            ).fetchall()
        result = []
        for row in rows:
            lats = [float(v) for v in row[11].split("|") if v]
            lons = [float(v) for v in row[12].split("|") if v]
            result.append(BioScan(
                body=row[0], species=row[1], species_localised=row[2], genus_localised=row[3],
                samples=int(row[4]), min_dist=float(row[5]), body_radius=float(row[6]),
                value=int(row[7]), complete=bool(row[8]),
                first_discovered=bool(row[9]), first_footfall=bool(row[10]),
                sample_lats=lats, sample_lons=lons,
                last_lat=row[13], last_lon=row[14],
                current_dist=None, alerted=False,
            ))
        return result

    def load_bodies(self, system: str) -> list[BodyInfo]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT body_name, body_id, level, planet_class, star_type, atmosphere,
                          terraform, landable, bio_signals, geo_signals, bio_genuses,
                          dist_ls, value, first_discovered, first_mapped, mapped, fss_scanned, radius,
                          bio_value_min, bio_value_max,
                          semi_major_axis, orbital_period, mean_anomaly, eccentricity, orbital_inclination,
                          surface_gravity
                   FROM bodies WHERE system = ?""",
                (system,),
            ).fetchall()
        result = []
        for row in rows:
            genuses = [g for g in row[10].split("|") if g]
            result.append(BodyInfo(
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
            ))
        return result

    def increment_stat(self, stat: str, value: float = 1.0) -> None:
        today = date.today().isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO stats (date, stat, value) VALUES (?, ?, ?) "
                "ON CONFLICT(date, stat) DO UPDATE SET value = value + excluded.value",
                (today, stat, float(value)),
            )
            self._conn.commit()

    def get_stats(self) -> dict:
        today       = date.today()
        week_ago    = (today - timedelta(days=6)).isoformat()
        month_start = today.replace(day=1).isoformat()
        year_start  = today.replace(month=1, day=1).isoformat()
        today_s     = today.isoformat()
        with self._lock:
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
