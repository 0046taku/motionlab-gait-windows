from __future__ import annotations

import argparse
from pathlib import Path

from motionlab_gait.analysis.engine import GaitAnalysisEngine
from motionlab_gait.persistence.database import Database
from motionlab_gait.persistence.video_repository import VideoRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Reanalyze a stored immutable Raw Pose")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--video-id", required=True)
    args = parser.parse_args()

    database = Database(args.data_root.resolve() / "motionlab.sqlite3")
    repository = VideoRepository(database)
    video = repository.get(args.video_id)
    if video is None or video.pose_path is None or not video.pose_path.is_file():
        raise RuntimeError("指定動画のRaw Poseが見つかりません。")

    processed_path, result_path, result = GaitAnalysisEngine().analyze(
        video, video.pose_path
    )
    repository.mark_analysis_ready(
        video.id,
        processed_pose_path=processed_path,
        result_path=result_path,
        quality_grade=result.quality.grade,
        analysis_version=result.analysis_version,
        anonymized_video_path=video.anonymized_video_path,
    )
    print(f"VIDEO_ID={video.id}")
    print(f"VERSION={result.analysis_version}")
    print(f"PROCESSED={processed_path}")
    print(f"RESULT={result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
