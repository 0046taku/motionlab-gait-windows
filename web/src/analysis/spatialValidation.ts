import type { PoseFrame, PoseLandmark } from "../domain/models";
import { clamp, mean, median, standardDeviation } from "./statistics";
import type {
  AnglePoint, CameraSideCheck, CycleValidationReport, GaitCycle, SegmentStabilityReport,
  Side, SpatialValidationReport, StaticStandingValidationReport
} from "./types";

const SIDE_POINTS = {
  left: { shoulder: 11, hip: 23, knee: 25, ankle: 27, heel: 29, toe: 31 },
  right: { shoulder: 12, hip: 24, knee: 26, ankle: 28, heel: 30, toe: 32 }
} as const;

export function validateSpatialBiomechanics(
  frames: readonly PoseFrame[],
  cycles: readonly GaitCycle[],
  rawAngles: readonly AnglePoint[],
  primarySide: Side | null
): SpatialValidationReport {
  const cameraSideCheck = inferCameraSide(frames, primarySide);
  if (!primarySide) return {
    strategy: "camera-side-central-ranked-v1", cameraSideCheck,
    segmentStability: [], cycles: [], selectedCycleCount: 0,
    staticStanding: emptyStaticStanding()
  };
  const segmentSeries = buildSegmentSeries(frames, primarySide);
  const segmentStability = summarizeSegments(segmentSeries);
  const staticStanding = validateInitialStanding(frames, rawAngles, segmentSeries, primarySide);
  const sideCycles = cycles.filter((cycle) => cycle.side === primarySide);
  const reports = sideCycles.map((cycle) => validateCycle(
    cycle, frames, rawAngles, segmentSeries, primarySide
  ));
  const ranked = reports.filter((report) => report.reasons.length === 0)
    .sort((a, b) => b.centralityScore - a.centralityScore).slice(0, 3);
  const selectedKeys = new Set(ranked.map(cycleKey));
  const selectedReports = reports.map((report) => ({ ...report, selected: selectedKeys.has(cycleKey(report)) }));
  return {
    strategy: "camera-side-central-ranked-v1", cameraSideCheck, segmentStability,
    cycles: selectedReports, selectedCycleCount: selectedReports.filter((item) => item.selected).length,
    staticStanding
  };
}

export function cyclesSelectedByValidation(
  cycles: readonly GaitCycle[], report: SpatialValidationReport
): GaitCycle[] {
  const selected = new Set(report.cycles.filter((item) => item.selected).map(cycleKey));
  return cycles.filter((cycle) => selected.has(cycleKey(cycle)));
}

function inferCameraSide(frames: readonly PoseFrame[], selected: Side | null): CameraSideCheck {
  const depthDifferences: number[] = [];
  for (const frame of frames) {
    const points = byIndex(frame);
    const left = [points.get(11), points.get(23), points.get(25)].filter(Boolean) as PoseLandmark[];
    const right = [points.get(12), points.get(24), points.get(26)].filter(Boolean) as PoseLandmark[];
    if (left.length !== 3 || right.length !== 3) continue;
    if ([...left, ...right].some((point) => point.visibility < 0.5)) continue;
    depthDifferences.push(mean(left.map((point) => point.z)) - mean(right.map((point) => point.z)));
  }
  const difference = depthDifferences.length ? median(depthDifferences) : 0;
  const confidence = clamp((Math.abs(difference) - 0.02) / 0.12);
  const inferredSide: Side | null = confidence >= 0.35 ? (difference < 0 ? "left" : "right") : null;
  const agreement = !selected || !inferredSide || confidence < 0.65
    ? "unknown" : selected === inferredSide ? "consistent" : "conflict";
  return { userSelectedSide: selected, inferredSide, confidence, agreement };
}

type SegmentName = SegmentStabilityReport["segment"];
type SegmentSample = { timestampMs: number; values: Partial<Record<SegmentName, number>> };

