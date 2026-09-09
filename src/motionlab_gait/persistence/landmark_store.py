from __future__ import annotations

import json
import os
from bisect import bisect_left
from collections.abc import Iterable
from pathlib import Path

from motionlab_gait.domain.models import POSE_LANDMARK_NAMES, PoseFrame

SCHEMA_NAME = "motionlab.pose.v1"


class LandmarkStore:
    def write(
        self,
        path: Path,
        *,
        video_id: str,
        source_video_name: str,
        frames: Iterable[PoseFrame],
    ) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        count = 0
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
                metadata = {
                    "type": "metadata",
                    "schema": SCHEMA_NAME,
                    "video_id": video_id,
                    "source_video_name": source_video_name,
                    "timestamp_unit": "milliseconds",
                    "normalized_coordinate_origin": "top_left",
                    "world_coordinate_unit": "meters",
                    "landmark_count": len(POSE_LANDMARK_NAMES),
                    "landmark_names": list(POSE_LANDMARK_NAMES),
                }
                output.write(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
                output.write("\n")
                for frame in frames:
                    output.write(
                        json.dumps(frame.to_dict(), ensure_ascii=False, separators=(",", ":"))
                    )
                    output.write("\n")
                    count += 1
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return count

    def read(self, path: Path) -> PoseTimeline:
        frames: list[PoseFrame] = []
        with path.open("r", encoding="utf-8") as source:
            first_line = source.readline()
            if not first_line:
                raise ValueError("Poseデータが空です。")
            metadata = json.loads(first_line)
            if metadata.get("type") != "metadata" or metadata.get("schema") != SCHEMA_NAME:
                raise ValueError("未対応のPoseデータ形式です。")
            for line in source:
                if not line.strip():
                    continue
                value = json.loads(line)
                if value.get("type") == "frame":
                    frames.append(PoseFrame.from_dict(value))
        return PoseTimeline(frames)


class PoseTimeline:
    def __init__(self, frames: Iterable[PoseFrame]) -> None:
        ordered = sorted(frames, key=lambda frame: (frame.timestamp_ms, frame.frame_index))
        self.frames: tuple[PoseFrame, ...] = tuple(ordered)
        self._timestamps = tuple(frame.timestamp_ms for frame in ordered)

    def nearest(self, timestamp_ms: int, tolerance_ms: int) -> PoseFrame | None:
        if not self.frames:
            return None
        position = bisect_left(self._timestamps, timestamp_ms)
        candidate_positions = [position]
        if position > 0:
            candidate_positions.append(position - 1)
        if position + 1 < len(self.frames):
            candidate_positions.append(position + 1)
        valid_positions = [index for index in candidate_positions if index < len(self.frames)]
        best = min(valid_positions, key=lambda index: abs(self._timestamps[index] - timestamp_ms))
        frame = self.frames[best]
        if abs(frame.timestamp_ms - timestamp_ms) > tolerance_ms:
            return None
        return frame

    def __len__(self) -> int:
        return len(self.frames)
