from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    patient_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    name TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    fps REAL NOT NULL,
                    frame_count INTEGER NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    pose_status TEXT NOT NULL DEFAULT 'pending',
                    pose_path TEXT,
                    pose_error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_videos_patient_imported
                    ON videos(patient_id, imported_at DESC);
                """
            )
            self._add_missing_columns(
                connection,
                "patients",
                {
                    "affected_side": "TEXT NOT NULL DEFAULT 'none'",
                    "diagnosis": "TEXT NOT NULL DEFAULT ''",
                    "onset_date": "TEXT",
                    "height_cm": "REAL",
                    "updated_at": "TEXT",
                },
            )
            self._add_missing_columns(
                connection,
                "videos",
                {
                    "walking_condition": "TEXT NOT NULL DEFAULT 'comfortable'",
                    "affected_side": "TEXT NOT NULL DEFAULT 'none'",
                    "orthosis": "TEXT NOT NULL DEFAULT 'none'",
                    "walking_aid": "TEXT NOT NULL DEFAULT 'none'",
                    "known_distance_m": "REAL",
                    "distance_start_ms": "INTEGER",
                    "distance_end_ms": "INTEGER",
                    "anonymize_face": "INTEGER NOT NULL DEFAULT 1",
                    "processed_pose_path": "TEXT",
                    "result_path": "TEXT",
                    "anonymized_video_path": "TEXT",
                    "quality_grade": "TEXT",
                    "analysis_version": "TEXT NOT NULL DEFAULT 'motionlab-gait-windows/0.4.0'",
                },
            )

    @staticmethod
    def _add_missing_columns(
        connection: sqlite3.Connection, table: str, definitions: dict[str, str]
    ) -> None:
        existing = {
            str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in definitions.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
