from __future__ import annotations

from motionlab_gait.config import AppPaths
from motionlab_gait.pose.mediapipe_provider import MediaPipePoseProvider


def verify_model_initialization(paths: AppPaths) -> None:
    with MediaPipePoseProvider(paths.model):
        pass

    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    options = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=str(paths.face_model)),
        running_mode=vision.RunningMode.VIDEO,
    )
    with vision.FaceDetector.create_from_options(options):
        pass
