from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from motionlab_gait.analysis.engine import GaitAnalysisEngine
from motionlab_gait.analysis.types import GaitAnalysisResult
from motionlab_gait.domain.models import PoseFrame, VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore
from motionlab_gait.pose.base import PoseProvider
from motionlab_gait.privacy.face_anonymizer import AnonymizationReport, FaceAnonymizer

ProgressCallback = Callable[[int, int], None]
StageCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]
ProviderFactory = Callable[[Path], PoseProvider]


@dataclass(frozen=True, slots=True)
class PoseAnalysisSummary:
    output_path: Path
    frame_count: int
    detected_frame_count: int
    processed_pose_path: Path
    result_path: Path
    analysis_result: GaitAnalysisResult
    anonymization_report: AnonymizationReport | None = None
    anonymization_error: str | None = None


class PoseAnalysisCancelled(RuntimeError):
    pass


class PoseAnalysisService:
    def __init__(
        self,
        model_path: Path,
        landmark_root: Path,
        provider_factory: ProviderFactory,
        landmark_store: LandmarkStore | None = None,
        gait_engine: GaitAnalysisEngine | None = None,
        face_anonymizer: FaceAnonymizer | None = None,
    ) -> None:
        self.model_path = model_path
        self.landmark_root = landmark_root
        self.provider_factory = provider_factory
        self.landmark_store = landmark_store or LandmarkStore()
        self.gait_engine = gait_engine or GaitAnalysisEngine(self.landmark_store)
        self.face_anonymizer = face_anonymizer

    def analyze(
        self,
        video: VideoRecord,
        *,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
        stage: StageCallback | None = None,
    ) -> PoseAnalysisSummary:
        import cv2

        output_path = self.landmark_root / video.patient_id / f"{video.id}.pose.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(str(video.stored_path))
        if not capture.isOpened():
            raise RuntimeError("保存動画をPose解析用に開けませんでした。")

        processed = 0
        detected = 0
        last_timestamp = -1

        try:
            if stage:
                stage("pose")
            with self.provider_factory(self.model_path) as provider:

                def frame_stream() -> Iterator[PoseFrame]:
                    nonlocal processed, detected, last_timestamp
                    frame_index = 0
                    while True:
                        if is_cancelled and is_cancelled():
                            raise PoseAnalysisCancelled("Pose解析を中止しました。")
                        ok, bgr_frame = capture.read()
                        if not ok:
                            break
                        fallback_timestamp = round(frame_index * 1000.0 / video.fps)
                        decoded_timestamp = round(float(capture.get(cv2.CAP_PROP_POS_MSEC)))
                        if frame_index == 0:
                            timestamp_ms = max(0, decoded_timestamp)
                        elif decoded_timestamp > last_timestamp:
                            timestamp_ms = decoded_timestamp
                        else:
                            timestamp_ms = fallback_timestamp
                        timestamp_ms = max(last_timestamp + 1, timestamp_ms)
                        last_timestamp = timestamp_ms

                        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                        landmarks = provider.detect(rgb_frame, timestamp_ms)
                        if landmarks:
                            detected += 1
                        processed += 1
                        if progress:
                            progress(processed, video.frame_count)
                        yield PoseFrame(
                            frame_index=frame_index,
                            timestamp_ms=timestamp_ms,
                            landmarks=landmarks,
                        )
                        frame_index += 1

                written = self.landmark_store.write(
                    output_path,
                    video_id=video.id,
                    source_video_name=video.original_name,
                    frames=frame_stream(),
                )
        finally:
            capture.release()

        if stage:
            stage("gait")
        processed_pose_path, result_path, gait_result = self.gait_engine.analyze(
            video, output_path.resolve()
        )
        anonymization_report = None
        anonymization_error = None
        if video.anonymize_face and self.face_anonymizer is not None:
            try:
                if stage:
                    stage("anonymize")
                anonymization_report = self.face_anonymizer.anonymize(
                    video,
                    processed_pose_path,
                    is_cancelled=is_cancelled,
                    progress=progress,
                )
            except Exception as error:
                anonymization_error = str(error)
        return PoseAnalysisSummary(
            output_path=output_path.resolve(),
            frame_count=written,
            detected_frame_count=detected,
            processed_pose_path=processed_pose_path,
            result_path=result_path,
            analysis_result=gait_result,
            anonymization_report=anonymization_report,
            anonymization_error=anonymization_error,
        )
