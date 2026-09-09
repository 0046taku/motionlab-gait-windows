from __future__ import annotations

import numpy as np

from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseFrame, PoseLandmark
from motionlab_gait.privacy.face_anonymizer import FaceAnonymizer


def test_pose_face_fallback_and_blur() -> None:
    landmarks = tuple(
        PoseLandmark(
            index,
            name,
            0.45 + (index % 3) * 0.03,
            0.15 + (index % 4) * 0.02,
            0.0,
            0.9,
            0.9,
        )
        for index, name in enumerate(POSE_LANDMARK_NAMES)
    )
    box = FaceAnonymizer._pose_face_box(PoseFrame(0, 0, landmarks), 640, 480)
    assert box is not None
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    x, y, width, height = box
    frame[y : y + height, x : x + width] = np.random.default_rng(3).integers(
        0, 255, (height, width, 3), dtype=np.uint8
    )
    before = frame.copy()
    FaceAnonymizer._blur_box(frame, box)
    assert np.any(frame != before)


def test_box_scaling_and_overlap() -> None:
    assert FaceAnonymizer._scale_box((1, 2, 3, 4), 2.0) == (2, 4, 6, 8)
    assert FaceAnonymizer._intersection_over_union((0, 0, 10, 10), (5, 5, 10, 10)) > 0
