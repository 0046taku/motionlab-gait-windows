from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from motionlab_gait.analysis.event_detector import GaitEventDetector
from motionlab_gait.analysis.findings import summarize_observed_features
from motionlab_gait.analysis.joint_pipeline import JointAnglePipeline
from motionlab_gait.analysis.kinematics import calculate_joint_angles, calculate_temporal_metrics
from motionlab_gait.analysis.landmark_processor import LandmarkProcessor
from motionlab_gait.analysis.quality import assess_pose_quality
from motionlab_gait.analysis.types import GaitCycle
from motionlab_gait.analysis.viewpoint import assess_viewpoint, select_analysis_frames
from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseFrame, PoseLandmark


def _walking_frames(seconds: float = 5.0, fps: float = 30.0) -> tuple[PoseFrame, ...]:
    frames: list[PoseFrame] = []
    for frame_index in range(round(seconds * fps)):
        time = frame_index / fps
        pelvis_x = 0.25 + 0.05 * time
        landmarks: list[PoseLandmark] = []
        for index, name in enumerate(POSE_LANDMARK_NAMES):
            side_phase = 0.0 if "left" in name else math.pi
            swing = 0.08 * math.sin(2 * math.pi * time + side_phase)
            x = pelvis_x
            y = 0.25
            if "shoulder" in name:
                x += 0.01 * math.sin(2 * math.pi * time + side_phase)
                y = 0.30
            elif "hip" in name:
                y = 0.50
            elif "knee" in name:
                x += 0.45 * swing
                y = 0.68
            elif "ankle" in name:
                x += 0.8 * swing
                y = 0.86
            elif "heel" in name or "foot_index" in name:
                x += swing
                y = 0.91
            landmarks.append(PoseLandmark(index, name, x, y, 0.0, 0.95, 0.95))
        frames.append(PoseFrame(frame_index, round(time * 1000), tuple(landmarks)))
    return tuple(frames)


def test_quality_and_processing_preserve_frame_timestamps() -> None:
    frames = list(_walking_frames(seconds=2.0))
    broken = list(frames[15].landmarks)
    item = broken[27]
    broken[27] = PoseLandmark(item.index, item.name, 2.0, item.y, item.z, 0.95, 0.95)
    frames[15] = PoseFrame(frames[15].frame_index, frames[15].timestamp_ms, tuple(broken))

    quality = assess_pose_quality(tuple(frames), expected_frame_count=len(frames), fps=30.0)
    processed, report = LandmarkProcessor().process(tuple(frames), fps=30.0)

    assert quality.grade in {"A", "B"}
    assert [item.timestamp_ms for item in processed] == [item.timestamp_ms for item in frames]
    assert report.replaced_outliers >= 1
    assert next(item for item in processed[15].landmarks if item.index == 27).outlier_replaced


def test_events_cycles_metrics_and_angles_are_computable() -> None:
    frames = _walking_frames()
    direction, confidence, events, cycles, warnings = GaitEventDetector().detect(frames, fps=30.0)
    metrics = calculate_temporal_metrics(events, cycles)
    angles = calculate_joint_angles(frames, cycles, direction=direction)

    assert direction == "right"
    assert confidence > 0.5
    assert any(item.event_type == "IC" for item in events)
    assert any(item.event_type == "TO" for item in events)
    assert len(cycles) >= 4
    assert any(item.name == "cadence" and item.value for item in metrics.values)
    assert any(item.joint == "knee_flexion" for item in angles)
    assert isinstance(warnings, tuple)


def test_speed_requires_explicit_distance_interval() -> None:
    empty = calculate_temporal_metrics((), ())
    speed = next(item for item in empty.values if item.name == "walking_speed")
    assert speed.value is None

    calibrated = calculate_temporal_metrics(
        (), (), known_distance_m=10.0, distance_start_ms=1_000, distance_end_ms=6_000
    )
    speed = next(item for item in calibrated.values if item.name == "walking_speed")
    assert speed.value == 2.0


def test_findings_keep_measurements_separate_from_check_candidates() -> None:
    metrics = calculate_temporal_metrics((), ())
    observed, checks = summarize_observed_features(metrics, (), affected_side="none")
    assert "患側が未設定" in observed[0]
    assert checks == ()


