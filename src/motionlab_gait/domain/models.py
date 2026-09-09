from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Patient:
    id: str
    patient_code: str
    name: str
    notes: str
    created_at: datetime
    affected_side: str = "none"
    diagnosis: str = ""
    onset_date: str | None = None
    height_cm: float | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VideoRecord:
    id: str
    patient_id: str
    original_name: str
    stored_path: Path
    imported_at: datetime
    duration_ms: int
    fps: float
    frame_count: int
    width: int
    height: int
    pose_status: str = "pending"
    pose_path: Path | None = None
    pose_error: str | None = None
    walking_condition: str = "comfortable"
    affected_side: str = "none"
    orthosis: str = "none"
    walking_aid: str = "none"
    known_distance_m: float | None = None
    distance_start_ms: int | None = None
    distance_end_ms: int | None = None
    anonymize_face: bool = True
    processed_pose_path: Path | None = None
    result_path: Path | None = None
    anonymized_video_path: Path | None = None
    quality_grade: str | None = None
    analysis_version: str = "motionlab-gait-windows/0.4.0"


@dataclass(frozen=True, slots=True)
class PoseLandmark:
    index: int
    name: str
    x: float
    y: float
    z: float
    visibility: float
    presence: float
    world_x: float | None = None
    world_y: float | None = None
    world_z: float | None = None
    interpolated: bool = False
    outlier_replaced: bool = False

    def to_dict(self) -> dict[str, int | float | str | None]:
        return {
            "index": self.index,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "visibility": self.visibility,
            "presence": self.presence,
            "world_x": self.world_x,
            "world_y": self.world_y,
            "world_z": self.world_z,
            "interpolated": self.interpolated,
            "outlier_replaced": self.outlier_replaced,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> PoseLandmark:
        def optional_float(key: str) -> float | None:
            raw = value.get(key)
            return None if raw is None else float(raw)

        return cls(
            index=int(value["index"]),
            name=str(value["name"]),
            x=float(value["x"]),
            y=float(value["y"]),
            z=float(value["z"]),
            visibility=float(value.get("visibility", 0.0)),
            presence=float(value.get("presence", 0.0)),
            world_x=optional_float("world_x"),
            world_y=optional_float("world_y"),
            world_z=optional_float("world_z"),
            interpolated=bool(value.get("interpolated", False)),
            outlier_replaced=bool(value.get("outlier_replaced", False)),
        )


@dataclass(frozen=True, slots=True)
class PoseFrame:
    frame_index: int
    timestamp_ms: int
    landmarks: tuple[PoseLandmark, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "frame",
            "frame_index": self.frame_index,
            "timestamp_ms": self.timestamp_ms,
            "landmarks": [landmark.to_dict() for landmark in self.landmarks],
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> PoseFrame:
        raw_landmarks = value.get("landmarks", [])
        if not isinstance(raw_landmarks, list):
            raise ValueError("landmarks must be a list")
        return cls(
            frame_index=int(value["frame_index"]),
            timestamp_ms=int(value["timestamp_ms"]),
            landmarks=tuple(PoseLandmark.from_dict(item) for item in raw_landmarks),
        )


POSE_LANDMARK_NAMES: tuple[str, ...] = (
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
)
