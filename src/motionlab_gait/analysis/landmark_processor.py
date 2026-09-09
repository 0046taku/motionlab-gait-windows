from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, sosfiltfilt

from motionlab_gait.analysis.types import ProcessingReport
from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseFrame, PoseLandmark


def _finite_segments(values: np.ndarray) -> list[tuple[int, int]]:
    mask = np.isfinite(values)
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
    return list(zip(starts.tolist(), ends.tolist(), strict=True))


class LandmarkProcessor:
    def __init__(
        self,
        *,
        confidence_threshold: float = 0.5,
        max_interpolation_gap_ms: int = 100,
        cutoff_hz: float = 6.0,
        filter_order: int = 4,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.max_interpolation_gap_ms = max_interpolation_gap_ms
        self.cutoff_hz = cutoff_hz
        self.filter_order = filter_order

    def process(
        self, frames: tuple[PoseFrame, ...], *, fps: float
    ) -> tuple[tuple[PoseFrame, ...], ProcessingReport]:
        if not frames:
            return (), ProcessingReport(
                0, 0, 0, 0, self.confidence_threshold, self.max_interpolation_gap_ms
            )

        frame_count = len(frames)
        timestamps = np.asarray([frame.timestamp_ms for frame in frames], dtype=float)
        coords = np.full((frame_count, 33, 6), np.nan, dtype=float)
        visibility = np.zeros((frame_count, 33), dtype=float)
        presence = np.zeros((frame_count, 33), dtype=float)
        originally_valid = np.zeros((frame_count, 33), dtype=bool)
        observed = np.zeros((frame_count, 33), dtype=bool)

        for frame_position, frame in enumerate(frames):
            for landmark in frame.landmarks:
                if not 0 <= landmark.index < 33:
                    continue
                index = landmark.index
                observed[frame_position, index] = True
                visibility[frame_position, index] = landmark.visibility
                presence[frame_position, index] = landmark.presence
                confident = min(landmark.visibility, landmark.presence) >= self.confidence_threshold
                originally_valid[frame_position, index] = confident
                if confident:
                    coords[frame_position, index, :3] = (landmark.x, landmark.y, landmark.z)
                    coords[frame_position, index, 3:] = (
                        np.nan if landmark.world_x is None else landmark.world_x,
                        np.nan if landmark.world_y is None else landmark.world_y,
                        np.nan if landmark.world_z is None else landmark.world_z,
                    )

        outlier_mask = np.zeros((frame_count, 33), dtype=bool)
        interpolated_mask = np.zeros((frame_count, 33), dtype=bool)
        for landmark_index in range(33):
            # Detect a 1-2 frame excursion from normalized landmark trajectories.
            # The same frame mask is then applied to every coordinate so a point
            # cannot become an anatomically inconsistent mixture of samples.
            rejected_landmark = np.zeros(frame_count, dtype=bool)
            for dimension in range(3):
                rejected_landmark |= self._reject_velocity_spikes(
                    coords[:, landmark_index, dimension], timestamps, position_floor=0.015
                )
            outlier_mask[:, landmark_index] = rejected_landmark
            coords[rejected_landmark, landmark_index, :] = np.nan
            for dimension in range(6):
                series = coords[:, landmark_index, dimension]
                filled = self._interpolate_short_gaps(series, timestamps)
                interpolated_mask[:, landmark_index] |= filled
                coords[:, landmark_index, dimension] = self._smooth(series, fps)

        output: list[PoseFrame] = []
        for frame_position, source_frame in enumerate(frames):
            landmarks: list[PoseLandmark] = []
            for index, name in enumerate(POSE_LANDMARK_NAMES):
                normalized = coords[frame_position, index, :3]
                if not np.all(np.isfinite(normalized)):
                    continue
                world = coords[frame_position, index, 3:]
                was_interpolated = bool(
                    interpolated_mask[frame_position, index]
                    or (
                        not originally_valid[frame_position, index]
                        and np.all(np.isfinite(normalized))
                    )
                )
                landmarks.append(
                    PoseLandmark(
                        index=index,
                        name=name,
                        x=float(normalized[0]),
                        y=float(normalized[1]),
                        z=float(normalized[2]),
                        visibility=float(visibility[frame_position, index]),
                        presence=float(presence[frame_position, index]),
                        world_x=float(world[0]) if math.isfinite(world[0]) else None,
                        world_y=float(world[1]) if math.isfinite(world[1]) else None,
                        world_z=float(world[2]) if math.isfinite(world[2]) else None,
                        interpolated=was_interpolated,
                        outlier_replaced=bool(outlier_mask[frame_position, index]),
                    )
                )
            output.append(
                PoseFrame(
                    frame_index=source_frame.frame_index,
                    timestamp_ms=source_frame.timestamp_ms,
                    landmarks=tuple(landmarks),
                )
            )

        report = ProcessingReport(
            frame_count=frame_count,
            interpolated_values=int(interpolated_mask.sum()),
            replaced_outliers=int(outlier_mask.sum()),
            smoothing_window_frames=0,
            confidence_threshold=self.confidence_threshold,
            max_interpolation_gap_ms=self.max_interpolation_gap_ms,
            low_confidence_landmarks=int((observed & ~originally_valid).sum()),
            filter_type="butterworth_lowpass",
            filter_order=self.filter_order,
            cutoff_hz=self.cutoff_hz,
            zero_phase=True,
        )
        return tuple(output), report

    @staticmethod
    def _reject_velocity_spikes(
        values: np.ndarray, timestamps: np.ndarray, *, position_floor: float
    ) -> np.ndarray:
        """Reject only short, high-velocity excursions that reverse immediately.

        A genuine fast movement generally continues in the same direction. A pose
        jump typically produces two unusually large velocity edges with opposite
        signs and returns close to the local trajectory within one or two frames.
        """
        rejected = np.zeros(len(values), dtype=bool)
        if len(values) < 5:
            return rejected
        dt = np.diff(timestamps) / 1000.0
        velocity = np.full(len(values) - 1, np.nan, dtype=float)
        usable = (
            np.isfinite(values[:-1])
            & np.isfinite(values[1:])
            & (dt > 0.0)
            & (dt <= 0.1)
        )
        velocity[usable] = np.diff(values)[usable] / dt[usable]
        finite_velocity = velocity[np.isfinite(velocity)]
        if len(finite_velocity) < 4:
            return rejected
        median_velocity = float(np.median(finite_velocity))
        mad = float(np.median(np.abs(finite_velocity - median_velocity)))
        robust_scale = 1.4826 * mad
        velocity_floor = position_floor / max(float(np.median(dt[dt > 0])), 1e-3)
        threshold = max(velocity_floor, 6.0 * robust_scale)

        for gap in (1, 2):
            for left in range(0, len(values) - gap - 1):
                right = left + gap + 1
                if not (math.isfinite(values[left]) and math.isfinite(values[right])):
                    continue
                first_edge = velocity[left]
                last_edge = velocity[right - 1]
                if not (math.isfinite(first_edge) and math.isfinite(last_edge)):
                    continue
                if abs(first_edge) <= threshold or abs(last_edge) <= threshold:
                    continue
                if first_edge * last_edge >= 0.0:
                    continue
                interior = np.arange(left + 1, right)
                if not np.all(np.isfinite(values[interior])):
                    continue
                expected = np.interp(
                    timestamps[interior],
                    (timestamps[left], timestamps[right]),
                    (values[left], values[right]),
                )
                if float(np.max(np.abs(values[interior] - expected))) > position_floor:
                    rejected[interior] = True
        return rejected

    def _interpolate_short_gaps(self, values: np.ndarray, timestamps: np.ndarray) -> np.ndarray:
        filled = np.zeros(len(values), dtype=bool)
        valid = np.flatnonzero(np.isfinite(values))
        for left, right in zip(valid, valid[1:], strict=False):
            if right == left + 1:
                continue
            if timestamps[right] - timestamps[left] > self.max_interpolation_gap_ms:
                continue
            positions = np.arange(left + 1, right)
            values[positions] = np.interp(
                timestamps[positions],
                (timestamps[left], timestamps[right]),
                (values[left], values[right]),
            )
            filled[positions] = True
        return filled

    def _smooth(self, values: np.ndarray, fps: float) -> np.ndarray:
        output = values.copy()
        if fps <= 0.0:
            return output
        cutoff = min(self.cutoff_hz, 0.45 * fps)
        if cutoff <= 0.0:
            return output
        sos = butter(self.filter_order, cutoff, btype="lowpass", fs=fps, output="sos")
        for start, end in _finite_segments(values):
            if end - start < 15:
                continue
            try:
                output[start:end] = sosfiltfilt(sos, values[start:end])
            except ValueError:
                # Very short finite segments are intentionally left unfiltered.
                continue
        return output
