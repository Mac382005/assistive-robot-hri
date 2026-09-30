from __future__ import annotations

import csv
from contextlib import closing
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_PATH


class RobotDatabase:
    def __init__(self, db_path: Path | str = DATABASE_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _column_names(self, connection: sqlite3.Connection, table: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}

    def _migrate_trials(self, connection: sqlite3.Connection) -> None:
        columns = self._column_names(connection, "trials")
        additions = {
            "action": "TEXT NOT NULL DEFAULT 'acknowledged'",
            "schedule_id": "INTEGER",
            "source": "TEXT NOT NULL DEFAULT 'manual'",
        }
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(f"ALTER TABLE trials ADD COLUMN {column} {definition}")

    def initialise(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL;")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id TEXT NOT NULL,
                    display_name TEXT,
                    reminder_type TEXT NOT NULL,
                    condition_name TEXT NOT NULL,
                    social_cue_count INTEGER NOT NULL,
                    cue_flags TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL,
                    response_time_ms INTEGER NOT NULL CHECK(response_time_ms >= 0),
                    acknowledged INTEGER NOT NULL DEFAULT 1,
                    notes TEXT DEFAULT '',
                    action TEXT NOT NULL DEFAULT 'acknowledged',
                    schedule_id INTEGER,
                    source TEXT NOT NULL DEFAULT 'manual'
                )
                """
            )
            self._migrate_trials(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_participant ON trials(participant_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_started_at ON trials(started_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    time_of_day TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    condition_name TEXT NOT NULL DEFAULT 'HIGH',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedules_time ON schedules(time_of_day)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def save_trial(
        self,
        *,
        participant_id: str,
        display_name: str,
        reminder_type: str,
        condition_name: str,
        social_cue_count: int,
        cue_flags: dict,
        started_at: str,
        acknowledged_at: str,
        response_time_ms: int,
        notes: str = "",
        acknowledged: bool = True,
        action: str = "acknowledged",
        schedule_id: int | None = None,
        source: str = "manual",
    ) -> int:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO trials (
                    participant_id,
                    display_name,
                    reminder_type,
                    condition_name,
                    social_cue_count,
                    cue_flags,
                    started_at,
                    acknowledged_at,
                    response_time_ms,
                    acknowledged,
                    notes,
                    action,
                    schedule_id,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_id,
                    display_name,
                    reminder_type,
                    condition_name,
                    social_cue_count,
                    json.dumps(cue_flags, separators=(",", ":")),
                    started_at,
                    acknowledged_at,
                    response_time_ms,
                    1 if acknowledged else 0,
                    notes,
                    action,
                    schedule_id,
                    source,
                ),
            )
            return int(cursor.lastrowid)

    def recent_trials(self, limit: int = 20) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 200)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, participant_id, display_name, reminder_type,
                       condition_name, social_cue_count, started_at,
                       acknowledged_at, response_time_ms, acknowledged,
                       action, schedule_id, source, notes
                FROM trials
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_trials(self) -> int:
        with closing(self._connect()) as connection, connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM trials").fetchone()
        return int(row["total"])

    def export_csv(self) -> str:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT * FROM trials ORDER BY id ASC").fetchall()

        output = io.StringIO(newline="")
        if not rows:
            output.write(
                "id,participant_id,display_name,reminder_type,condition_name,"
                "social_cue_count,cue_flags,started_at,acknowledged_at,"
                "response_time_ms,acknowledged,notes,action,schedule_id,source\n"
            )
            return output.getvalue()

        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue()

    def get_settings(self) -> dict[str, str]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def set_settings(self, values: dict[str, str]) -> None:
        if not values:
            return
        with closing(self._connect()) as connection, connection:
            for key, value in values.items():
                connection.execute(
                    """
                    INSERT INTO settings(key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(key), str(value)),
                )

    @staticmethod
    def _serialise_days(days_of_week: list[int]) -> str:
        normalised = sorted({int(day) for day in days_of_week if 0 <= int(day) <= 6})
        if not normalised:
            raise ValueError("At least one day must be selected.")
        return json.dumps(normalised, separators=(",", ":"))

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> dict:
        payload = dict(row)
        payload["days_of_week"] = json.loads(payload["days_of_week"])
        payload["enabled"] = bool(payload["enabled"])
        return payload

    def list_schedules(self, *, enabled_only: bool = False) -> list[dict]:
        query = "SELECT * FROM schedules"
        params: tuple = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY time_of_day ASC, id ASC"
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_schedule(row) for row in rows]

    def get_schedule(self, schedule_id: int) -> dict | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM schedules WHERE id = ?", (int(schedule_id),)
            ).fetchone()
        return self._row_to_schedule(row) if row else None

    def create_schedule(
        self,
        *,
        title: str,
        reminder_type: str,
        time_of_day: str,
        days_of_week: list[int],
        message: str,
        condition_name: str,
        enabled: bool,
    ) -> int:
        now = self._utc_now_iso()
        days_json = self._serialise_days(days_of_week)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO schedules(
                    title, reminder_type, time_of_day, days_of_week,
                    message, condition_name, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    reminder_type,
                    time_of_day,
                    days_json,
                    message,
                    condition_name,
                    1 if enabled else 0,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def update_schedule(self, schedule_id: int, **values) -> bool:
        current = self.get_schedule(schedule_id)
        if not current:
            return False
        fields = {
            "title": values.get("title", current["title"]),
            "reminder_type": values.get("reminder_type", current["reminder_type"]),
            "time_of_day": values.get("time_of_day", current["time_of_day"]),
            "days_of_week": self._serialise_days(values.get("days_of_week", current["days_of_week"])),
            "message": values.get("message", current["message"]),
            "condition_name": values.get("condition_name", current["condition_name"]),
            "enabled": 1 if values.get("enabled", current["enabled"]) else 0,
            "updated_at": self._utc_now_iso(),
        }
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE schedules
                SET title = ?, reminder_type = ?, time_of_day = ?, days_of_week = ?,
                    message = ?, condition_name = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    fields["title"],
                    fields["reminder_type"],
                    fields["time_of_day"],
                    fields["days_of_week"],
                    fields["message"],
                    fields["condition_name"],
                    fields["enabled"],
                    fields["updated_at"],
                    int(schedule_id),
                ),
            )
        return True

    def delete_schedule(self, schedule_id: int) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM schedules WHERE id = ?", (int(schedule_id),))
            return cursor.rowcount > 0

    def replace_schedules(self, schedules: list[dict]) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM schedules")
        for item in schedules:
            self.create_schedule(**item)

    def seed_schedules_if_needed(self, schedules: list[dict]) -> bool:
        settings = self.get_settings()
        if settings.get("demo_schedule_seeded") == "1":
            return False
        if not self.list_schedules():
            for item in schedules:
                self.create_schedule(**item)
        self.set_settings({"demo_schedule_seeded": "1"})
        return True

