from __future__ import annotations

import math
from statistics import median

import numpy as np

from motionlab_gait.analysis.types import ViewpointReport
from motionlab_gait.domain.models import PoseFrame


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _landmarks(frame: PoseFrame) -> dict[int, object]:
    return {item.index: item for item in frame.landmarks}


def _frame_sagittal_score(frame: PoseFrame) -> float:
    """Estimate side-view suitability from projected body width and bilateral depth.

    This is a conservative acquisition-quality heuristic, not an anatomical angle.
    """
    points = _landmarks(frame)
    if not all(index in points for index in (11, 12, 23, 24)):
        return 0.0
    left_shoulder, right_shoulder = points[11], points[12]
    left_hip, right_hip = points[23], points[24]
    shoulder_mid = (
        (left_shoulder.x + right_shoulder.x) / 2.0,
        (left_shoulder.y + right_shoulder.y) / 2.0,
    )
    hip_mid = (
        (left_hip.x + right_hip.x) / 2.0,
        (left_hip.y + right_hip.y) / 2.0,
    )
    torso = math.dist(shoulder_mid, hip_mid)
    if torso <= 1e-5:
        return 0.0
    shoulder_width = math.dist(
        (left_shoulder.x, left_shoulder.y), (right_shoulder.x, right_shoulder.y)
    ) / torso
    hip_width = math.dist((left_hip.x, left_hip.y), (right_hip.x, right_hip.y)) / torso
    shoulder_depth = abs(left_shoulder.z - right_shoulder.z) / torso

    narrow_shoulders = _clamp((1.05 - shoulder_width) / 0.65)
    narrow_hips = _clamp((0.70 - hip_width) / 0.45)
    bilateral_depth = _clamp((shoulder_depth - 0.50) / 1.50)
    return 0.35 * narrow_shoulders + 0.35 * narrow_hips + 0.30 * bilateral_depth


def assess_viewpoint(frames: tuple[PoseFrame, ...], *, fps: float) -> ViewpointReport:
    if len(frames) < 10:
        return ViewpointReport(
            classification="insufficient",
            sagittal_fraction=0.0,
            stable_sagittal_score=0.0,
            analysis_start_ms=None,
            analysis_end_ms=None,
            analysis_frame_count=0,
            analysis_supported=False,
            warnings=("撮影面を判定できるフレームが不足しています。",),
        )

    raw_scores = np.asarray([_frame_sagittal_score(frame) for frame in frames], dtype=float)
    half_window = max(1, round(max(fps, 1.0) * 0.25))
    smoothed = np.asarray(
        [
            median(raw_scores[max(0, index - half_window) : index + half_window + 1])
            for index in range(len(raw_scores))
        ],
        dtype=float,
    )
    qualified = smoothed >= 0.60

    # Bridge brief landmark/viewpoint interruptions, but never a sustained camera-plane change.
    max_gap = max(1, round(max(fps, 1.0) * 0.30))
    true_positions = np.flatnonzero(qualified)
    for before, after in zip(true_positions, true_positions[1:], strict=False):
        if 1 < after - before <= max_gap + 1:
            qualified[before : after + 1] = True

    best_start = best_end = None
    run_start = None
    for index, is_sagittal in enumerate([*qualified, False]):
        if is_sagittal and run_start is None:
            run_start = index
        elif not is_sagittal and run_start is not None:
            run_end = index - 1
            if best_start is None or run_end - run_start > best_end - best_start:
                best_start, best_end = run_start, run_end
            run_start = None

    sagittal_fraction = float(np.mean(qualified))
    minimum_frames = max(30, round(max(fps, 1.0) * 3.0))
    supported = (
        best_start is not None
        and best_end is not None
        and best_end - best_start + 1 >= minimum_frames
    )
    if not supported:
        return ViewpointReport(
            classification="frontal_or_oblique",
            sagittal_fraction=round(sagittal_fraction, 3),
            stable_sagittal_score=0.0,
            analysis_start_ms=None,
            analysis_end_ms=None,
            analysis_frame_count=0,
            analysis_supported=False,
            warnings=(
                "3秒以上連続する安定した矢状面区間がないため、IC/TO・時間指標・関節角度を算出しません。",
            ),
        )

    assert best_start is not None and best_end is not None
    stable_score = float(median(smoothed[best_start : best_end + 1]))
    classification = "sagittal" if sagittal_fraction >= 0.80 else "mixed"
    warnings: list[str] = []
    if classification == "mixed":
        warnings.append(
            "前額面・斜め・旋回区間が混在しています。最長の安定した矢状面区間だけを定量解析しました。"
        )
    if stable_score < 0.72:
        warnings.append("採用した区間も完全な真横ではない可能性があり、角度は低信頼です。")
    return ViewpointReport(
        classification=classification,
        sagittal_fraction=round(sagittal_fraction, 3),
        stable_sagittal_score=round(stable_score, 3),
        analysis_start_ms=frames[best_start].timestamp_ms,
        analysis_end_ms=frames[best_end].timestamp_ms,
        analysis_frame_count=best_end - best_start + 1,
        analysis_supported=True,
        warnings=tuple(warnings),
    )


def select_analysis_frames(
    frames: tuple[PoseFrame, ...], report: ViewpointReport
) -> tuple[PoseFrame, ...]:
    if (
        not report.analysis_supported
        or report.analysis_start_ms is None
        or report.analysis_end_ms is None
    ):
        return ()
    return tuple(
        frame
        for frame in frames
        if report.analysis_start_ms <= frame.timestamp_ms <= report.analysis_end_ms
    )
