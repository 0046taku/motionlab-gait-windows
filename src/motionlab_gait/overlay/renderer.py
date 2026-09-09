from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from motionlab_gait.domain.models import PoseLandmark

POSE_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (17, 19),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (18, 20),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (29, 31),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (30, 32),
    (28, 32),
)


class SkeletonOverlayRenderer:
    def __init__(self, confidence_threshold: float = 0.35) -> None:
        self.confidence_threshold = confidence_threshold

    def draw(self, bgr_frame: Any, landmarks: Sequence[PoseLandmark]) -> Any:
        if not landmarks:
            return bgr_frame
        import cv2

        height, width = bgr_frame.shape[:2]
        by_index = {landmark.index: landmark for landmark in landmarks}

        for start_index, end_index in POSE_CONNECTIONS:
            start = by_index.get(start_index)
            end = by_index.get(end_index)
            if not start or not end or not self._visible(start) or not self._visible(end):
                continue
            start_point = (round(start.x * width), round(start.y * height))
            end_point = (round(end.x * width), round(end.y * height))
            cv2.line(bgr_frame, start_point, end_point, (55, 227, 168), 3, cv2.LINE_AA)

        for landmark in landmarks:
            if not self._visible(landmark):
                continue
            point = (round(landmark.x * width), round(landmark.y * height))
            cv2.circle(bgr_frame, point, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(bgr_frame, point, 5, (45, 110, 235), 1, cv2.LINE_AA)
        return bgr_frame

    def _visible(self, landmark: PoseLandmark) -> bool:
        return (
            landmark.visibility >= self.confidence_threshold
            and landmark.presence >= self.confidence_threshold
            and -0.2 <= landmark.x <= 1.2
            and -0.2 <= landmark.y <= 1.2
        )
