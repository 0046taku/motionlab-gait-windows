import type { PoseFrame, PoseLandmark, VideoAnalysisMetadata } from "../domain/models";

export type Side = "left" | "right";
export type Joint = "hip_flexion" | "knee_flexion" | "ankle_dorsiflexion";
export type QualityStatus = "high" | "caution" | "difficult";

export interface ProcessedLandmark extends PoseLandmark {
  interpolated: boolean;
  outlierReplaced: boolean;
}

export interface ProcessedPoseFrame extends Omit<PoseFrame, "landmarks"> {
  landmarks: ProcessedLandmark[];
}

export interface ProcessingReport {
  frameCount: number;
  interpolatedValues: number;
  replacedOutliers: number;
  confidenceThreshold: number;
  maxInterpolationGapMs: number;
  filterType: "butterworth_lowpass";
  filterOrder: 4;
  cutoffHz: number;
  zeroPhase: true;
  presenceFallback: boolean;
}

export interface ViewpointReport {
  classification: "sagittal" | "mixed" | "frontal_or_oblique" | "insufficient";
  sagittalFraction: number;
  stableSagittalScore: number;
  analysisStartMs: number | null;
  analysisEndMs: number | null;
  analysisFrameCount: number;
  analysisSupported: boolean;
  warnings: string[];
}

export interface GaitEvent {
  eventType: "IC" | "TO";
  side: Side;
  timestampMs: number;
  frameIndex: number;
  confidence: number;
}

export interface GaitCycle {
  side: Side;
  startMs: number;
  endMs: number;
  toeOffMs: number | null;
  confidence: number;
}

export interface AnglePoint {
  timestampMs: number;
  cyclePercent: number | null;
  side: Side;
  joint: Joint;
  angleDegrees: number;
  confidence: number;
}

export interface JointQualityReport {
  joint: Joint;
  status: QualityStatus;
  meanVisibility: number;
  meanPresence: number;
  outlierRate: number;
  interpolationRate: number;
  trackingContinuity: number;
  usablePointRate: number;
  angleJumpRate: number;
  segmentConsistency: number;
  validCycleCount: number;
  excludedCycleCount: number;
  warnings: string[];
}

export interface AcquisitionQuality {
  status: "high" | "caution" | "retake";
  reasons: string[];
  fullBodyCoverage: number;
  footCoverage: number;
  primaryLimbCoverage: number;
  cameraStability: number;
  sideViewScore: number;
  cycleCount: number;
  cameraSideAgreement: "consistent" | "conflict" | "unknown";
}

export interface CameraSideCheck {
  userSelectedSide: Side | null;
  inferredSide: Side | null;
  confidence: number;
  agreement: "consistent" | "conflict" | "unknown";
}

export interface SegmentStabilityReport {
  segment: "shoulder_hip" | "hip_knee" | "knee_ankle" | "heel_toe";
  medianLengthPx: number;
  coefficientOfVariation: number;
  suddenChangeRate: number;
}

export interface CycleValidationReport {
  side: Side;
  startMs: number;
  endMs: number;
  centralityScore: number;
  outOfPlaneRisk: number;
  outOfPlaneFrameRate: number;
  segmentInstabilityRate: number;
  kinematicRiskRate: number;
  selected: boolean;
  reasons: string[];
}

export interface StaticStandingValidationReport {
  method: "initial-window-validation-v1";
  status: "candidate" | "moving" | "insufficient";
  windowStartMs: number | null;
  windowEndMs: number | null;
  frameCount: number;
  pelvisTravelTorsoRatio: number | null;
  cameraSideCoverage: number;
  kneeRawJitterDegrees: number | null;
  segmentLengthCoefficientOfVariation: number | null;
  ankleNeutralCandidateDegrees: number | null;
  /** This report never changes raw or filtered joint angles. */
  appliedAsCalibration: false;
}

export interface SpatialValidationReport {
  strategy: "camera-side-central-ranked-v1";
  cameraSideCheck: CameraSideCheck;
  segmentStability: SegmentStabilityReport[];
  cycles: CycleValidationReport[];
  selectedCycleCount: number;
  staticStanding: StaticStandingValidationReport;
}

export interface FilterCandidateValidation {
  cutoffHz: 4 | 6 | 8;
  joint: Joint;
  side: Side;
  highFrequencyResidual: number;
  peakAttenuation: number;
  romAttenuation: number;
  peakTimingShiftMs: number;
  rawFrameToFrameVariation: number;
  filteredFrameToFrameVariation: number;
}

export interface AnalysisVersions {
  analysisVersion: "motionlab-gait-web/0.4.0";
  poseModelVersion: "@mediapipe/tasks-vision@1.0.1/pose_landmarker_full";
  filterVersion: "butterworth4-zero-phase-v1";
  angleDefinitionVersion: "sagittal-pixel-v2";
  eventDetectorVersion: "multisignal-v2";
}

export interface GaitAnalysisResult {
  analysisVersion: "motionlab-gait-web/0.4.0";
  versions: AnalysisVersions;
  fps: number;
  videoMetadata?: VideoAnalysisMetadata;
  primarySide: Side | null;
  acquisitionQuality: AcquisitionQuality;
  direction: "left" | "right" | "unknown";
  directionConfidence: number;
  viewpoint: ViewpointReport;
  processing: ProcessingReport;
  events: GaitEvent[];
  cycles: GaitCycle[];
  angles: AnglePoint[];
  rawAngles: AnglePoint[];
  continuousRawAngles: AnglePoint[];
  continuousFilteredAngles: AnglePoint[];
  jointQuality: JointQualityReport[];
  filterValidation: FilterCandidateValidation[];
  spatialValidation: SpatialValidationReport;
  warnings: string[];
}
