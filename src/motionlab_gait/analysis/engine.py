from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from motionlab_gait.analysis.event_detector import GaitEventDetector
from motionlab_gait.analysis.findings import summarize_observed_features
from motionlab_gait.analysis.joint_pipeline import JointAnglePipeline
from motionlab_gait.analysis.kinematics import calculate_temporal_metrics
from motionlab_gait.analysis.landmark_processor import LandmarkProcessor
from motionlab_gait.analysis.quality import assess_pose_quality
from motionlab_gait.analysis.result_store import AnalysisResultStore
from motionlab_gait.analysis.types import GaitAnalysisResult, GaitEvent
from motionlab_gait.analysis.viewpoint import assess_viewpoint, select_analysis_frames
from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore

ANALYSIS_VERSION = "motionlab-gait-windows/0.4.0"


class GaitAnalysisEngine:
    def __init__(
        self,
        landmark_store: LandmarkStore | None = None,
        result_store: AnalysisResultStore | None = None,
    ) -> None:
        self.landmark_store = landmark_store or LandmarkStore()
        self.result_store = result_store or AnalysisResultStore()
        self.processor = LandmarkProcessor()
        self.event_detector = GaitEventDetector()
        self.joint_pipeline = JointAnglePipeline()

    def analyze(
        self, video: VideoRecord, raw_pose_path: Path
    ) -> tuple[Path, Path, GaitAnalysisResult]:
        raw_timeline = self.landmark_store.read(raw_pose_path)
        raw_frames = raw_timeline.frames
        processed_frames, processing = self.processor.process(raw_frames, fps=video.fps)
        viewpoint = assess_viewpoint(processed_frames, fps=video.fps)
        analysis_frames = select_analysis_frames(processed_frames, viewpoint)
        raw_analysis_frames = select_analysis_frames(raw_frames, viewpoint)
        quality_frames = select_analysis_frames(raw_frames, viewpoint) or raw_frames
        quality = assess_pose_quality(
            quality_frames,
            expected_frame_count=len(quality_frames),
            fps=video.fps,
            viewpoint=viewpoint,
        )
        direction, direction_confidence, events, cycles, event_warnings = (
            self.event_detector.detect(analysis_frames, fps=video.fps)
        )
        temporal = calculate_temporal_metrics(
            events,
            cycles,
            known_distance_m=video.known_distance_m,
            distance_start_ms=video.distance_start_ms,
            distance_end_ms=video.distance_end_ms,
        )
        joint_analysis = self.joint_pipeline.analyze(
            raw_analysis_frames,
            analysis_frames,
            cycles,
            direction=direction,
        )
        angles = joint_analysis.filtered_angles
        observed, checks = summarize_observed_features(
            temporal, angles, affected_side=video.affected_side
        )
        warnings = tuple(dict.fromkeys((*quality.warnings, *event_warnings)))
        limitations = (
            "単眼2D動画からの自動推定であり、三次元動作解析装置の代替ではありません。",
            "IC/TOと関節角度は研究・評価用の未検証推定値です。診断には使用しないでください。",
            "足関節角度は靴・遮蔽・カメラ視点の影響が大きく、信頼度を低く設定しています。",
        )
        processed_path = raw_pose_path.with_name(
            raw_pose_path.name.replace(".pose.jsonl", ".processed.pose.jsonl")
        )
        result_path = raw_pose_path.with_name(
            raw_pose_path.name.replace(".pose.jsonl", ".analysis.json")
        )
        result = GaitAnalysisResult(
            schema="motionlab.gait-analysis.v1",
            analysis_version=ANALYSIS_VERSION,
            video_id=video.id,
            created_at=datetime.now(UTC).isoformat(),
            direction=direction,
            direction_confidence=direction_confidence,
            quality=quality,
            viewpoint=viewpoint,
            processing=processing,
            events=events,
            cycles=cycles,
            temporal_metrics=temporal,
            angles=angles,
            joint_quality=joint_analysis.quality,
            raw_angles=joint_analysis.raw_angles,
            angle_debug=joint_analysis.debug,
            observed_features=observed,
            clinical_check_candidates=checks,
            warnings=warnings,
            limitations=limitations,
            provenance={
                "raw_pose_path": str(raw_pose_path),
                "processed_pose_path": str(processed_path),
                "raw_pose_preserved": True,
                "filter": (
                    "4th-order Butterworth low-pass at 6 Hz, zero-phase "
                    "forward-backward filtering on finite landmark segments"
                ),
                "outlier_method": (
                    "velocity MAD threshold with opposite-direction return; "
                    "only 1-2 frame landmark excursions"
                ),
                "representative_cycle": (
                    "median in 1 percent gait-cycle bins after joint-specific "
                    "low-quality cycle exclusion"
                ),
                "event_method": "direction-adjusted heel/toe extrema relative to ipsilateral hip",
                "analysis_window": {
                    "start_ms": viewpoint.analysis_start_ms,
                    "end_ms": viewpoint.analysis_end_ms,
                    "selection": "longest stable sagittal-view segment",
                },
                "symmetry_formula": "100*abs(L-R)/(0.5*(L+R)); 0 is symmetric",
                "affected_side": video.affected_side,
                "angle_convention": {
                    "hip_flexion": "positive forward flexion relative to trunk-down axis",
                    "knee_flexion": "180 degrees minus included hip-knee-ankle angle",
                    "ankle_dorsiflexion": (
                        "90 degrees minus angle between shank and heel-to-toe axis"
                    ),
                },
            },
        )
        self.landmark_store.write(
            processed_path,
            video_id=video.id,
            source_video_name=video.original_name,
            frames=processed_frames,
        )
        self.result_store.write(result_path, result)
        return processed_path.resolve(), result_path.resolve(), result

    def apply_manual_events(
        self, video: VideoRecord, events: tuple[GaitEvent, ...]
    ) -> dict[str, object]:
        if video.result_path is None or video.processed_pose_path is None:
            raise ValueError("解析結果または加工済みPoseがありません。")
        result = self.result_store.read_dict(video.result_path)
        frames = self.landmark_store.read(video.processed_pose_path).frames
        viewpoint = result.get("viewpoint", {})
        start_ms = viewpoint.get("analysis_start_ms")
        end_ms = viewpoint.get("analysis_end_ms")
        if start_ms is not None and end_ms is not None:
            frames = tuple(
                frame for frame in frames if int(start_ms) <= frame.timestamp_ms <= int(end_ms)
            )
            events = tuple(
                item for item in events if int(start_ms) <= item.timestamp_ms <= int(end_ms)
            )
        ordered_events = tuple(sorted(events, key=lambda item: item.timestamp_ms))
        cycles = tuple(self.event_detector.build_cycles(list(ordered_events)))
        temporal = calculate_temporal_metrics(
            ordered_events,
            cycles,
            known_distance_m=video.known_distance_m,
            distance_start_ms=video.distance_start_ms,
            distance_end_ms=video.distance_end_ms,
        )
        raw_frames = frames
        raw_pose_path = Path(str(result.get("provenance", {}).get("raw_pose_path", "")))
        if raw_pose_path.is_file():
            raw_frames = self.landmark_store.read(raw_pose_path).frames
            if start_ms is not None and end_ms is not None:
                raw_frames = tuple(
                    frame
                    for frame in raw_frames
                    if int(start_ms) <= frame.timestamp_ms <= int(end_ms)
                )
        joint_analysis = self.joint_pipeline.analyze(
            raw_frames,
            frames,
            cycles,
            direction=str(result.get("direction", "unknown")),
        )
        angles = joint_analysis.filtered_angles
        observed, checks = summarize_observed_features(
            temporal, angles, affected_side=video.affected_side
        )
        result["events"] = [asdict(item) for item in ordered_events]
        result["cycles"] = [asdict(item) for item in cycles]
        result["temporal_metrics"] = asdict(temporal)
        result["angles"] = [asdict(item) for item in angles]
        result["raw_angles"] = [asdict(item) for item in joint_analysis.raw_angles]
        result["joint_quality"] = [asdict(item) for item in joint_analysis.quality]
        result["angle_debug"] = joint_analysis.debug
        result["observed_features"] = list(observed)
        result["clinical_check_candidates"] = list(checks)
        provenance = dict(result.get("provenance", {}))
        provenance["manual_event_correction_at"] = datetime.now(UTC).isoformat()
        result["provenance"] = provenance
        warnings = list(result.get("warnings", []))
        message = "IC/TO時刻はユーザーが確認・修正しています。"
        if message not in warnings:
            warnings.append(message)
        result["warnings"] = warnings
        self.result_store.write_dict(video.result_path, result)
        return result
