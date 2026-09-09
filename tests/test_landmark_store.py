from __future__ import annotations

import json
from pathlib import Path

from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseFrame, PoseLandmark
from motionlab_gait.persistence.landmark_store import LandmarkStore


def make_landmarks() -> tuple[PoseLandmark, ...]:
    return tuple(
        PoseLandmark(
            index=index,
            name=name,
            x=index / 32,
            y=0.5,
            z=-0.1,
            visibility=0.9,
            presence=0.8,
            world_x=0.1,
            world_y=0.2,
            world_z=0.3,
        )
        for index, name in enumerate(POSE_LANDMARK_NAMES)
    )


def test_landmark_jsonl_schema_and_timeline_lookup(tmp_path: Path) -> None:
    path = tmp_path / "pose.jsonl"
    frames = [
        PoseFrame(0, 0, make_landmarks()),
        PoseFrame(1, 33, make_landmarks()),
        PoseFrame(2, 67, ()),
    ]
    store = LandmarkStore()
    assert store.write(path, video_id="video", source_video_name="walk.mp4", frames=frames) == 3

    lines = path.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(lines[0])
    first_frame = json.loads(lines[1])
    assert metadata["schema"] == "motionlab.pose.v1"
    assert metadata["landmark_count"] == 33
    assert len(first_frame["landmarks"]) == 33
    assert first_frame["landmarks"][0]["presence"] == 0.8

    timeline = store.read(path)
    assert len(timeline) == 3
    assert timeline.nearest(30, tolerance_ms=10).timestamp_ms == 33
    assert timeline.nearest(200, tolerance_ms=20) is None
