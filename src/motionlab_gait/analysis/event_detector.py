from __future__ import annotations

import math
from statistics import median

import numpy as np
from scipy.signal import find_peaks

from motionlab_gait.analysis.types import GaitCycle, GaitEvent
from motionlab_gait.domain.models import PoseFrame

SIDE_INDICES = {
    "left": {"hip": 23, "ankle": 27, "heel": 29, "toe": 31},
    "right": {"hip": 24, "ankle": 28, "heel": 30, "toe": 32},
}


def _landmark(frame: PoseFrame, index: int):
    return next((item for item in frame.landmarks if item.index == index), None)


class GaitEventDetector:
    def detect(
        self, frames: tuple[PoseFrame, ...], *, fps: float
    ) -> tuple[str, float, tuple[GaitEvent, ...], tuple[GaitCycle, ...], tuple[str, ...]]:
        direction, direction_confidence = self._detect_direction(frames)
        direction_sign = -1.0 if direction == "left" else 1.0
        events: list[GaitEvent] = []
        warnings: list[str] = []
        if direction == "unknown":
            warnings.append(
                "進行方向を十分な確信で判定できませんでした。右方向として仮解析しています。"
            )

        timestamps = np.asarray([frame.timestamp_ms for frame in frames], dtype=float)
        minimum_distance = max(2, round(max(fps, 1.0) * 0.40))
        for side, indices in SIDE_INDICES.items():
            heel_signal, heel_conf = self._relative_signal(
                frames, indices["heel"], indices["hip"], direction_sign
            )
            toe_signal, toe_conf = self._relative_signal(
                frames, indices["toe"], indices["hip"], direction_sign
            )
            heel_signal = self._fill_for_peaks(heel_signal)
            toe_signal = self._fill_for_peaks(toe_signal)
            if heel_signal is None or toe_signal is None:
                warnings.append(f"{side}下肢の接地・離地候補を検出できませんでした。")
                continue

            heel_prominence = max(0.008, float(np.nanstd(heel_signal)) * 0.20)
            toe_prominence = max(0.008, float(np.nanstd(toe_signal)) * 0.20)
            ic_positions, ic_props = find_peaks(
                heel_signal, distance=minimum_distance, prominence=heel_prominence
            )
            to_positions, to_props = find_peaks(
                -toe_signal, distance=minimum_distance, prominence=toe_prominence
            )
            for position, prominence in zip(
                ic_positions, ic_props.get("prominences", []), strict=False
            ):
                confidence = self._event_confidence(
                    float(prominence), heel_prominence, heel_conf[position], direction_confidence
                )
                events.append(
                    GaitEvent(
                        "IC",
                        side,
                        int(timestamps[position]),
                        frames[position].frame_index,
                        confidence,
                    )
                )
            for position, prominence in zip(
                to_positions, to_props.get("prominences", []), strict=False
            ):
                confidence = self._event_confidence(
                    float(prominence), toe_prominence, toe_conf[position], direction_confidence
                )
                events.append(
                    GaitEvent(
                        "TO",
                        side,
                        int(timestamps[position]),
                        frames[position].frame_index,
                        confidence,
                    )
                )

        events.sort(key=lambda item: (item.timestamp_ms, item.side, item.event_type))
        cycles = self.build_cycles(events)
        if len(cycles) < 2:
            warnings.append("解析可能な歩行周期が少ないため、平均値の信頼性が低いです。")
        return direction, direction_confidence, tuple(events), tuple(cycles), tuple(warnings)

    @staticmethod
    def _detect_direction(frames: tuple[PoseFrame, ...]) -> tuple[str, float]:
        samples: list[float] = []
        for frame in frames:
            left = _landmark(frame, 23)
            right = _landmark(frame, 24)
            if left is not None and right is not None:
                samples.append((left.x + right.x) / 2.0)
            elif left is not None:
                samples.append(left.x)
            elif right is not None:
                samples.append(right.x)
            else:
                samples.append(math.nan)
        values = np.asarray(samples, dtype=float)
        valid = values[np.isfinite(values)]
        if len(valid) < 10:
            return "unknown", 0.0
        section = max(3, len(valid) // 5)
        displacement = float(np.median(valid[-section:]) - np.median(valid[:section]))
        confidence = min(1.0, abs(displacement) / 0.20)
        if abs(displacement) < 0.03:
            return "unknown", confidence
        return ("right" if displacement > 0 else "left"), confidence

    @staticmethod
    def _relative_signal(
        frames: tuple[PoseFrame, ...], distal_index: int, hip_index: int, direction_sign: float
    ) -> tuple[np.ndarray, np.ndarray]:
        values = np.full(len(frames), np.nan, dtype=float)
        confidence = np.zeros(len(frames), dtype=float)
        for position, frame in enumerate(frames):
            distal = _landmark(frame, distal_index)
            hip = _landmark(frame, hip_index)
            if distal is None or hip is None:
                continue
            values[position] = direction_sign * (distal.x - hip.x)
            confidence[position] = min(
                distal.visibility, distal.presence, hip.visibility, hip.presence
            )
        return values, confidence

    @staticmethod
    def _fill_for_peaks(values: np.ndarray) -> np.ndarray | None:
        valid = np.flatnonzero(np.isfinite(values))
        if len(valid) < 10:
            return None
        output = values.copy()
        missing = np.flatnonzero(~np.isfinite(output))
        output[missing] = np.interp(missing, valid, output[valid])
        return output

    @staticmethod
    def _event_confidence(
        prominence: float, threshold: float, landmark_confidence: float, direction_confidence: float
    ) -> float:
        signal_score = min(1.0, prominence / max(threshold * 3.0, 1e-6))
        return round(
            max(
                0.0,
                min(
                    1.0,
                    0.55 * signal_score + 0.35 * landmark_confidence + 0.10 * direction_confidence,
                ),
            ),
            3,
        )

    @staticmethod
    def build_cycles(events: list[GaitEvent]) -> list[GaitCycle]:
        cycles: list[GaitCycle] = []
        for side in ("left", "right"):
            initial_contacts = [
                item for item in events if item.side == side and item.event_type == "IC"
            ]
            toe_offs = [item for item in events if item.side == side and item.event_type == "TO"]
            for start, end in zip(initial_contacts, initial_contacts[1:], strict=False):
                duration = end.timestamp_ms - start.timestamp_ms
                if not 700 <= duration <= 2_500:
                    continue
                candidates = [
                    item
                    for item in toe_offs
                    if start.timestamp_ms + 0.25 * duration
                    < item.timestamp_ms
                    < start.timestamp_ms + 0.85 * duration
                ]
                toe_off = max(candidates, key=lambda item: item.confidence) if candidates else None
                confidence = min(start.confidence, end.confidence)
                if toe_off is not None:
                    confidence = min(confidence, toe_off.confidence)
                else:
                    confidence *= 0.6
                cycles.append(
                    GaitCycle(
                        side=side,
                        start_ms=start.timestamp_ms,
                        end_ms=end.timestamp_ms,
                        toe_off_ms=toe_off.timestamp_ms if toe_off else None,
                        confidence=round(confidence, 3),
                    )
                )
        filtered: list[GaitCycle] = []
        for side in ("left", "right"):
            side_cycles = [item for item in cycles if item.side == side]
            if len(side_cycles) < 3:
                filtered.extend(side_cycles)
                continue
            typical_duration = median(item.end_ms - item.start_ms for item in side_cycles)
            filtered.extend(
                item
                for item in side_cycles
                if 0.65 * typical_duration <= item.end_ms - item.start_ms <= 1.50 * typical_duration
            )
        return sorted(filtered, key=lambda item: item.start_ms)
