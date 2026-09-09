from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseLandmark, VideoRecord
from motionlab_gait.overlay.renderer import SkeletonOverlayRenderer
from motionlab_gait.persistence.landmark_store import LandmarkStore
from motionlab_gait.pose.base import PoseProvider
from motionlab_gait.services.pose_analysis_service import PoseAnalysisService
from motionlab_gait.services.video_service import VideoService


class FakePoseProvider(PoseProvider):
    def __init__(self, _model_path: Path) -> None:
        self.closed = False

    def detect(self, rgb_frame, timestamp_ms: int) -> tuple[PoseLandmark, ...]:
        del rgb_frame, timestamp_ms
        return tuple(
            PoseLandmark(index, name, 0.25 + index * 0.01, 0.5, 0.0, 1.0, 1.0)
            for index, name in enumerate(POSE_LANDMARK_NAMES)
        )

    def close(self) -> None:
        self.closed = True


def create_test_video(path: Path, frame_count: int = 5) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    assert writer.isOpened()
    for index in range(frame_count):
        frame = np.full((120, 160, 3), index * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_video_import_and_pose_analysis_are_separate(tmp_path: Path) -> None:
    source = tmp_path / "source.avi"
    create_test_video(source)
    video_service = VideoService(tmp_path / "stored")
    imported = video_service.import_for_patient(source, "patient-1")
    assert imported.stored_path.is_file()
    assert imported.frame_count == 5
    assert imported.patient_id == "patient-1"

    analysis = PoseAnalysisService(
        model_path=tmp_path / "fake.task",
        landmark_root=tmp_path / "poses",
        provider_factory=FakePoseProvider,
    )
    progress: list[tuple[int, int]] = []
    summary = analysis.analyze(
        imported,
        progress=lambda current, total: progress.append((current, total)),
    )
    assert summary.frame_count == 5
    assert summary.detected_frame_count == 5
    assert progress[-1] == (5, 5)

    timeline = LandmarkStore().read(summary.output_path)
    assert len(timeline.frames[0].landmarks) == 33
    timestamps = [frame.timestamp_ms for frame in timeline.frames]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_overlay_changes_pixels_for_visible_landmarks() -> None:
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    video = VideoRecord(
        id="v",
        patient_id="p",
        original_name="x.mp4",
        stored_path=Path("x.mp4"),
        imported_at=datetime.now(UTC),
        duration_ms=100,
        fps=30.0,
        frame_count=3,
        width=300,
        height=200,
    )
    del video
    landmarks = tuple(
        PoseLandmark(index, name, 0.2 + (index % 5) * 0.1, 0.2 + (index % 7) * 0.08, 0, 1, 1)
        for index, name in enumerate(POSE_LANDMARK_NAMES)
    )
    result = SkeletonOverlayRenderer().draw(frame, landmarks)
    assert np.count_nonzero(result) > 0
