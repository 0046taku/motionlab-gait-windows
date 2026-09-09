from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "MotionLab Gait"
APP_SLUG = "MotionLabGaitWindows"
MODEL_FILENAME = "pose_landmarker_full.task"
FACE_MODEL_FILENAME = "blaze_face_short_range.tflite"
MODEL_SOURCE_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/1/pose_landmarker_full.task"
)


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled).resolve() if bundled else project_root()


def default_data_root() -> Path:
    overridden = os.getenv("MOTIONLAB_DATA_DIR")
    if overridden:
        return Path(overridden).expanduser().resolve()
    # Keep the default data beside the app so the double-click launcher works
    # even when AppData is protected by Windows or a managed environment.
    return project_root() / "data"


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_root: Path
    database: Path
    videos: Path
    poses: Path
    model: Path
    face_model: Path

    @classmethod
    def create(cls, data_root: Path | None = None) -> AppPaths:
        root = (data_root or default_data_root()).resolve()
        videos = root / "videos"
        poses = root / "poses"
        root.mkdir(parents=True, exist_ok=True)
        videos.mkdir(parents=True, exist_ok=True)
        poses.mkdir(parents=True, exist_ok=True)
        bundled_model = resource_root() / "models" / MODEL_FILENAME
        return cls(
            data_root=root,
            database=root / "motionlab.sqlite3",
            videos=videos,
            poses=poses,
            model=bundled_model,
            face_model=resource_root() / "models" / FACE_MODEL_FILENAME,
        )
