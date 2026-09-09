from __future__ import annotations

import math
from statistics import fmean

from motionlab_gait.analysis.types import QualityComponent, QualityReport, ViewpointReport
from motionlab_gait.domain.models import PoseFrame

LOWER_LIMB_INDICES = (23, 24, 25, 26, 27, 28, 29, 30, 31, 32)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def assess_pose_quality(
    frames: tuple[PoseFrame, ...],
    *,
    expected_frame_count: int,
    fps: float,
    viewpoint: ViewpointReport | None = None,
) -> QualityReport:
    detected = [frame for frame in frames if len(frame.landmarks) == 33]
    expected = max(1, expected_frame_count or len(frames))
    detection_rate = _clamp(len(detected) / expected)

    all_visibility = [
        landmark.visibility
        for frame in detected
        for landmark in frame.landmarks
        if math.isfinite(landmark.visibility)
    ]
    mean_visibility = _clamp(fmean(all_visibility)) if all_visibility else 0.0
    lower_visibility = [
        frame.landmarks[index].visibility
        for frame in detected
        for index in LOWER_LIMB_INDICES
        if index < len(frame.landmarks)
    ]
    lower_limb_visibility = _clamp(fmean(lower_visibility)) if lower_visibility else 0.0

    if len(detected) < 2:
        continuity = 0.0
        jump_rate = 1.0
    else:
        nominal_ms = 1000.0 / max(fps, 1.0)
        gaps = [
            detected[index].timestamp_ms - detected[index - 1].timestamp_ms
            for index in range(1, len(detected))
        ]
        continuity = _clamp(1.0 - sum(max(0.0, gap / nominal_ms - 1.5) for gap in gaps) / expected)
        jumps = 0
        comparisons = 0
        for before, after in zip(detected, detected[1:], strict=False):
            for index in LOWER_LIMB_INDICES:
                first = before.landmarks[index]
                second = after.landmarks[index]
                if min(first.visibility, second.visibility) < 0.5:
                    continue
                comparisons += 1
                displacement = math.hypot(second.x - first.x, second.y - first.y)
                if displacement > 0.12:
                    jumps += 1
        jump_rate = jumps / comparisons if comparisons else 1.0

    stability = 1.0 - _clamp(jump_rate * 10.0)
    viewpoint_score = viewpoint.stable_sagittal_score if viewpoint else 1.0
    score = 100.0 * (
        0.25 * detection_rate
        + 0.15 * mean_visibility
        + 0.20 * lower_limb_visibility
        + 0.10 * continuity
        + 0.05 * stability
        + 0.25 * viewpoint_score
    )
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"
    if viewpoint is not None:
        if not viewpoint.analysis_supported:
            grade = "D"
            score = min(score, 49.0)
        elif viewpoint.classification == "mixed" and grade == "A":
            grade = "B"
            score = min(score, 84.0)

    warnings: list[str] = []
    if detection_rate < 0.8:
        warnings.append("人物を検出できないフレームが多く、結果が不安定です。")
    if lower_limb_visibility < 0.6:
        warnings.append("股・膝・足部の見え方が不十分です。")
    if continuity < 0.9 or jump_rate > 0.02:
        warnings.append("ランドマークの途切れまたは急な位置飛びがあります。")
    if fps < 25:
        warnings.append("フレームレートが低く、接地時刻の誤差が大きくなります。")
    if viewpoint is not None:
        warnings.extend(viewpoint.warnings)

    components = (
        QualityComponent("detection", detection_rate, "33点が得られたフレーム割合"),
        QualityComponent("visibility", mean_visibility, "全ランドマークの平均visibility"),
        QualityComponent("lower_limb", lower_limb_visibility, "下肢10点の平均visibility"),
        QualityComponent("continuity", continuity, "フレーム間の連続性"),
        QualityComponent("stability", stability, "急な位置飛びの少なさ"),
        QualityComponent("viewpoint", viewpoint_score, "矢状面としての撮影適合度"),
    )
    return QualityReport(
        grade=grade,
        score=round(score, 1),
        detection_rate=detection_rate,
        mean_visibility=mean_visibility,
        continuity=continuity,
        jump_rate=jump_rate,
        lower_limb_visibility=lower_limb_visibility,
        components=components,
        warnings=tuple(warnings),
    )