function buildSegmentSeries(frames: readonly PoseFrame[], side: Side): SegmentSample[] {
  const indices = SIDE_POINTS[side];
  return frames.map((frame) => {
    const points = byIndex(frame); const width = frame.frameWidth; const height = frame.frameHeight;
    const length = (first: number, second: number): number | undefined => {
      const a = points.get(first); const b = points.get(second);
      if (!a || !b || !width || !height || Math.min(a.visibility, b.visibility) < 0.5) return undefined;
      return Math.hypot((a.x - b.x) * width, (a.y - b.y) * height);
    };
    return { timestampMs: frame.timestampMs, values: {
      shoulder_hip: length(indices.shoulder, indices.hip),
      hip_knee: length(indices.hip, indices.knee),
      knee_ankle: length(indices.knee, indices.ankle),
      heel_toe: length(indices.heel, indices.toe)
    } };
  });
}

function summarizeSegments(samples: readonly SegmentSample[]): SegmentStabilityReport[] {
  const names: SegmentName[] = ["shoulder_hip", "hip_knee", "knee_ankle", "heel_toe"];
  return names.map((segment) => {
    const values = samples.map((sample) => sample.values[segment]).filter((value): value is number => value !== undefined);
    const middle = median(values); const sudden = suddenSegmentFrames(samples, segment, middle);
    return {
      segment, medianLengthPx: round(middle),
      coefficientOfVariation: middle > 0 ? round(standardDeviation(values) / middle) : 0,
      suddenChangeRate: values.length ? round(sudden.size / values.length) : 1
    };
  });
}

function emptyStaticStanding(): StaticStandingValidationReport {
  return {
    method: "initial-window-validation-v1", status: "insufficient", windowStartMs: null, windowEndMs: null,
    frameCount: 0, pelvisTravelTorsoRatio: null, cameraSideCoverage: 0, kneeRawJitterDegrees: null,
    segmentLengthCoefficientOfVariation: null, ankleNeutralCandidateDegrees: null, appliedAsCalibration: false
  };
}

function validateInitialStanding(
  frames: readonly PoseFrame[], rawAngles: readonly AnglePoint[], segments: readonly SegmentSample[], side: Side
): StaticStandingValidationReport {
  if (!frames.length) return emptyStaticStanding();
  const startMs = frames[0]!.timestampMs;
  const endMs = Math.min(startMs + 2_000, frames.at(-1)!.timestampMs);
  const windowFrames = frames.filter((frame) => frame.timestampMs >= startMs && frame.timestampMs <= endMs);
  const indices = SIDE_POINTS[side];
  const pelvis: { x: number; y: number }[] = [];
  let visibleFrames = 0;
  for (const frame of windowFrames) {
    const points = byIndex(frame); const hip = points.get(indices.hip);
    const required = [points.get(indices.shoulder), hip, points.get(indices.knee), points.get(indices.ankle)];
    if (required.every((point) => point && point.visibility >= 0.5)) visibleFrames += 1;
    if (hip && frame.frameWidth && frame.frameHeight && hip.visibility >= 0.5) {
      pelvis.push({ x: hip.x * frame.frameWidth, y: hip.y * frame.frameHeight });
    }
  }
  const torsoLengths = segments.filter((sample) => sample.timestampMs >= startMs && sample.timestampMs <= endMs)
    .map((sample) => sample.values.shoulder_hip).filter((value): value is number => value !== undefined);
  const torso = median(torsoLengths);
  const pelvisTravel = pelvis.length > 1
    ? Math.hypot(pelvis.at(-1)!.x - pelvis[0]!.x, pelvis.at(-1)!.y - pelvis[0]!.y) : Number.NaN;
  const pelvisTravelTorsoRatio = torso > 0 && Number.isFinite(pelvisTravel) ? pelvisTravel / torso : null;
  const knee = rawAngles.filter((point) => point.side === side && point.joint === "knee_flexion"
    && point.timestampMs >= startMs && point.timestampMs <= endMs).map((point) => point.angleDegrees);
  const ankle = rawAngles.filter((point) => point.side === side && point.joint === "ankle_dorsiflexion"
    && point.timestampMs >= startMs && point.timestampMs <= endMs).map((point) => point.angleDegrees);
  const segmentCv = torso > 0 && torsoLengths.length > 2 ? standardDeviation(torsoLengths) / torso : null;
  const coverage = windowFrames.length ? visibleFrames / windowFrames.length : 0;
  const enough = windowFrames.length >= 10 && endMs - startMs >= 900 && pelvis.length >= 10 && knee.length >= 5;
  const status = !enough ? "insufficient"
    : pelvisTravelTorsoRatio !== null && pelvisTravelTorsoRatio <= 0.12 ? "candidate" : "moving";
  return {
    method: "initial-window-validation-v1", status, windowStartMs: startMs, windowEndMs: endMs,
    frameCount: windowFrames.length, pelvisTravelTorsoRatio: nullableRound(pelvisTravelTorsoRatio),
    cameraSideCoverage: round(coverage), kneeRawJitterDegrees: knee.length > 1 ? round(standardDeviation(knee)) : null,
    segmentLengthCoefficientOfVariation: nullableRound(segmentCv),
    ankleNeutralCandidateDegrees: ankle.length ? round(median(ankle)) : null,
    appliedAsCalibration: false
  };
}

