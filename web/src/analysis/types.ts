import type { PoseFrame, PoseLandmark } from "../domain/models";

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

export interface GaitAnalysisResult {
  analysisVersion: "motionlab-gait-web/0.2.0";
  fps: number;
  direction: "left" | "right" | "unknown";
  directionConfidence: number;
  viewpoint: ViewpointReport;
  processing: ProcessingReport;
  events: GaitEvent[];
  cycles: GaitCycle[];
  angles: AnglePoint[];
  rawAngles: AnglePoint[];
  jointQuality: JointQualityReport[];
  warnings: string[];
}

