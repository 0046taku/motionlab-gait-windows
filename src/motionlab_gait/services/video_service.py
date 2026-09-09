from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from motionlab_gait.domain.models import VideoRecord

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"}


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    duration_ms: int
    fps: float
    frame_count: int
    width: int
    height: int


class VideoImportError(ValueError):
    pass


class VideoService:
    def __init__(self, video_root: Path) -> None:
        self.video_root = video_root

    def import_for_patient(self, source: Path, patient_id: str) -> VideoRecord:
        source = source.resolve()
        if not source.is_file():
            raise VideoImportError("選択した動画ファイルが見つかりません。")
        extension = source.suffix.lower()
        if extension not in SUPPORTED_VIDEO_EXTENSIONS:
            raise VideoImportError(
                "対応していない動画形式です。MP4 / MOV / AVI等を選択してください。"
            )

        metadata = self.probe(source)
        video_id = str(uuid.uuid4())
        patient_directory = self.video_root / patient_id
        patient_directory.mkdir(parents=True, exist_ok=True)
        destination = patient_directory / f"{video_id}{extension}"
        try:
            shutil.copy2(source, destination)
        except OSError as error:
            destination.unlink(missing_ok=True)
            raise VideoImportError(f"動画を保存できませんでした: {error}") from error

        return VideoRecord(
            id=video_id,
            patient_id=patient_id,
            original_name=source.name,
            stored_path=destination.resolve(),
            imported_at=datetime.now(UTC),
            duration_ms=metadata.duration_ms,
            fps=metadata.fps,
            frame_count=metadata.frame_count,
            width=metadata.width,
            height=metadata.height,
        )

    @staticmethod
    def probe(path: Path) -> VideoMetadata:
        try:
            import cv2
        except ImportError as error:
            raise VideoImportError("OpenCVがインストールされていません。") from error

        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise VideoImportError(
                    "動画を開けません。コーデックまたはファイルを確認してください。"
                )
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
                raise VideoImportError("動画情報を読み取れません。別のMP4動画で試してください。")
            duration_ms = max(1, round(frame_count * 1000.0 / fps))
            ok, _ = capture.read()
            if not ok:
                raise VideoImportError("動画の先頭フレームを読み取れません。")
        finally:
            capture.release()
        return VideoMetadata(
            duration_ms=duration_ms,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
        )
