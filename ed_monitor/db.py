from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .state import BodyInfo, LogEvent


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
        genuses = "|".join(body.bio_genuses)
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO bodies
                   (system, body_name, body_id, level, planet_class, star_type, atmosphere,
                    terraform, landable, bio_signals, geo_signals, bio_genuses, dist_ls, value,
                    first_discovered, first_mapped, mapped, fss_scanned, radius)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    system, body.name, body.body_id, body.level,
                    body.planet_class, body.star_type, body.atmosphere,
                    int(body.terraform), int(body.landable),
                    body.bio_signals, body.geo_signals, genuses,
                    body.dist_ls, body.value,
                    int(body.first_discovered), int(body.first_mapped),
                    int(body.mapped), int(body.fss_scanned), body.radius,
                ),
            )
            self._conn.commit()

    def load_bodies(self, system: str) -> list[BodyInfo]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT body_name, body_id, level, planet_class, star_type, atmosphere,
                          terraform, landable, bio_signals, geo_signals, bio_genuses,
                          dist_ls, value, first_discovered, first_mapped, mapped, fss_scanned, radius
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
            ))
        return result
