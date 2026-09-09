from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.persistence.database import Database


class VideoRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, video: VideoRecord) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO videos (
                    id, patient_id, original_name, stored_path, imported_at,
                    duration_ms, fps, frame_count, width, height,
                    pose_status, pose_path, pose_error, walking_condition,
                    affected_side, orthosis, walking_aid, known_distance_m,
                    distance_start_ms, distance_end_ms, anonymize_face,
                    processed_pose_path, result_path, anonymized_video_path,
                    quality_grade, analysis_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    video.id,
                    video.patient_id,
                    video.original_name,
                    str(video.stored_path),
                    video.imported_at.isoformat(),
                    video.duration_ms,
                    video.fps,
                    video.frame_count,
                    video.width,
                    video.height,
                    video.pose_status,
                    str(video.pose_path) if video.pose_path else None,
                    video.pose_error,
                    video.walking_condition,
                    video.affected_side,
                    video.orthosis,
                    video.walking_aid,
                    video.known_distance_m,
                    video.distance_start_ms,
                    video.distance_end_ms,
                    int(video.anonymize_face),
                    str(video.processed_pose_path) if video.processed_pose_path else None,
                    str(video.result_path) if video.result_path else None,
                    str(video.anonymized_video_path) if video.anonymized_video_path else None,
                    video.quality_grade,
                    video.analysis_version,
                ),
            )

    def list_for_patient(self, patient_id: str) -> list[VideoRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM videos
                WHERE patient_id = ?
                ORDER BY imported_at DESC
                """,
                (patient_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, video_id: str) -> VideoRecord | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def mark_pose_processing(self, video_id: str) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE videos
                SET pose_status = 'processing', pose_error = NULL
                WHERE id = ?
                """,
                (video_id,),
            )

    def mark_pose_ready(self, video_id: str, pose_path: Path) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE videos
                SET pose_status = 'ready', pose_path = ?, pose_error = NULL
                WHERE id = ?
                """,
                (str(pose_path), video_id),
            )

    def mark_analysis_ready(
        self,
        video_id: str,
        *,
        processed_pose_path: Path,
        result_path: Path,
        quality_grade: str,
        analysis_version: str,
        anonymized_video_path: Path | None = None,
    ) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE videos
                SET pose_status = 'ready', processed_pose_path = ?, result_path = ?,
                    quality_grade = ?, analysis_version = ?, anonymized_video_path = ?,
                    pose_error = NULL
                WHERE id = ?
                """,
                (
                    str(processed_pose_path),
                    str(result_path),
                    quality_grade,
                    analysis_version,
                    str(anonymized_video_path) if anonymized_video_path else None,
                    video_id,
                ),
            )

    def mark_pose_failed(self, video_id: str, message: str) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE videos
                SET pose_status = 'failed', pose_error = ?
                WHERE id = ?
                """,
                (message, video_id),
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> VideoRecord:
        raw_pose_path = row["pose_path"]
        processed_pose_path = row["processed_pose_path"]
        result_path = row["result_path"]
        anonymized_video_path = row["anonymized_video_path"]
        return VideoRecord(
            id=str(row["id"]),
            patient_id=str(row["patient_id"]),
            original_name=str(row["original_name"]),
            stored_path=Path(str(row["stored_path"])),
            imported_at=datetime.fromisoformat(str(row["imported_at"])),
            duration_ms=int(row["duration_ms"]),
            fps=float(row["fps"]),
            frame_count=int(row["frame_count"]),
            width=int(row["width"]),
            height=int(row["height"]),
            pose_status=str(row["pose_status"]),
            pose_path=Path(str(raw_pose_path)) if raw_pose_path else None,
            pose_error=str(row["pose_error"]) if row["pose_error"] else None,
            walking_condition=str(row["walking_condition"]),
            affected_side=str(row["affected_side"]),
            orthosis=str(row["orthosis"]),
            walking_aid=str(row["walking_aid"]),
            known_distance_m=(
                float(row["known_distance_m"]) if row["known_distance_m"] is not None else None
            ),
            distance_start_ms=(
                int(row["distance_start_ms"]) if row["distance_start_ms"] is not None else None
            ),
            distance_end_ms=(
                int(row["distance_end_ms"]) if row["distance_end_ms"] is not None else None
            ),
            anonymize_face=bool(row["anonymize_face"]),
            processed_pose_path=(Path(str(processed_pose_path)) if processed_pose_path else None),
            result_path=Path(str(result_path)) if result_path else None,
            anonymized_video_path=(
                Path(str(anonymized_video_path)) if anonymized_video_path else None
            ),
            quality_grade=str(row["quality_grade"]) if row["quality_grade"] else None,
            analysis_version=str(row["analysis_version"]),
        )