function validateCycle(
  cycle: GaitCycle, frames: readonly PoseFrame[], rawAngles: readonly AnglePoint[],
  segments: readonly SegmentSample[], side: Side
): CycleValidationReport {
  const cycleFrames = frames.filter((frame) => frame.timestampMs >= cycle.startMs && frame.timestampMs <= cycle.endMs);
  const sagittalScores = cycleFrames.map(sideViewScore).filter((score) => Number.isFinite(score));
  const centers = cycleFrames.map(subjectCenterX).filter((value): value is number => value !== null);
  const centralityScore = centers.length ? clamp(1 - 2 * Math.abs(median(centers) - 0.5)) : 0;
  const outOfPlaneFrameRate = sagittalScores.length
    ? sagittalScores.filter((score) => score < 0.60).length / sagittalScores.length : 1;
  const outOfPlaneRisk = sagittalScores.length ? 1 - median(sagittalScores) : 1;
  const sampleIndices = segments.map((sample, index) => sample.timestampMs >= cycle.startMs && sample.timestampMs <= cycle.endMs ? index : -1)
    .filter((index) => index >= 0);
  const unstable = new Set<number>();
  for (const name of ["shoulder_hip", "hip_knee", "knee_ankle", "heel_toe"] as SegmentName[]) {
    const values = segments.map((sample) => sample.values[name]).filter((value): value is number => value !== undefined);
    const middle = median(values);
    for (const index of suddenSegmentFrames(segments, name, middle)) if (sampleIndices.includes(index)) unstable.add(index);
  }
  const segmentInstabilityRate = cycleFrames.length ? unstable.size / cycleFrames.length : 1;
  const knee = rawAngles.filter((point) => point.side === side && point.joint === "knee_flexion"
    && point.timestampMs >= cycle.startMs && point.timestampMs <= cycle.endMs).sort((a, b) => a.timestampMs - b.timestampMs);
  let kinematicFlags = 0;
  for (let index = 1; index < knee.length - 1; index += 1) {
    const before = knee[index - 1]!; const current = knee[index]!; const after = knee[index + 1]!;
    const isolatedJump = Math.abs(current.angleDegrees - (before.angleDegrees + after.angleDegrees) / 2) > 20
      && Math.abs(before.angleDegrees - after.angleDegrees) < 10;
    const correspondingFrame = frames.findIndex((frame) => frame.timestampMs === current.timestampMs);
    if (isolatedJump && (current.confidence < 0.8 || unstable.has(correspondingFrame))) kinematicFlags += 1;
  }
  const kinematicRiskRate = knee.length ? kinematicFlags / knee.length : 1;
  const reasons: string[] = [];
  if (cycle.confidence < 0.50) reasons.push("歩行イベント信頼度が低い");
  if (outOfPlaneFrameRate > 0.20) reasons.push("側方性が不十分");
  if (segmentInstabilityRate > 0.10) reasons.push("segment長が不安定");
  if (kinematicRiskRate > 0.10) reasons.push("運動学的な単発jumpを検出");
  return {
    side, startMs: cycle.startMs, endMs: cycle.endMs, centralityScore: round(centralityScore),
    outOfPlaneRisk: round(outOfPlaneRisk), outOfPlaneFrameRate: round(outOfPlaneFrameRate),
    segmentInstabilityRate: round(segmentInstabilityRate), kinematicRiskRate: round(kinematicRiskRate),
    selected: false, reasons
  };
}

