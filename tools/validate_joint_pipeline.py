from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from motionlab_gait.analysis.engine import GaitAnalysisEngine
from motionlab_gait.analysis.types import AnglePoint
from motionlab_gait.persistence.database import Database
from motionlab_gait.persistence.landmark_store import LandmarkStore
from motionlab_gait.persistence.video_repository import VideoRepository

SEGMENTS = {
    "hip_flexion": {"left": (11, 23, 25), "right": (12, 24, 26)},
    "knee_flexion": {"left": (23, 25, 27), "right": (24, 26, 28)},
    "ankle_dorsiflexion": {
        "left": (25, 27, 29, 31),
        "right": (26, 28, 30, 32),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate all joint-angle pipelines")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--knee-baseline", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = Database(args.data_root.resolve() / "motionlab.sqlite3")
    repository = VideoRepository(database)
    with database.connection() as connection:
        row = connection.execute(
            "SELECT id FROM videos WHERE pose_path IS NOT NULL ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("Pose解析済み動画がありません。")
    video = repository.get(str(row["id"]))
    if video is None or video.pose_path is None:
        raise RuntimeError("動画またはRaw Poseが見つかりません。")

    copied_raw = output / f"{video.id}.pose.jsonl"
    shutil.copy2(video.pose_path, copied_raw)
    processed_path, result_path, result = GaitAnalysisEngine().analyze(video, copied_raw)

    summary: dict[str, object] = {
        "analysis_version": result.analysis_version,
        "video_id": result.video_id,
        "viewpoint": asdict(result.viewpoint),
        "joints": {},
        "knee_regression": _compare_knee(result.angles, args.knee_baseline),
        "representative_frames": {},
    }
    quality = {item.joint: item for item in result.joint_quality}
    joints = summary["joints"]
    assert isinstance(joints, dict)
    for joint in SEGMENTS:
        joint_output: dict[str, object] = {
            "quality": asdict(quality[joint]),
            "sides": {},
        }
        for side in ("left", "right"):
            raw = _select(result.raw_angles, joint, side)
            filtered = _select(result.angles, joint, side)
            joint_output["sides"][side] = {
                "raw": _angle_summary(raw),
                "filtered": _angle_summary(filtered),
                "raw_jitter": _jitter(raw),
                "filtered_jitter": _jitter(filtered),
            }
        joints[joint] = joint_output
        image = _render_representative(
            video.stored_path,
            processed_path,
            result.angles,
            joint,
            output,
        )
        summary["representative_frames"][joint] = str(image) if image else None

    summary_path = output / "joint-validation.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"RESULT={result_path}")
    print(f"SUMMARY={summary_path}")
    return 0


def _select(
    angles: tuple[AnglePoint, ...], joint: str, side: str
) -> list[AnglePoint]:
    return [
        point
        for point in angles
        if point.joint == joint and point.side == side and point.cycle_percent is not None
    ]


def _angle_summary(points: list[AnglePoint]) -> dict[str, float | int | None]:
    values = [point.angle_degrees for point in points]
    if not values:
        return {"count": 0, "minimum": None, "maximum": None, "rom": None}
    minimum = min(values)
    maximum = max(values)
    return {
        "count": len(values),
        "minimum": round(minimum, 3),
        "maximum": round(maximum, 3),
        "rom": round(maximum - minimum, 3),
    }


def _jitter(points: list[AnglePoint]) -> dict[str, float | None]:
    ordered = sorted(points, key=lambda point: point.timestamp_ms)
    differences = np.asarray(
        [
            abs(later.angle_degrees - earlier.angle_degrees)
            for earlier, later in zip(ordered, ordered[1:], strict=False)
            if later.timestamp_ms > earlier.timestamp_ms
        ],
        dtype=float,
    )
    if not len(differences):
        return {"median_frame_change": None, "p95_frame_change": None}
    return {
        "median_frame_change": round(float(np.median(differences)), 3),
        "p95_frame_change": round(float(np.percentile(differences, 95)), 3),
    }


def _compare_knee(
    current: tuple[AnglePoint, ...], baseline_path: Path | None
) -> dict[str, object]:
    if baseline_path is None or not baseline_path.is_file():
        return {"available": False}
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))["knee_angles"]
    current_knee = [asdict(point) for point in current if point.joint == "knee_flexion"]
    return {
        "available": True,
        "exact_match": current_knee == baseline,
        "baseline_points": len(baseline),
        "current_points": len(current_knee),
    }


def _render_representative(
    video_path: Path,
    processed_path: Path,
    angles: tuple[AnglePoint, ...],
    joint: str,
    output: Path,
) -> Path | None:
    points = [
        point for point in angles if point.joint == joint and point.cycle_percent is not None
    ]
    if not points or not video_path.is_file():
        return None
    representative = max(points, key=lambda point: point.angle_degrees)
    timeline = LandmarkStore().read(processed_path)
    pose_frame = timeline.nearest(representative.timestamp_ms, tolerance_ms=80)
    if pose_frame is None:
        return None
    capture = cv2.VideoCapture(str(video_path))
    capture.set(cv2.CAP_PROP_POS_MSEC, representative.timestamp_ms)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        return None
    height, width = frame.shape[:2]
    landmarks = {item.index: item for item in pose_frame.landmarks}
    indices = SEGMENTS[joint][representative.side]
    required = [landmarks.get(index) for index in indices]
    if any(item is None for item in required):
        return None
    pixel_points = [
        (round(item.x * width), round(item.y * height))
        for item in required
        if item is not None
    ]
    for first, second in zip(pixel_points, pixel_points[1:], strict=False):
        cv2.line(frame, first, second, (0, 220, 255), max(3, width // 500))
    for point in pixel_points:
        cv2.circle(frame, point, max(5, width // 300), (30, 60, 255), -1)
    text = (
        f"{joint} {representative.side} {representative.angle_degrees:.1f} deg "
        f"at {representative.timestamp_ms / 1000:.2f} s"
    )
    cv2.putText(
        frame,
        text,
        (40, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.8, width / 1800),
        (255, 255, 255),
        max(2, width // 800),
        cv2.LINE_AA,
    )
    target = output / f"representative-{joint}.jpg"
    cv2.imwrite(str(target), frame)
    return target


if __name__ == "__main__":
    raise SystemExit(main())
