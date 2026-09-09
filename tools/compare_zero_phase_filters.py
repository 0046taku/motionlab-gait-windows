from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from motionlab_gait.analysis.joint_pipeline import JointAnglePipeline
from motionlab_gait.analysis.landmark_processor import LandmarkProcessor
from motionlab_gait.analysis.types import AnglePoint, GaitCycle
from motionlab_gait.persistence.landmark_store import LandmarkStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare zero-phase landmark filters")
    parser.add_argument("--raw-pose", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
    start_ms = baseline["viewpoint"]["analysis_start_ms"]
    end_ms = baseline["viewpoint"]["analysis_end_ms"]
    full_raw = LandmarkStore().read(args.raw_pose).frames
    raw = tuple(frame for frame in full_raw if start_ms <= frame.timestamp_ms <= end_ms)
    cycles = tuple(GaitCycle(**item) for item in baseline["cycles"])
    baseline_angles = tuple(AnglePoint(**item) for item in baseline["angles"])

    output: dict[str, object] = {
        "video_id": baseline["video_id"],
        "fps": args.fps,
        "baseline": _all_summaries(baseline_angles),
        "candidates": {},
    }
    candidates = output["candidates"]
    assert isinstance(candidates, dict)
    for cutoff in (4.0, 6.0, 8.0):
        filtered_frames, processing = LandmarkProcessor(cutoff_hz=cutoff).process(
            full_raw, fps=args.fps
        )
        filtered_frames = tuple(
            frame
            for frame in filtered_frames
            if start_ms <= frame.timestamp_ms <= end_ms
        )
        bundle = JointAnglePipeline().analyze(
            raw,
            filtered_frames,
            cycles,
            direction=baseline["direction"],
        )
        summaries = _all_summaries(bundle.filtered_angles)
        candidates[str(int(cutoff))] = {
            "processing": asdict(processing),
            "joint_quality": [asdict(item) for item in bundle.quality],
            "joints": summaries,
            "difference_from_baseline": _differences(
                output["baseline"], summaries  # type: ignore[arg-type]
            ),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _all_summaries(points: tuple[AnglePoint, ...]) -> dict[str, object]:
    output: dict[str, object] = {}
    for joint in ("hip_flexion", "knee_flexion", "ankle_dorsiflexion"):
        output[joint] = {}
        for side in ("left", "right"):
            selected = [
                point
                for point in points
                if point.joint == joint
                and point.side == side
                and point.cycle_percent is not None
            ]
            output[joint][side] = _summary(selected)  # type: ignore[index]
    return output


def _summary(points: list[AnglePoint]) -> dict[str, float | int | None]:
    if not points:
        return {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "rom": None,
            "peak_cycle_percent": None,
            "median_frame_change": None,
            "p95_frame_change": None,
            "representative_method": "median_1_percent_bins",
        }
    bins: dict[int, list[float]] = {}
    for point in points:
        assert point.cycle_percent is not None
        bins.setdefault(round(point.cycle_percent), []).append(point.angle_degrees)
    representative = {
        percent: float(np.median(values)) for percent, values in bins.items()
    }
    minimum = min(representative.values())
    maximum = max(representative.values())
    peak_percent = min(
        percent for percent, value in representative.items() if value == maximum
    )
    changes: list[float] = []
    for side_points in (sorted(points, key=lambda point: point.timestamp_ms),):
        changes.extend(
            abs(later.angle_degrees - earlier.angle_degrees)
            for earlier, later in zip(side_points, side_points[1:], strict=False)
            if 0 < later.timestamp_ms - earlier.timestamp_ms <= 100
        )
    return {
        "count": len(points),
        "minimum": round(minimum, 3),
        "maximum": round(maximum, 3),
        "rom": round(maximum - minimum, 3),
        "peak_cycle_percent": peak_percent,
        "median_frame_change": round(float(np.median(changes)), 3) if changes else None,
        "p95_frame_change": round(float(np.percentile(changes, 95)), 3) if changes else None,
        "representative_method": "median_1_percent_bins",
    }


def _differences(
    baseline: dict[str, object], candidate: dict[str, object]
) -> dict[str, object]:
    output: dict[str, object] = {}
    for joint in baseline:
        output[joint] = {}
        for side in ("left", "right"):
            before = baseline[joint][side]  # type: ignore[index]
            after = candidate[joint][side]  # type: ignore[index]
            output[joint][side] = {  # type: ignore[index]
                "minimum_delta_deg": _subtract(after["minimum"], before["minimum"]),
                "maximum_delta_deg": _subtract(after["maximum"], before["maximum"]),
                "rom_delta_deg": _subtract(after["rom"], before["rom"]),
                "peak_timing_delta_percent": _subtract(
                    after["peak_cycle_percent"], before["peak_cycle_percent"]
                ),
                "median_frame_change_reduction_percent": _reduction(
                    before["median_frame_change"], after["median_frame_change"]
                ),
                "p95_frame_change_reduction_percent": _reduction(
                    before["p95_frame_change"], after["p95_frame_change"]
                ),
            }
    return output


def _subtract(after: object, before: object) -> float | None:
    if after is None or before is None:
        return None
    return round(float(after) - float(before), 3)


def _reduction(before: object, after: object) -> float | None:
    if before in (None, 0) or after is None:
        return None
    return round(100.0 * (float(before) - float(after)) / float(before), 1)


if __name__ == "__main__":
    raise SystemExit(main())
