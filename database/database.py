from __future__ import annotations

import csv
from contextlib import closing
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import (
    DATABASE_PATH,
    DEFAULT_CONDITION,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_PARTICIPANT_ID,
)


class RobotDatabase:
    """SQLite storage for profiles, schedules, HRI trials and chat history."""

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

    @staticmethod
    def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}

    def _migrate_trials(self, connection: sqlite3.Connection) -> None:
        columns = self._column_names(connection, "trials")
        additions = {
            "action": "TEXT NOT NULL DEFAULT 'acknowledged'",
            "schedule_id": "INTEGER",
            "source": "TEXT NOT NULL DEFAULT 'manual'",
            "profile_id": "INTEGER",
        }
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(f"ALTER TABLE trials ADD COLUMN {column} {definition}")

    def _migrate_schedules(self, connection: sqlite3.Connection) -> None:
        columns = self._column_names(connection, "schedules")
        if "profile_id" not in columns:
            connection.execute("ALTER TABLE schedules ADD COLUMN profile_id INTEGER")

    def _ensure_initial_profile(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT id FROM profiles ORDER BY id ASC LIMIT 1").fetchone()
        if row:
            first_profile_id = int(row["id"])
        else:
            settings = {
                str(item["key"]): str(item["value"])
                for item in connection.execute("SELECT key, value FROM settings").fetchall()
            }
            now = self._utc_now_iso()
            cursor = connection.execute(
                """
                INSERT INTO profiles(
                    participant_id, display_name, default_condition,
                    about_me, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    settings.get("participant_id", DEFAULT_PARTICIPANT_ID),
                    settings.get("display_name", DEFAULT_DISPLAY_NAME),
                    settings.get("default_condition", DEFAULT_CONDITION).upper(),
                    "",
                    now,
                    now,
                ),
            )
            first_profile_id = int(cursor.lastrowid)

        active_row = connection.execute(
            "SELECT value FROM settings WHERE key = 'active_profile_id'"
        ).fetchone()
        active_profile_id: int | None = None
        if active_row:
            try:
                candidate = int(active_row["value"])
                exists = connection.execute(
                    "SELECT 1 FROM profiles WHERE id = ?", (candidate,)
                ).fetchone()
                if exists:
                    active_profile_id = candidate
            except (TypeError, ValueError):
                active_profile_id = None

        if active_profile_id is None:
            active_profile_id = first_profile_id
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES('active_profile_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(active_profile_id),),
            )

        # Existing V2 schedules/trials belonged to the single legacy profile.
        connection.execute(
            "UPDATE schedules SET profile_id = ? WHERE profile_id IS NULL",
            (active_profile_id,),
        )
        connection.execute(
            "UPDATE trials SET profile_id = ? WHERE profile_id IS NULL",
            (active_profile_id,),
        )
        return active_profile_id

    def initialise(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL;")

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    default_condition TEXT NOT NULL DEFAULT 'HIGH',
                    about_me TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
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
                """
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER,
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
            self._migrate_schedules(connection)

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                )
                """
            )

            active_profile_id = self._ensure_initial_profile(connection)

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_participant ON trials(participant_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_profile ON trials(profile_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_started_at ON trials(started_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedules_profile_time ON schedules(profile_id, time_of_day)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_profile_id ON chat_messages(profile_id, id)"
            )

            # Keep legacy V2 settings aligned for backwards compatibility.
            active = connection.execute(
                "SELECT * FROM profiles WHERE id = ?", (active_profile_id,)
            ).fetchone()
            if active:
                for key, value in (
                    ("participant_id", active["participant_id"]),
                    ("display_name", active["display_name"]),
                    ("default_condition", active["default_condition"]),
                ):
                    connection.execute(
                        """
                        INSERT INTO settings(key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        (key, str(value)),
                    )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    @staticmethod
    def _profile_dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row else None

    def list_profiles(self) -> list[dict]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM profiles ORDER BY display_name COLLATE NOCASE, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_profile(self, profile_id: int) -> dict | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM profiles WHERE id = ?", (int(profile_id),)
            ).fetchone()
        return self._profile_dict(row)

    def get_active_profile_id(self) -> int:
        settings = self.get_settings()
        try:
            profile_id = int(settings.get("active_profile_id", ""))
        except ValueError:
            profile_id = 0
        if profile_id and self.get_profile(profile_id):
            return profile_id
        profiles = self.list_profiles()
        if not profiles:
            raise RuntimeError("No profiles are available.")
        profile_id = int(profiles[0]["id"])
        self.set_active_profile(profile_id)
        return profile_id

    def get_active_profile(self) -> dict:
        profile = self.get_profile(self.get_active_profile_id())
        if not profile:
            raise RuntimeError("Active profile not found.")
        return profile

    def set_active_profile(self, profile_id: int) -> dict:
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError("Profile not found.")
        self.set_settings(
            {
                "active_profile_id": str(profile_id),
                "participant_id": str(profile["participant_id"]),
                "display_name": str(profile["display_name"]),
                "default_condition": str(profile["default_condition"]),
            }
        )
        return profile

    def create_profile(
        self,
        *,
        participant_id: str,
        display_name: str,
        default_condition: str = "HIGH",
        about_me: str = "",
    ) -> int:
        now = self._utc_now_iso()
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute(
                    """
                    INSERT INTO profiles(
                        participant_id, display_name, default_condition,
                        about_me, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        participant_id,
                        display_name,
                        default_condition,
                        about_me,
                        now,
                        now,
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Participant / User ID must be unique.") from exc

    def update_profile(self, profile_id: int, **values) -> bool:
        current = self.get_profile(profile_id)
        if not current:
            return False
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """
                    UPDATE profiles
                    SET participant_id = ?, display_name = ?, default_condition = ?,
                        about_me = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        values.get("participant_id", current["participant_id"]),
                        values.get("display_name", current["display_name"]),
                        values.get("default_condition", current["default_condition"]),
                        values.get("about_me", current["about_me"]),
                        self._utc_now_iso(),
                        int(profile_id),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Participant / User ID must be unique.") from exc

        if int(profile_id) == self.get_active_profile_id():
            self.set_active_profile(int(profile_id))
        return True

    def delete_profile(self, profile_id: int) -> int:
        profiles = self.list_profiles()
        if len(profiles) <= 1:
            raise ValueError("At least one profile must remain.")
        if not self.get_profile(profile_id):
            raise ValueError("Profile not found.")

        active_id = self.get_active_profile_id()
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM chat_messages WHERE profile_id = ?", (int(profile_id),))
            connection.execute("DELETE FROM schedules WHERE profile_id = ?", (int(profile_id),))
            connection.execute("DELETE FROM profiles WHERE id = ?", (int(profile_id),))

        if active_id == int(profile_id):
            remaining = self.list_profiles()
            new_active = int(remaining[0]["id"])
            self.set_active_profile(new_active)
            return new_active
        return active_id

    # ------------------------------------------------------------------
    # HRI trials
    # ------------------------------------------------------------------

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
        profile_id: int | None = None,
    ) -> int:
        if profile_id is None:
            profile_id = self.get_active_profile_id()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO trials (
                    profile_id, participant_id, display_name, reminder_type,
                    condition_name, social_cue_count, cue_flags, started_at,
                    acknowledged_at, response_time_ms, acknowledged, notes,
                    action, schedule_id, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
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

    def recent_trials(self, limit: int = 20, profile_id: int | None = None) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 200)
        query = """
            SELECT id, profile_id, participant_id, display_name, reminder_type,
                   condition_name, social_cue_count, started_at, acknowledged_at,
                   response_time_ms, acknowledged, action, schedule_id, source, notes
            FROM trials
        """
        params: list[object] = []
        if profile_id is not None:
            query += " WHERE profile_id = ?"
            params.append(int(profile_id))
        query += " ORDER BY id DESC LIMIT ?"
        params.append(safe_limit)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def count_trials(self, profile_id: int | None = None) -> int:
        query = "SELECT COUNT(*) AS total FROM trials"
        params: tuple = ()
        if profile_id is not None:
            query += " WHERE profile_id = ?"
            params = (int(profile_id),)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(query, params).fetchone()
        return int(row["total"])

    def export_csv(self, profile_id: int | None = None) -> str:
        query = "SELECT * FROM trials"
        params: tuple = ()
        if profile_id is not None:
            query += " WHERE profile_id = ?"
            params = (int(profile_id),)
        query += " ORDER BY id ASC"
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, params).fetchall()

        output = io.StringIO(newline="")
        if not rows:
            output.write(
                "id,profile_id,participant_id,display_name,reminder_type,condition_name,"
                "social_cue_count,cue_flags,started_at,acknowledged_at,response_time_ms,"
                "acknowledged,notes,action,schedule_id,source\n"
            )
            return output.getvalue()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue()

    # ------------------------------------------------------------------
    # Schedules
    # ------------------------------------------------------------------

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

    def list_schedules(
        self,
        *,
        enabled_only: bool = False,
        profile_id: int | None = None,
    ) -> list[dict]:
        if profile_id is None:
            profile_id = self.get_active_profile_id()
        query = "SELECT * FROM schedules WHERE profile_id = ?"
        params: list[object] = [int(profile_id)]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY time_of_day ASC, id ASC"
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, tuple(params)).fetchall()
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
        profile_id: int | None = None,
    ) -> int:
        if profile_id is None:
            profile_id = self.get_active_profile_id()
        now = self._utc_now_iso()
        days_json = self._serialise_days(days_of_week)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO schedules(
                    profile_id, title, reminder_type, time_of_day, days_of_week,
                    message, condition_name, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(profile_id),
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
            cursor = connection.execute(
                "DELETE FROM schedules WHERE id = ?", (int(schedule_id),)
            )
            return cursor.rowcount > 0

    def replace_schedules(self, schedules: list[dict], profile_id: int | None = None) -> None:
        if profile_id is None:
            profile_id = self.get_active_profile_id()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM schedules WHERE profile_id = ?", (int(profile_id),)
            )
        for item in schedules:
            self.create_schedule(profile_id=profile_id, **item)

    def seed_schedules_if_needed(self, schedules: list[dict], profile_id: int | None = None) -> bool:
        if profile_id is None:
            profile_id = self.get_active_profile_id()
        if self.list_schedules(profile_id=profile_id):
            return False
        for item in schedules:
            self.create_schedule(profile_id=profile_id, **item)
        return True

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------

    def add_chat_message(self, profile_id: int, role: str, content: str) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported chat role.")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_messages(profile_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(profile_id), role, content, self._utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def chat_history(self, profile_id: int, limit: int = 30) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 200)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT id, profile_id, role, content, created_at
                FROM chat_messages
                WHERE profile_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(profile_id), safe_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_chat(self, profile_id: int) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE profile_id = ?", (int(profile_id),)
            )
