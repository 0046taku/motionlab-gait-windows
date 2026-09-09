from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

import numpy as np

from motionlab_gait.analysis.kinematics import calculate_joint_angles
from motionlab_gait.analysis.types import AnglePoint, GaitCycle, JointQualityReport
from motionlab_gait.domain.models import PoseFrame

JOINT_LANDMARKS: dict[str, dict[str, tuple[int, ...]]] = {
    "hip_flexion": {"left": (11, 23, 25), "right": (12, 24, 26)},
    "knee_flexion": {"left": (23, 25, 27), "right": (24, 26, 28)},
    "ankle_dorsiflexion": {
        "left": (25, 27, 29, 31),
        "right": (26, 28, 30, 32),
    },
}


@dataclass(frozen=True, slots=True)
class JointAnalysisBundle:
    filtered_angles: tuple[AnglePoint, ...]
    raw_angles: tuple[AnglePoint, ...]
    quality: tuple[JointQualityReport, ...]
    debug: dict[str, object]


class JointAnglePipeline:
    """One auditable path from landmarks to normalized angles for every joint.

    Landmark rejection, short-gap interpolation and smoothing happen upstream in
    LandmarkProcessor. This class deliberately calls the same angle and gait-cycle
    normalization function for hip, knee and ankle; only their anatomical angle
    definitions remain joint-specific in kinematics.calculate_joint_angles.
    """

    def analyze(
        self,
        raw_frames: tuple[PoseFrame, ...],
        filtered_frames: tuple[PoseFrame, ...],
        cycles: tuple[GaitCycle, ...],
        *,
        direction: str,
    ) -> JointAnalysisBundle:
        filtered = calculate_joint_angles(filtered_frames, cycles, direction=direction)
        raw = calculate_joint_angles(raw_frames, cycles, direction=direction)
        assessments = tuple(
            self._assess_joint(
                joint,
                raw_frames,
                filtered_frames,
                filtered,
                cycles,
                direction,
            )
            for joint in JOINT_LANDMARKS
        )
        quality = tuple(item[0] for item in assessments)
        valid_cycle_keys = {
            joint: assessments[index][1] for index, joint in enumerate(JOINT_LANDMARKS)
        }
        filtered = self._exclude_invalid_cycle_points(filtered, valid_cycle_keys, cycles)
        raw = self._exclude_invalid_cycle_points(raw, valid_cycle_keys, cycles)
        return JointAnalysisBundle(
            filtered_angles=filtered,
            raw_angles=raw,
            quality=quality,
            debug=self._debug_summary(raw, filtered, quality),
        )

    @staticmethod
    def _assess_joint(
        joint: str,
        raw_frames: tuple[PoseFrame, ...],
        filtered_frames: tuple[PoseFrame, ...],
        angles: tuple[AnglePoint, ...],
        cycles: tuple[GaitCycle, ...],
        direction: str,
    ) -> tuple[JointQualityReport, frozenset[tuple[str, int, int]]]:
        expected_landmarks = max(
            1,
            len(raw_frames) * sum(len(value) for value in JOINT_LANDMARKS[joint].values()),
        )
        expected_joint_frames = max(1, len(filtered_frames) * 2)
        visibility: list[float] = []
        presence: list[float] = []
        outliers = 0
        interpolated = 0
        complete_joint_frames = 0

        for raw_frame, filtered_frame in zip(raw_frames, filtered_frames, strict=False):
            raw_by_index = {item.index: item for item in raw_frame.landmarks}
            filtered_by_index = {item.index: item for item in filtered_frame.landmarks}
            for indices in JOINT_LANDMARKS[joint].values():
                raw_required = [raw_by_index.get(index) for index in indices]
                filtered_required = [filtered_by_index.get(index) for index in indices]
                visibility.extend(
                    item.visibility if item is not None else 0.0 for item in raw_required
                )
                presence.extend(item.presence if item is not None else 0.0 for item in raw_required)
                outliers += sum(
                    bool(item and item.outlier_replaced) for item in filtered_required
                )
                interpolated += sum(
                    bool(item and item.interpolated) for item in filtered_required
                )
                complete_joint_frames += int(all(item is not None for item in filtered_required))

        joint_angles = tuple(
            point
            for point in angles
            if point.joint == joint and point.cycle_percent is not None
        )
        valid_cycle_keys: set[tuple[str, int, int]] = set()
        expected_cycle_samples = 0
        for cycle in cycles:
            cycle_frames = tuple(
                (raw_frame, filtered_frame)
                for raw_frame, filtered_frame in zip(
                    raw_frames, filtered_frames, strict=False
                )
                if cycle.start_ms <= filtered_frame.timestamp_ms <= cycle.end_ms
            )
            expected = len(cycle_frames)
            available = sum(
                point.side == cycle.side
                and cycle.start_ms <= point.timestamp_ms <= cycle.end_ms
                for point in joint_angles
            )
            expected_cycle_samples += expected
            indices = JOINT_LANDMARKS[joint][cycle.side]
            samples = [
                item
                for raw_frame, _ in cycle_frames
                for item in raw_frame.landmarks
                if item.index in indices
            ]
            processed_samples = [
                item
                for _, filtered_frame in cycle_frames
                for item in filtered_frame.landmarks
                if item.index in indices
            ]
            expected_landmark_samples = max(1, expected * len(indices))
            confidence = [min(item.visibility, item.presence) for item in samples]
            cycle_confidence = fmean(confidence) if confidence else 0.0
            cycle_interpolation = (
                sum(item.interpolated for item in processed_samples)
                / expected_landmark_samples
            )
            cycle_outliers = (
                sum(item.outlier_replaced for item in processed_samples)
                / expected_landmark_samples
            )
            minimum_coverage = 0.65 if joint == "ankle_dorsiflexion" else 0.60
            maximum_interpolation = 0.15 if joint == "ankle_dorsiflexion" else 0.20
            maximum_outliers = 0.10 if joint == "ankle_dorsiflexion" else 0.15
            if (
                expected >= 5
                and available / expected >= minimum_coverage
                and cycle_confidence >= 0.50
                and cycle_interpolation <= maximum_interpolation
                and cycle_outliers <= maximum_outliers
            ):
                valid_cycle_keys.add((cycle.side, cycle.start_ms, cycle.end_ms))

        valid_cycles = len(valid_cycle_keys)

        mean_visibility = fmean(visibility) if visibility else 0.0
        mean_presence = fmean(presence) if presence else 0.0
        outlier_rate = outliers / expected_landmarks
        interpolation_rate = interpolated / expected_landmarks
        continuity = complete_joint_frames / expected_joint_frames
        usable_rate = min(1.0, len(joint_angles) / max(1, expected_cycle_samples))
        excluded_cycles = max(0, len(cycles) - valid_cycles)
        jump_threshold = {
            "hip_flexion": 12.0,
            "knee_flexion": 15.0,
            "ankle_dorsiflexion": 10.0,
        }[joint]
        adjacent_changes: list[float] = []
        for side in ("left", "right"):
            ordered = sorted(
                (point for point in joint_angles if point.side == side),
                key=lambda point: point.timestamp_ms,
            )
            adjacent_changes.extend(
                abs(later.angle_degrees - earlier.angle_degrees)
                for earlier, later in zip(ordered, ordered[1:], strict=False)
                if 0 < later.timestamp_ms - earlier.timestamp_ms <= 100
            )
        angle_jump_rate = (
            sum(change > jump_threshold for change in adjacent_changes) / len(adjacent_changes)
            if adjacent_changes
            else 1.0
        )

        segment_consistency = 1.0
        if joint == "ankle_dorsiflexion":
            direction_sign = -1.0 if direction == "left" else 1.0
            foot_directions: list[bool] = []
            for frame in filtered_frames:
                by_index = {item.index: item for item in frame.landmarks}
                for side in ("left", "right"):
                    heel_index, toe_index = JOINT_LANDMARKS[joint][side][-2:]
                    heel = by_index.get(heel_index)
                    toe = by_index.get(toe_index)
                    if heel is not None and toe is not None:
                        foot_directions.append(direction_sign * (toe.x - heel.x) > 0.005)
            segment_consistency = (
                sum(foot_directions) / len(foot_directions) if foot_directions else 0.0
            )

        difficult = (
            valid_cycles == 0
            or continuity < 0.50
            or usable_rate < 0.35
            or mean_visibility < 0.50
            or mean_presence < 0.50
        )
        if joint == "ankle_dorsiflexion":
            difficult = (
                difficult
                or continuity < 0.65
                or usable_rate < 0.50
                or segment_consistency < 0.40
            )
            high = (
                mean_visibility >= 0.80
                and mean_presence >= 0.80
                and continuity >= 0.85
                and usable_rate >= 0.75
                and outlier_rate <= 0.05
                and interpolation_rate <= 0.08
                and angle_jump_rate <= 0.05
                and segment_consistency >= 0.80
                and valid_cycles >= 2
            )
        else:
            high = (
                mean_visibility >= 0.75
                and mean_presence >= 0.75
                and continuity >= 0.80
                and usable_rate >= 0.70
                and outlier_rate <= 0.08
                and interpolation_rate <= 0.12
                and angle_jump_rate <= 0.08
                and valid_cycles >= 2
            )

        status = "difficult" if difficult else ("high" if high else "caution")
        warnings: list[str] = []
        if joint == "ankle_dorsiflexion" and status == "caution":
            warnings.append("足部ランドマークの追跡品質に注意が必要なため参考値です。")
        if joint == "ankle_dorsiflexion" and status == "difficult":
            warnings.append("足部の追跡が不安定なため解析困難です。")
        if angle_jump_rate > (0.05 if joint == "ankle_dorsiflexion" else 0.08):
            warnings.append("短時間の角度変化が複数あり、追跡の安定性に注意が必要です。")
        if joint == "ankle_dorsiflexion" and segment_consistency < 0.80:
            warnings.append("踵から足趾への足部segment方向が一部フレームで不安定です。")
        if excluded_cycles:
            warnings.append(f"品質条件を満たさない{excluded_cycles}周期を集計から除外しました。")
        report = JointQualityReport(
            joint=joint,
            status=status,
            mean_visibility=round(mean_visibility, 4),
            mean_presence=round(mean_presence, 4),
            outlier_rate=round(outlier_rate, 4),
            interpolation_rate=round(interpolation_rate, 4),
            tracking_continuity=round(continuity, 4),
            usable_point_rate=round(usable_rate, 4),
            angle_jump_rate=round(angle_jump_rate, 4),
            segment_consistency=round(segment_consistency, 4),
            valid_cycle_count=valid_cycles,
            excluded_cycle_count=excluded_cycles,
            warnings=tuple(warnings),
        )
        return report, frozenset(valid_cycle_keys)

    @staticmethod
    def _exclude_invalid_cycle_points(
        points: tuple[AnglePoint, ...],
        valid_cycle_keys: dict[str, frozenset[tuple[str, int, int]]],
        cycles: tuple[GaitCycle, ...],
    ) -> tuple[AnglePoint, ...]:
        output: list[AnglePoint] = []
        for point in points:
            if point.cycle_percent is None:
                output.append(point)
                continue
            containing = next(
                (
                    (cycle.side, cycle.start_ms, cycle.end_ms)
                    for cycle in cycles
                    if cycle.side == point.side
                    and cycle.start_ms <= point.timestamp_ms <= cycle.end_ms
                ),
                None,
            )
            if containing in valid_cycle_keys.get(point.joint, frozenset()):
                output.append(point)
        return tuple(output)

    @staticmethod
    def _debug_summary(
        raw: tuple[AnglePoint, ...],
        filtered: tuple[AnglePoint, ...],
        quality: tuple[JointQualityReport, ...],
    ) -> dict[str, object]:
        output: dict[str, object] = {
            "note": "RawとFilteredの差は正常波形への適合ではなく、単発jump抑制の確認用です。",
            "joints": {},
        }
        quality_by_joint = {item.joint: item for item in quality}
        joints = output["joints"]
        assert isinstance(joints, dict)
        for joint in JOINT_LANDMARKS:
            joint_summary: dict[str, object] = {}
            for side in ("left", "right"):
                raw_points = [
                    point
                    for point in raw
                    if point.joint == joint
                    and point.side == side
                    and point.cycle_percent is not None
                ]
                filtered_points = [
                    point
                    for point in filtered
                    if point.joint == joint
                    and point.side == side
                    and point.cycle_percent is not None
                ]
                joint_summary[side] = {
                    "raw": _range_summary(raw_points),
                    "filtered": _range_summary(filtered_points),
                }
            report = quality_by_joint[joint]
            joint_summary["valid_cycle_count"] = report.valid_cycle_count
            joint_summary["excluded_cycle_count"] = report.excluded_cycle_count
            joints[joint] = joint_summary
        return output


def _range_summary(points: list[AnglePoint]) -> dict[str, float | int | None]:
    if not points:
        return {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "rom": None,
            "peak_cycle_percent": None,
            "median_frame_change": None,
            "p95_frame_change": None,
        }
    values = [point.angle_degrees for point in points]
    minimum = min(values)
    maximum = max(values)
    peak = max(points, key=lambda point: point.angle_degrees)
    ordered = sorted(points, key=lambda point: point.timestamp_ms)
    changes = [
        abs(later.angle_degrees - earlier.angle_degrees)
        for earlier, later in zip(ordered, ordered[1:], strict=False)
        if 0 < later.timestamp_ms - earlier.timestamp_ms <= 100
    ]
    return {
        "count": len(values),
        "minimum": round(minimum, 3),
        "maximum": round(maximum, 3),
        "rom": round(maximum - minimum, 3),
        "peak_cycle_percent": (
            round(peak.cycle_percent, 1) if peak.cycle_percent is not None else None
        ),
        "median_frame_change": (
            round(float(np.median(changes)), 3) if changes else None
        ),
        "p95_frame_change": (
            round(float(np.percentile(changes, 95)), 3) if changes else None
        ),
    }
