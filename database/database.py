from __future__ import annotations

import csv
import io
import json
import sqlite3
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

    def initialise(self) -> None:
        with self._connect() as connection:
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
                    notes TEXT DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_participant ON trials(participant_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trials_started_at ON trials(started_at)"
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
    ) -> int:
        with self._connect() as connection:
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
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
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
                    notes,
                ),
            )
            return int(cursor.lastrowid)

    def recent_trials(self, limit: int = 20) -> list[dict]:
        safe_limit = min(max(int(limit), 1), 200)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, participant_id, display_name, reminder_type,
                       condition_name, social_cue_count, started_at,
                       acknowledged_at, response_time_ms, acknowledged, notes
                FROM trials
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_trials(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM trials").fetchone()
        return int(row["total"])

    def export_csv(self) -> str:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trials ORDER BY id ASC"
            ).fetchall()

        output = io.StringIO(newline="")
        if not rows:
            output.write(
                "id,participant_id,display_name,reminder_type,condition_name,"
                "social_cue_count,cue_flags,started_at,acknowledged_at,"
                "response_time_ms,acknowledged,notes\n"
            )
            return output.getvalue()

        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue()
