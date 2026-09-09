from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class QualityComponent:
    name: str
    score: float
    message: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    grade: str
    score: float
    detection_rate: float
    mean_visibility: float
    continuity: float
    jump_rate: float
    lower_limb_visibility: float
    components: tuple[QualityComponent, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ViewpointReport:
    classification: str
    sagittal_fraction: float
    stable_sagittal_score: float
    analysis_start_ms: int | None
    analysis_end_ms: int | None
    analysis_frame_count: int
    analysis_supported: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessingReport:
    frame_count: int
    interpolated_values: int
    replaced_outliers: int
    smoothing_window_frames: int
    confidence_threshold: float
    max_interpolation_gap_ms: int
    low_confidence_landmarks: int = 0
    filter_type: str = "butterworth_lowpass"
    filter_order: int = 4
    cutoff_hz: float = 6.0
    zero_phase: bool = True


@dataclass(frozen=True, slots=True)
class GaitEvent:
    event_type: str
    side: str
    timestamp_ms: int
    frame_index: int
    confidence: float
    source: str = "automatic"


@dataclass(frozen=True, slots=True)
class GaitCycle:
    side: str
    start_ms: int
    end_ms: int
    toe_off_ms: int | None
    confidence: float


@dataclass(frozen=True, slots=True)
class MetricValue:
    name: str
    value: float | None
    unit: str
    confidence: float
    note: str = ""


@dataclass(frozen=True, slots=True)
class TemporalMetrics:
    values: tuple[MetricValue, ...]
    left_cycle_count: int
    right_cycle_count: int


@dataclass(frozen=True, slots=True)
class AnglePoint:
    timestamp_ms: int
    cycle_percent: float | None
    side: str
    joint: str
    angle_degrees: float
    confidence: float


@dataclass(frozen=True, slots=True)
class JointQualityReport:
    joint: str
    status: str
    mean_visibility: float
    mean_presence: float
    outlier_rate: float
    interpolation_rate: float
    tracking_continuity: float
    usable_point_rate: float
    angle_jump_rate: float
    segment_consistency: float
    valid_cycle_count: int
    excluded_cycle_count: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GaitAnalysisResult:
    schema: str
    analysis_version: str
    video_id: str
    created_at: str
    direction: str
    direction_confidence: float
    quality: QualityReport
    viewpoint: ViewpointReport
    processing: ProcessingReport
    events: tuple[GaitEvent, ...]
    cycles: tuple[GaitCycle, ...]
    temporal_metrics: TemporalMetrics
    angles: tuple[AnglePoint, ...]
    joint_quality: tuple[JointQualityReport, ...]
    raw_angles: tuple[AnglePoint, ...] = ()
    angle_debug: dict[str, Any] = field(default_factory=dict)
    observed_features: tuple[str, ...] = ()
    clinical_check_candidates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