function suddenSegmentFrames(samples: readonly SegmentSample[], name: SegmentName, medianLength: number): Set<number> {
  const output = new Set<number>();
  if (medianLength <= 0) return output;
  for (let index = 1; index < samples.length - 1; index += 1) {
    const before = samples[index - 1]!.values[name]; const current = samples[index]!.values[name]; const after = samples[index + 1]!.values[name];
    if (before === undefined || current === undefined || after === undefined) continue;
    const isolated = Math.abs(current - (before + after) / 2) / medianLength > 0.15;
    const neighborsAgree = Math.abs(before - after) / medianLength < 0.08;
    if (isolated && neighborsAgree) output.add(index);
  }
  return output;
}

function sideViewScore(frame: PoseFrame): number {
  const points = byIndex(frame); const width = frame.frameWidth; const height = frame.frameHeight;
  const leftShoulder = points.get(11); const rightShoulder = points.get(12); const leftHip = points.get(23); const rightHip = points.get(24);
  if (!width || !height || !leftShoulder || !rightShoulder || !leftHip || !rightHip) return 0;
  const shoulderMid = [(leftShoulder.x + rightShoulder.x) * width / 2, (leftShoulder.y + rightShoulder.y) * height / 2];
  const hipMid = [(leftHip.x + rightHip.x) * width / 2, (leftHip.y + rightHip.y) * height / 2];
  const torso = Math.hypot(shoulderMid[0]! - hipMid[0]!, shoulderMid[1]! - hipMid[1]!);
  if (torso <= 1e-6) return 0;
  const shoulderWidth = Math.hypot((leftShoulder.x - rightShoulder.x) * width, (leftShoulder.y - rightShoulder.y) * height) / torso;
  const hipWidth = Math.hypot((leftHip.x - rightHip.x) * width, (leftHip.y - rightHip.y) * height) / torso;
  const shoulderDepth = Math.abs(leftShoulder.z - rightShoulder.z) * width / torso;
  return 0.35 * clamp((1.05 - shoulderWidth) / 0.65) + 0.35 * clamp((0.70 - hipWidth) / 0.45)
    + 0.30 * clamp((shoulderDepth - 0.50) / 1.50);
}

function subjectCenterX(frame: PoseFrame): number | null {
  const points = byIndex(frame);
  const candidates = [points.get(11), points.get(12), points.get(23), points.get(24)].filter(Boolean) as PoseLandmark[];
  return candidates.length >= 2 ? median(candidates.map((point) => point.x)) : null;
}

function byIndex(frame: PoseFrame): Map<number, PoseLandmark> {
  return new Map(frame.landmarks.map((landmark) => [landmark.index, landmark]));
}

function cycleKey(cycle: { side: Side; startMs: number; endMs: number }): string {
  return `${cycle.side}:${cycle.startMs}:${cycle.endMs}`;
}

function round(value: number): number { return Math.round(value * 10_000) / 10_000; }
function nullableRound(value: number | null): number | null { return value === null ? null : round(value); }
