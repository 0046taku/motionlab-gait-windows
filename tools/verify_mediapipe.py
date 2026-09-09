from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import cv2  # noqa: E402

from motionlab_gait.domain.models import VideoRecord  # noqa: E402
from motionlab_gait.persistence.landmark_store import LandmarkStore  # noqa: E402
from motionlab_gait.pose.mediapipe_provider import MediaPipePoseProvider  # noqa: E402
from motionlab_gait.services.pose_analysis_service import PoseAnalysisService  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/verify_mediapipe.py <full-body-image>")
        return 2
    image_path = Path(sys.argv[1]).resolve()
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    output_root = PROJECT_ROOT / ".test-output"
    output_root.mkdir(parents=True, exist_ok=True)
    video_path = output_root / "mediapipe_pose_check.avi"
    height, width = image.shape[:2]
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError("Cannot create verification video")
    for _ in range(8):
        writer.write(image)
    writer.release()

    video = VideoRecord(
        id="mediapipe-verification",
        patient_id="verification",
        original_name=video_path.name,
        stored_path=video_path,
        imported_at=datetime.now(UTC),
        duration_ms=800,
        fps=10.0,
        frame_count=8,
        width=width,
        height=height,
    )
    service = PoseAnalysisService(
        model_path=PROJECT_ROOT / "models" / "pose_landmarker_full.task",
        landmark_root=output_root / "poses",
        provider_factory=MediaPipePoseProvider,
    )
    summary = service.analyze(video)
    timeline = LandmarkStore().read(summary.output_path)
    detected = [frame for frame in timeline.frames if frame.landmarks]
    if not detected:
        raise AssertionError("MediaPipe did not detect a pose")
    if any(len(frame.landmarks) != 33 for frame in detected):
        raise AssertionError("Detected frame does not contain exactly 33 landmarks")
    if any(
        frame.timestamp_ms >= next_frame.timestamp_ms
        for frame, next_frame in zip(timeline.frames, timeline.frames[1:], strict=False)
    ):
        raise AssertionError("Frame timestamps are not strictly increasing")
    print(
        "MediaPipe video verification OK: "
        f"{summary.detected_frame_count}/{summary.frame_count} frames, 33 landmarks/frame"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
