from __future__ import annotations

import math
from statistics import fmean

from motionlab_gait.analysis.types import (
    AnglePoint,
    GaitCycle,
    GaitEvent,
    MetricValue,
    TemporalMetrics,
)
from motionlab_gait.domain.models import PoseFrame


def _point(frame: PoseFrame, index: int):
    return next((item for item in frame.landmarks if item.index == index), None)


def _mean(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _confidence(events: list[GaitEvent] | tuple[GaitEvent, ...]) -> float:
    return fmean(item.confidence for item in events) if events else 0.0


def calculate_temporal_metrics(
    events: tuple[GaitEvent, ...],
    cycles: tuple[GaitCycle, ...],
    *,
    known_distance_m: float | None = None,
    distance_start_ms: int | None = None,
    distance_end_ms: int | None = None,
) -> TemporalMetrics:
    values: list[MetricValue] = []
    valid_ic = sorted(
        (item for item in events if item.event_type == "IC"), key=lambda item: item.timestamp_ms
    )
    alternating_steps = [
        (later.timestamp_ms - earlier.timestamp_ms) / 1000.0
        for earlier, later in zip(valid_ic, valid_ic[1:], strict=False)
        if earlier.side != later.side
        and 0.15 <= (later.timestamp_ms - earlier.timestamp_ms) / 1000.0 <= 1.5
    ]
    step_time = _mean(alternating_steps)
    values.append(MetricValue("step_time", step_time, "s", _confidence(valid_ic), "左右IC間隔"))

    complete_cycles = tuple(
        item
        for item in cycles
        if item.toe_off_ms is not None
        and 0.25
        <= (item.toe_off_ms - item.start_ms) / max(item.end_ms - item.start_ms, 1)
        <= 0.85
    )
    cycle_durations = [(item.end_ms - item.start_ms) / 1000.0 for item in complete_cycles]
    stride_time = _mean(cycle_durations)
    cycle_confidence = (
        fmean(item.confidence for item in complete_cycles) if complete_cycles else 0.0
    )
    values.append(MetricValue("stride_time", stride_time, "s", cycle_confidence, "同側IC間隔"))

    stance_durations = [
        (item.toe_off_ms - item.start_ms) / 1000.0 for item in complete_cycles
    ]
    swing_durations = [
        (item.end_ms - item.toe_off_ms) / 1000.0 for item in complete_cycles
    ]
    stance_time = _mean(stance_durations)
    swing_time = _mean(swing_durations)
    stance_percentages = [
        100.0 * (item.toe_off_ms - item.start_ms) / (item.end_ms - item.start_ms)
        for item in complete_cycles
    ]
    swing_percentages = [100.0 - value for value in stance_percentages]
    values.extend(
        (
            MetricValue("stance_time", stance_time, "s", cycle_confidence, "ICから同側TO"),
            MetricValue("swing_time", swing_time, "s", cycle_confidence, "TOから次の同側IC"),
            MetricValue(
                "stance_percent",
                _mean(stance_percentages),
                "%",
                cycle_confidence,
            ),
            MetricValue(
                "swing_percent",
                _mean(swing_percentages),
                "%",
                cycle_confidence,
            ),
            MetricValue(
                "cadence",
                (120.0 / stride_time) if stride_time and stride_time > 0 else None,
                "steps/min",
                cycle_confidence,
                "完全な同側IC周期から算出（120÷平均stride time）",
            ),
        )
    )

    for metric_name, extractor in (
        ("stride_time", lambda cycle: (cycle.end_ms - cycle.start_ms) / 1000.0),
        (
            "stance_time",
            lambda cycle: None
            if cycle.toe_off_ms is None
            else (cycle.toe_off_ms - cycle.start_ms) / 1000.0,
        ),
    ):
        side_means: dict[str, float | None] = {}
        for side in ("left", "right"):
            side_values = [
                value
                for cycle in complete_cycles
                if cycle.side == side and (value := extractor(cycle)) is not None
            ]
            side_means[side] = _mean(side_values)
            values.append(
                MetricValue(f"{side}_{metric_name}", side_means[side], "s", cycle_confidence)
            )
        left, right = side_means["left"], side_means["right"]
        symmetry = (
            100.0 * abs(left - right) / (0.5 * (left + right))
            if left is not None and right is not None and left + right > 0
            else None
        )
        values.append(
            MetricValue(
                f"{metric_name}_symmetry_index",
                symmetry,
                "%",
                cycle_confidence,
                "0%が左右同等。|L-R|/平均×100",
            )
        )

    speed = None
    speed_note = "距離と計測区間が未設定のため算出しません。"
    if (
        known_distance_m is not None
        and known_distance_m > 0
        and distance_start_ms is not None
        and distance_end_ms is not None
        and distance_end_ms > distance_start_ms
    ):
        speed = known_distance_m / ((distance_end_ms - distance_start_ms) / 1000.0)
        speed_note = "ユーザー指定距離÷指定区間時間"
    values.append(MetricValue("walking_speed", speed, "m/s", 1.0 if speed else 0.0, speed_note))
    return TemporalMetrics(
        values=tuple(values),
        left_cycle_count=sum(item.side == "left" for item in complete_cycles),
        right_cycle_count=sum(item.side == "right" for item in complete_cycles),
    )


def calculate_joint_angles(
    frames: tuple[PoseFrame, ...], cycles: tuple[GaitCycle, ...], *, direction: str
) -> tuple[AnglePoint, ...]:
    direction_sign = -1.0 if direction == "left" else 1.0
    points: list[AnglePoint] = []
    indices = {
        "left": (11, 23, 25, 27, 29, 31),
        "right": (12, 24, 26, 28, 30, 32),
    }
    for frame in frames:
        for side, (shoulder_i, hip_i, knee_i, ankle_i, heel_i, toe_i) in indices.items():
            landmarks = [
                _point(frame, index)
                for index in (shoulder_i, hip_i, knee_i, ankle_i, heel_i, toe_i)
            ]
            if any(item is None for item in landmarks):
                continue
            shoulder, hip, knee, ankle, heel, toe = landmarks
            shoulder_p = (direction_sign * shoulder.x, -shoulder.y)
            hip_p = (direction_sign * hip.x, -hip.y)
            knee_p = (direction_sign * knee.x, -knee.y)
            ankle_p = (direction_sign * ankle.x, -ankle.y)
            heel_p = (direction_sign * heel.x, -heel.y)
            toe_p = (direction_sign * toe.x, -toe.y)

            body_down = _vector(shoulder_p, hip_p)
            thigh_down = _vector(hip_p, knee_p)
            hip_flexion = _signed_angle(body_down, thigh_down)
            knee_flexion = 180.0 - _unsigned_angle(_vector(knee_p, hip_p), _vector(knee_p, ankle_p))
            ankle_dorsiflexion = 90.0 - _unsigned_angle(
                _vector(ankle_p, knee_p), _vector(heel_p, toe_p)
            )
            cycle_percent = _cycle_percent(frame.timestamp_ms, side, cycles)
            for joint, angle, joint_confidence in (
                (
                    "hip_flexion",
                    hip_flexion,
                    min(min(item.visibility, item.presence) for item in (shoulder, hip, knee)),
                ),
                (
                    "knee_flexion",
                    knee_flexion,
                    min(min(item.visibility, item.presence) for item in (hip, knee, ankle)),
                ),
                (
                    "ankle_dorsiflexion",
                    ankle_dorsiflexion,
                    0.75
                    * min(
                        min(item.visibility, item.presence)
                        for item in (knee, ankle, heel, toe)
                    ),
                ),
            ):
                bounds = {
                    "hip_flexion": (-45.0, 75.0),
                    "knee_flexion": (-5.0, 130.0),
                    "ankle_dorsiflexion": (-50.0, 40.0),
                }[joint]
                if (
                    math.isfinite(angle)
                    and joint_confidence >= 0.5
                    and bounds[0] <= angle <= bounds[1]
                ):
                    points.append(
                        AnglePoint(
                            timestamp_ms=frame.timestamp_ms,
                            cycle_percent=cycle_percent,
                            side=side,
                            joint=joint,
                            angle_degrees=round(angle, 3),
                            confidence=round(joint_confidence, 3),
                        )
                    )
    return tuple(points)


def _vector(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    return end[0] - start[0], end[1] - start[1]


def _unsigned_angle(first: tuple[float, float], second: tuple[float, float]) -> float:
    denominator = math.hypot(*first) * math.hypot(*second)
    if denominator <= 1e-9:
        return math.nan
    cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / denominator))
    return math.degrees(math.acos(cosine))


def _signed_angle(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.degrees(
        math.atan2(
            first[0] * second[1] - first[1] * second[0], first[0] * second[0] + first[1] * second[1]
        )
    )


def _cycle_percent(timestamp_ms: int, side: str, cycles: tuple[GaitCycle, ...]) -> float | None:
    for cycle in cycles:
        if cycle.side == side and cycle.start_ms <= timestamp_ms <= cycle.end_ms:
            return 100.0 * (timestamp_ms - cycle.start_ms) / (cycle.end_ms - cycle.start_ms)
    return None