def _set_camera_plane(
    frames: tuple[PoseFrame, ...], *, front_until: int
) -> tuple[PoseFrame, ...]:
    output: list[PoseFrame] = []
    for frame_position, frame in enumerate(frames):
        landmarks = list(frame.landmarks)
        for left_index, right_index, front_half_width, side_half_width in (
            (11, 12, 0.12, 0.015),
            (23, 24, 0.07, 0.010),
        ):
            center = (landmarks[left_index].x + landmarks[right_index].x) / 2.0
            if frame_position < front_until:
                landmarks[left_index] = replace(
                    landmarks[left_index], x=center - front_half_width, z=0.0
                )
                landmarks[right_index] = replace(
                    landmarks[right_index], x=center + front_half_width, z=0.0
                )
            else:
                landmarks[left_index] = replace(
                    landmarks[left_index], x=center - side_half_width, z=-0.35
                )
                landmarks[right_index] = replace(
                    landmarks[right_index], x=center + side_half_width, z=0.35
                )
        output.append(replace(frame, landmarks=tuple(landmarks)))
    return tuple(output)


def test_mixed_camera_plane_selects_only_stable_sagittal_segment() -> None:
    frames = _walking_frames(seconds=10.0)
    mixed = _set_camera_plane(frames, front_until=len(frames) // 2)

    report = assess_viewpoint(mixed, fps=30.0)
    selected = select_analysis_frames(mixed, report)

    assert report.classification == "mixed"
    assert report.analysis_supported
    assert selected
    assert selected[0].timestamp_ms >= 4_500
    assert len(selected) < len(mixed)


def test_frontal_video_blocks_quantitative_analysis() -> None:
    frames = _walking_frames(seconds=5.0)
    frontal = _set_camera_plane(frames, front_until=len(frames))

    report = assess_viewpoint(frontal, fps=30.0)

    assert report.classification == "frontal_or_oblique"
    assert not report.analysis_supported
    assert select_analysis_frames(frontal, report) == ()


def test_stance_and_swing_percent_use_same_complete_cycles() -> None:
    cycles = (
        GaitCycle("left", 0, 1_000, 600, 0.9),
        GaitCycle("right", 500, 1_500, 1_100, 0.9),
        GaitCycle("left", 1_000, 3_000, None, 0.2),
    )
    metrics = calculate_temporal_metrics((), cycles)
    values = {item.name: item.value for item in metrics.values}

    assert values["stride_time"] == 1.0
    assert values["stance_percent"] == 60.0
    assert values["swing_percent"] == 40.0
    assert values["stance_percent"] + values["swing_percent"] == 100.0


def test_neutral_heel_to_toe_axis_produces_neutral_ankle_angle() -> None:
    landmarks = [
        PoseLandmark(index, name, 0.0, 0.0, 0.0, 0.95, 0.95)
        for index, name in enumerate(POSE_LANDMARK_NAMES)
    ]
    coordinates = {
        11: (0.0, 0.0),
        23: (0.0, 1.0),
        25: (0.0, 2.0),
        27: (0.0, 3.0),
        29: (0.0, 3.1),
        31: (1.0, 3.1),
    }
    for index, (x, y) in coordinates.items():
        landmarks[index] = replace(landmarks[index], x=x, y=y)
    frame = PoseFrame(15, 500, tuple(landmarks))
    cycle = GaitCycle("left", 0, 1_000, 600, 0.9)

    angles = calculate_joint_angles((frame,), (cycle,), direction="right")
    ankle = next(
        item
        for item in angles
        if item.side == "left" and item.joint == "ankle_dorsiflexion"
    )

    assert abs(ankle.angle_degrees) < 0.001


def test_joint_pipeline_keeps_existing_filtered_knee_angles_unchanged() -> None:
    raw = _walking_frames()
    processed, _ = LandmarkProcessor().process(raw, fps=30.0)
    direction, _, _, cycles, _ = GaitEventDetector().detect(processed, fps=30.0)

    bundle = JointAnglePipeline().analyze(
        raw, processed, cycles, direction=direction
    )
    existing = calculate_joint_angles(processed, cycles, direction=direction)

    expected_knees = tuple(item for item in existing if item.joint == "knee_flexion")
    actual_knees = tuple(item for item in bundle.filtered_angles if item.joint == "knee_flexion")
    assert actual_knees == expected_knees
    assert {item.joint for item in bundle.quality} == {
        "hip_flexion",
        "knee_flexion",
        "ankle_dorsiflexion",
    }


def test_hip_flexion_sign_does_not_flip_with_walking_direction() -> None:
    def hip_angle(knee_x: float, direction: str) -> float:
        landmarks = [
            PoseLandmark(index, name, 0.0, 0.0, 0.0, 0.95, 0.95)
            for index, name in enumerate(POSE_LANDMARK_NAMES)
        ]
        for index, (x, y) in {11: (0.0, 0.0), 23: (0.0, 1.0), 25: (knee_x, 2.0)}.items():
            landmarks[index] = replace(landmarks[index], x=x, y=y)
        frame = PoseFrame(15, 500, tuple(landmarks))
        cycle = GaitCycle("left", 0, 1_000, 600, 0.9)
        return next(
            item.angle_degrees
            for item in calculate_joint_angles((frame,), (cycle,), direction=direction)
            if item.side == "left" and item.joint == "hip_flexion"
        )

    assert hip_angle(0.5, "right") == hip_angle(-0.5, "left")
    assert hip_angle(0.5, "right") > 0


def test_unstable_foot_tracking_marks_ankle_as_difficult() -> None:
    frames: list[PoseFrame] = []
    for frame in _walking_frames():
        landmarks = tuple(
            replace(item, visibility=0.2, presence=0.2)
            if item.index in {29, 30, 31, 32}
            else item
            for item in frame.landmarks
        )
        frames.append(replace(frame, landmarks=landmarks))
    raw = tuple(frames)
    processed, _ = LandmarkProcessor().process(raw, fps=30.0)
    direction, _, _, cycles, _ = GaitEventDetector().detect(raw, fps=30.0)

    bundle = JointAnglePipeline().analyze(raw, processed, cycles, direction=direction)
    ankle_quality = next(
        item for item in bundle.quality if item.joint == "ankle_dorsiflexion"
    )

    assert ankle_quality.status == "difficult"
    assert any("解析困難" in warning for warning in ankle_quality.warnings)


def test_zero_phase_filter_reduces_high_frequency_noise_without_phase_shift() -> None:
    fps = 60.0
    frames = list(_walking_frames(seconds=4.0, fps=fps))
    clean: list[float] = []
    noisy: list[float] = []
    for index, frame in enumerate(frames):
        time = index / fps
        target = 0.5 + 0.08 * math.sin(2.0 * math.pi * time)
        sample = target + 0.015 * math.sin(20.0 * math.pi * time)
        clean.append(target)
        noisy.append(sample)
        landmarks = list(frame.landmarks)
        landmarks[25] = replace(landmarks[25], x=sample)
        frames[index] = replace(frame, landmarks=tuple(landmarks))

    processed, report = LandmarkProcessor(cutoff_hz=6.0).process(tuple(frames), fps=fps)
    filtered = np.asarray(
        [next(item.x for item in frame.landmarks if item.index == 25) for frame in processed]
    )
    clean_values = np.asarray(clean)
    noisy_values = np.asarray(noisy)
    interior = slice(30, -30)
    raw_error = float(np.sqrt(np.mean((noisy_values[interior] - clean_values[interior]) ** 2)))
    filtered_error = float(
        np.sqrt(np.mean((filtered[interior] - clean_values[interior]) ** 2))
    )
    lag = int(
        np.argmax(
            np.correlate(
                filtered[interior] - np.mean(filtered[interior]),
                clean_values[interior] - np.mean(clean_values[interior]),
                mode="full",
            )
        )
        - (len(filtered[interior]) - 1)
    )

    assert report.filter_type == "butterworth_lowpass"
    assert report.zero_phase
    assert filtered_error < raw_error * 0.35
    assert lag == 0


def test_long_low_confidence_gap_is_not_interpolated() -> None:
    frames = list(_walking_frames(seconds=2.0, fps=30.0))
    for index in range(20, 26):
        landmarks = list(frames[index].landmarks)
        landmarks[27] = replace(landmarks[27], visibility=0.2, presence=0.2)
        frames[index] = replace(frames[index], landmarks=tuple(landmarks))

    processed, report = LandmarkProcessor().process(tuple(frames), fps=30.0)

    assert report.low_confidence_landmarks == 6
    assert all(
        not any(item.index == 27 for item in processed[index].landmarks)
        for index in range(20, 26)
    )


def test_low_quality_cycle_is_excluded_from_representative_joint_angles() -> None:
    frames = list(_walking_frames(seconds=2.1, fps=30.0))
    for index, frame in enumerate(frames):
        if frame.timestamp_ms >= 1_000:
            landmarks = tuple(
                replace(item, visibility=0.2, presence=0.2)
                if item.index in {23, 25, 27}
                else item
                for item in frame.landmarks
            )
            frames[index] = replace(frame, landmarks=landmarks)
    raw = tuple(frames)
    processed, _ = LandmarkProcessor().process(raw, fps=30.0)
    cycles = (
        GaitCycle("left", 0, 999, 600, 0.9),
        GaitCycle("left", 1_000, 2_000, 1_600, 0.9),
    )

    bundle = JointAnglePipeline().analyze(raw, processed, cycles, direction="right")
    knee_quality = next(item for item in bundle.quality if item.joint == "knee_flexion")
    knee_points = [
        item
        for item in bundle.filtered_angles
        if item.joint == "knee_flexion" and item.side == "left"
    ]

    assert knee_quality.valid_cycle_count == 1
    assert knee_quality.excluded_cycle_count == 1
    assert knee_points
    assert all(item.timestamp_ms < 1_000 for item in knee_points)
