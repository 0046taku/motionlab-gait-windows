from __future__ import annotations

from pathlib import Path
from typing import Any

from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseLandmark
from motionlab_gait.pose.base import PoseProvider


class MediaPipePoseProvider(PoseProvider):
    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(
                f"Poseモデルが見つかりません: {model_path}\n"
                "setup_windows.bat をもう一度実行してください。"
            )
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            raise RuntimeError("MediaPipeがインストールされていません。") from error

        self._mp = mp
        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_segmentation_masks=False,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def detect(self, rgb_frame: Any, timestamp_ms: int) -> tuple[PoseLandmark, ...]:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.pose_landmarks:
            return ()

        normalized = result.pose_landmarks[0]
        world = result.pose_world_landmarks[0] if result.pose_world_landmarks else []
        if len(normalized) != len(POSE_LANDMARK_NAMES):
            raise RuntimeError(f"Poseランドマーク数が33ではありません: {len(normalized)}")

        landmarks: list[PoseLandmark] = []
        for index, item in enumerate(normalized):
            world_item = world[index] if index < len(world) else None
            landmarks.append(
                PoseLandmark(
                    index=index,
                    name=POSE_LANDMARK_NAMES[index],
                    x=float(item.x),
                    y=float(item.y),
                    z=float(item.z),
                    visibility=float(item.visibility or 0.0),
                    presence=float(item.presence or 0.0),
                    world_x=float(world_item.x) if world_item is not None else None,
                    world_y=float(world_item.y) if world_item is not None else None,
                    world_z=float(world_item.z) if world_item is not None else None,
                )
            )
        return tuple(landmarks)

    def close(self) -> None:
        landmarker = getattr(self, "_landmarker", None)
        if landmarker is not None:
            landmarker.close()
            self._landmarker = None
