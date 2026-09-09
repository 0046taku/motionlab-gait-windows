from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from motionlab_gait.domain.models import Patient, VideoRecord
from motionlab_gait.persistence.database import Database
from motionlab_gait.persistence.patient_repository import (
    DuplicatePatientCodeError,
    PatientRepository,
)
from motionlab_gait.persistence.video_repository import VideoRepository


def test_patient_and_video_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialize()
    patients = PatientRepository(database)
    videos = VideoRepository(database)

    patient = patients.create("PT-001", "テスト患者", "メモ")
    loaded_patient = patients.get(patient.id)
    assert loaded_patient == patient

    video = VideoRecord(
        id="video-1",
        patient_id=patient.id,
        original_name="walk.mp4",
        stored_path=tmp_path / "walk.mp4",
        imported_at=datetime.now(UTC),
        duration_ms=1000,
        fps=30.0,
        frame_count=30,
        width=640,
        height=480,
    )
    videos.add(video)
    loaded_video = videos.get(video.id)
    assert loaded_video == video

    pose_path = tmp_path / "video-1.pose.jsonl"
    videos.mark_pose_ready(video.id, pose_path)
    ready = videos.get(video.id)
    assert ready == replace(video, pose_status="ready", pose_path=pose_path)


def test_patient_code_is_case_insensitively_unique(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialize()
    patients = PatientRepository(database)
    patients.create("PT-001", "A")

    with pytest.raises(DuplicatePatientCodeError):
        patients.create("pt-001", "B")


def test_patient_dataclass_has_expected_fields() -> None:
    patient = Patient("id", "code", "name", "notes", datetime.now(UTC))
    assert patient.patient_code == "code"


def test_patient_input_lengths_are_validated(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialize()
    patients = PatientRepository(database)
    with pytest.raises(ValueError, match="64文字"):
        patients.create("X" * 65, "name")


def test_phase3_database_is_migrated_without_losing_rows(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE patients (
            id TEXT PRIMARY KEY, patient_code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE videos (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            original_name TEXT NOT NULL, stored_path TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, fps REAL NOT NULL,
            frame_count INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            pose_status TEXT NOT NULL DEFAULT 'pending', pose_path TEXT, pose_error TEXT
        );
        INSERT INTO patients VALUES (
            'p', 'LEGACY-1', '以前の患者', '',
            '2026-01-01T00:00:00+00:00'
        );
        """
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()
    loaded = PatientRepository(database).get("p")
    assert loaded is not None
    assert loaded.patient_code == "LEGACY-1"
    assert loaded.affected_side == "none"
