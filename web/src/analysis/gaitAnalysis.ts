import type { PoseFrame, PoseLandmark } from "../domain/models";
import { effectivePresence, processLandmarks } from "./landmarkProcessor";
import { clamp, mean, median, round, standardDeviation } from "./statistics";
import type {
  AnglePoint, GaitAnalysisResult, GaitCycle, GaitEvent, Joint,
  JointQualityReport, ProcessedPoseFrame, Side, ViewpointReport
} from "./types";

const SIDES: readonly Side[] = ["left", "right"];
const JOINTS: readonly Joint[] = ["hip_flexion", "knee_flexion", "ankle_dorsiflexion"];
const SIDE_INDICES = {
  left: { shoulder: 11, hip: 23, knee: 25, ankle: 27, heel: 29, toe: 31 },
  right: { shoulder: 12, hip: 24, knee: 26, ankle: 28, heel: 30, toe: 32 }
} as const;
const JOINT_LANDMARKS: Record<Joint, Record<Side, readonly number[]>> = {
  hip_flexion: { left: [11, 23, 25], right: [12, 24, 26] },
  knee_flexion: { left: [23, 25, 27], right: [24, 26, 28] },
  ankle_dorsiflexion: { left: [25, 27, 29, 31], right: [26, 28, 30, 32] }
};

export function analyzeGait(frames: readonly PoseFrame[]): GaitAnalysisResult {
  const processing = processLandmarks(frames);
  const viewpoint = assessViewpoint(processing.frames, processing.fps);
  const warnings = [...viewpoint.warnings];
  if (!viewpoint.analysisSupported) {
    return {
      analysisVersion: "motionlab-gait-web/0.2.0", fps: processing.fps,
      direction: "unknown", directionConfidence: 0, viewpoint,
      processing: processing.report, events: [], cycles: [], angles: [], rawAngles: [],
      jointQuality: JOINTS.map((joint) => emptyQuality(joint)), warnings
    };
  }
  const filteredFrames = selectAnalysisFrames(processing.frames, viewpoint);
  const rawFrames = selectAnalysisFrames(frames, viewpoint);
  const detected = detectEvents(filteredFrames, processing.fps);
  warnings.push(...detected.warnings);
  const filteredAngles = calculateJointAngles(filteredFrames, detected.cycles, detected.direction);
  const rawAngles = calculateJointAngles(rawFrames, detected.cycles, detected.direction);
  const assessments = JOINTS.map((joint) => assessJoint(
    joint, rawFrames, filteredFrames, filteredAngles, detected.cycles, detected.direction
  ));
  const validCycles = new Map(assessments.map((item) => [item.report.joint, item.validCycleKeys]));
  return {
    analysisVersion: "motionlab-gait-web/0.2.0",
    fps: processing.fps,
    direction: detected.direction,
    directionConfidence: detected.directionConfidence,
    viewpoint,
    processing: processing.report,
    events: detected.events,
    cycles: detected.cycles,
    angles: excludeInvalidCyclePoints(filteredAngles, detected.cycles, validCycles),
    rawAngles: excludeInvalidCyclePoints(rawAngles, detected.cycles, validCycles),
    jointQuality: assessments.map((item) => item.report),
    warnings
  };
}

function emptyQuality(joint: Joint): JointQualityReport {
  return {
    joint, status: "difficult", meanVisibility: 0, meanPresence: 0,
    outlierRate: 0, interpolationRate: 0, trackingContinuity: 0,
    usablePointRate: 0, angleJumpRate: 1, segmentConsistency: 0,
    validCycleCount: 0, excludedCycleCount: 0,
    warnings: ["歩行イベントを確認してください。"]
  };
}

function byIndex(frame: { landmarks: readonly PoseLandmark[] }): Map<number, PoseLandmark> {
  return new Map(frame.landmarks.map((landmark) => [landmark.index, landmark]));
}

function frameSagittalScore(frame: ProcessedPoseFrame): number {
  const points = byIndex(frame);
  const leftShoulder = points.get(11); const rightShoulder = points.get(12);
  const leftHip = points.get(23); const rightHip = points.get(24);
  if (!leftShoulder || !rightShoulder || !leftHip || !rightHip) return 0;
  const shoulderMid = [(leftShoulder.x + rightShoulder.x) / 2, (leftShoulder.y + rightShoulder.y) / 2] as const;
  const hipMid = [(leftHip.x + rightHip.x) / 2, (leftHip.y + rightHip.y) / 2] as const;
  const torso = Math.hypot(shoulderMid[0] - hipMid[0], shoulderMid[1] - hipMid[1]);
  if (torso <= 1e-5) return 0;
  const shoulderWidth = Math.hypot(leftShoulder.x - rightShoulder.x, leftShoulder.y - rightShoulder.y) / torso;
  const hipWidth = Math.hypot(leftHip.x - rightHip.x, leftHip.y - rightHip.y) / torso;
  const shoulderDepth = Math.abs(leftShoulder.z - rightShoulder.z) / torso;
  return 0.35 * clamp((1.05 - shoulderWidth) / 0.65)
    + 0.35 * clamp((0.70 - hipWidth) / 0.45)
    + 0.30 * clamp((shoulderDepth - 0.50) / 1.50);
}

export function assessViewpoint(frames: readonly ProcessedPoseFrame[], fps: number): ViewpointReport {
  if (frames.length < 10) {
    return {
      classification: "insufficient", sagittalFraction: 0, stableSagittalScore: 0,
      analysisStartMs: null, analysisEndMs: null, analysisFrameCount: 0,
      analysisSupported: false, warnings: ["撮影面を判定できるフレームが不足しています。"]
    };
  }
  const rawScores = frames.map(frameSagittalScore);
  const halfWindow = Math.max(1, Math.round(Math.max(fps, 1) * 0.25));
  const smoothed = rawScores.map((_, index) => median(rawScores.slice(
    Math.max(0, index - halfWindow), Math.min(rawScores.length, index + halfWindow + 1)
  )));
  const qualified = smoothed.map((score) => score >= 0.60);
  const maxGap = Math.max(1, Math.round(Math.max(fps, 1) * 0.30));
  const truePositions = qualified.map((value, index) => value ? index : -1).filter((index) => index >= 0);
  for (let index = 0; index < truePositions.length - 1; index += 1) {
    const before = truePositions[index]!; const after = truePositions[index + 1]!;
    if (after - before > 1 && after - before <= maxGap + 1) {
      for (let position = before; position <= after; position += 1) qualified[position] = true;
    }
  }
  let bestStart: number | null = null; let bestEnd: number | null = null; let runStart: number | null = null;
  [...qualified, false].forEach((isSagittal, index) => {
    if (isSagittal && runStart === null) runStart = index;
    else if (!isSagittal && runStart !== null) {
      const runEnd = index - 1;
      if (bestStart === null || runEnd - runStart > bestEnd! - bestStart) {
        bestStart = runStart; bestEnd = runEnd;
      }
      runStart = null;
    }
  });
  const sagittalFraction = mean(qualified.map(Number));
  const minimumFrames = Math.max(30, Math.round(Math.max(fps, 1) * 3));
  if (bestStart === null || bestEnd === null || bestEnd - bestStart + 1 < minimumFrames) {
    return {
      classification: "frontal_or_oblique", sagittalFraction: round(sagittalFraction),
      stableSagittalScore: 0, analysisStartMs: null, analysisEndMs: null,
      analysisFrameCount: 0, analysisSupported: false,
      warnings: ["3秒以上連続する安定した矢状面区間がないため、関節角度を算出しません。"]
    };
  }
  const stableScore = median(smoothed.slice(bestStart, bestEnd + 1));
  const classification = sagittalFraction >= 0.80 ? "sagittal" : "mixed";
  const warnings: string[] = [];
  if (classification === "mixed") warnings.push("前額面・斜め・旋回区間が混在しています。最長の安定した矢状面区間だけを定量解析しました。");
  if (stableScore < 0.72) warnings.push("採用した区間も完全な真横ではない可能性があり、角度は低信頼です。");
  return {
    classification, sagittalFraction: round(sagittalFraction), stableSagittalScore: round(stableScore),
    analysisStartMs: frames[bestStart]!.timestampMs, analysisEndMs: frames[bestEnd]!.timestampMs,
    analysisFrameCount: bestEnd - bestStart + 1, analysisSupported: true, warnings
  };
}

function selectAnalysisFrames<T extends { timestampMs: number }>(frames: readonly T[], report: ViewpointReport): T[] {
  if (!report.analysisSupported || report.analysisStartMs === null || report.analysisEndMs === null) return [];
  return frames.filter((frame) => frame.timestampMs >= report.analysisStartMs! && frame.timestampMs <= report.analysisEndMs!);
}

interface EventDetectionResult {
  direction: "left" | "right" | "unknown";
  directionConfidence: number;
  events: GaitEvent[];
  cycles: GaitCycle[];
  warnings: string[];
}

export function detectEvents(frames: readonly ProcessedPoseFrame[], fps: number): EventDetectionResult {
  const { direction, confidence: directionConfidence } = detectDirection(frames);
  const directionSign = direction === "left" ? -1 : 1;
  const events: GaitEvent[] = []; const warnings: string[] = [];
  if (direction === "unknown") warnings.push("進行方向を十分な確信で判定できませんでした。右方向として仮解析しています。");
  const minimumDistance = Math.max(2, Math.round(Math.max(fps, 1) * 0.40));
  for (const side of SIDES) {
    const indices = SIDE_INDICES[side];
    const heel = relativeSignal(frames, indices.heel, indices.hip, directionSign);
    const toe = relativeSignal(frames, indices.toe, indices.hip, directionSign);
    const heelSignal = fillForPeaks(heel.values); const toeSignal = fillForPeaks(toe.values);
    if (!heelSignal || !toeSignal) { warnings.push(`${side === "left" ? "左" : "右"}下肢の接地・離地候補を検出できませんでした。`); continue; }
    const heelThreshold = Math.max(0.008, standardDeviation(heelSignal) * 0.20);
    const toeThreshold = Math.max(0.008, standardDeviation(toeSignal) * 0.20);
    for (const peak of findPeaks(heelSignal, minimumDistance, heelThreshold)) {
      events.push({ eventType: "IC", side, timestampMs: frames[peak.position]!.timestampMs,
        frameIndex: frames[peak.position]!.frameIndex,
        confidence: eventConfidence(peak.prominence, heelThreshold, heel.confidence[peak.position]!, directionConfidence) });
    }
    for (const peak of findPeaks(toeSignal.map((value) => -value), minimumDistance, toeThreshold)) {
      events.push({ eventType: "TO", side, timestampMs: frames[peak.position]!.timestampMs,
        frameIndex: frames[peak.position]!.frameIndex,
        confidence: eventConfidence(peak.prominence, toeThreshold, toe.confidence[peak.position]!, directionConfidence) });
    }
  }
  events.sort((a, b) => a.timestampMs - b.timestampMs || a.side.localeCompare(b.side) || a.eventType.localeCompare(b.eventType));
  const cycles = buildCycles(events);
  if (cycles.length < 2) warnings.push("解析可能な歩行周期が少ないため、平均値の信頼性が低いです。");
  return { direction, directionConfidence, events, cycles, warnings };
}

function detectDirection(frames: readonly ProcessedPoseFrame[]): { direction: "left" | "right" | "unknown"; confidence: number } {
  const samples = frames.map((frame) => {
    const points = byIndex(frame); const left = points.get(23); const right = points.get(24);
    return left && right ? (left.x + right.x) / 2 : left?.x ?? right?.x ?? Number.NaN;
  }).filter(Number.isFinite);
  if (samples.length < 10) return { direction: "unknown", confidence: 0 };
  const section = Math.max(3, Math.floor(samples.length / 5));
  const displacement = median(samples.slice(-section)) - median(samples.slice(0, section));
  const confidence = Math.min(1, Math.abs(displacement) / 0.20);
  return Math.abs(displacement) < 0.03
    ? { direction: "unknown", confidence }
    : { direction: displacement > 0 ? "right" : "left", confidence };
}

function relativeSignal(frames: readonly ProcessedPoseFrame[], distalIndex: number, hipIndex: number, directionSign: number): { values: number[]; confidence: number[] } {
  const values: number[] = []; const confidence: number[] = [];
  for (const frame of frames) {
    const points = byIndex(frame); const distal = points.get(distalIndex); const hip = points.get(hipIndex);
    values.push(distal && hip ? directionSign * (distal.x - hip.x) : Number.NaN);
    confidence.push(distal && hip ? Math.min(
      distal.visibility, effectivePresence(distal.visibility, distal.presence),
      hip.visibility, effectivePresence(hip.visibility, hip.presence)
    ) : 0);
  }
  return { values, confidence };
}

function fillForPeaks(values: readonly number[]): number[] | null {
  const valid = values.map((value, index) => Number.isFinite(value) ? index : -1).filter((index) => index >= 0);
  if (valid.length < 10) return null;
  return values.map((value, index) => {
    if (Number.isFinite(value)) return value;
    const rightPosition = valid.findIndex((position) => position > index);
    if (rightPosition < 0) return values[valid.at(-1)!]!;
    if (rightPosition === 0) return values[valid[0]!]!;
    const left = valid[rightPosition - 1]!; const right = valid[rightPosition]!;
    return values[left]! + ((index - left) / (right - left)) * (values[right]! - values[left]!);
  });
}

function peakProminence(values: readonly number[], position: number): number {
  const height = values[position]!;
  let leftMinimum = height;
  for (let index = position - 1; index >= 0; index -= 1) {
    leftMinimum = Math.min(leftMinimum, values[index]!);
    if (values[index]! > height) break;
  }
  let rightMinimum = height;
  for (let index = position + 1; index < values.length; index += 1) {
    rightMinimum = Math.min(rightMinimum, values[index]!);
    if (values[index]! > height) break;
  }
  return height - Math.max(leftMinimum, rightMinimum);
}

function findPeaks(values: readonly number[], minimumDistance: number, prominenceThreshold: number): { position: number; prominence: number }[] {
  const candidates: { position: number; prominence: number; height: number }[] = [];
  for (let index = 1; index < values.length - 1; index += 1) {
    if (values[index]! > values[index - 1]! && values[index]! >= values[index + 1]!) {
      const prominence = peakProminence(values, index);
      if (prominence >= prominenceThreshold) candidates.push({ position: index, prominence, height: values[index]! });
    }
  }
  const accepted: typeof candidates = [];
  for (const candidate of [...candidates].sort((a, b) => b.height - a.height)) {
    if (accepted.every((item) => Math.abs(item.position - candidate.position) >= minimumDistance)) accepted.push(candidate);
  }
  return accepted.sort((a, b) => a.position - b.position).map(({ position, prominence }) => ({ position, prominence }));
}

function eventConfidence(prominence: number, threshold: number, landmarkConfidence: number, directionConfidence: number): number {
  const signalScore = Math.min(1, prominence / Math.max(threshold * 3, 1e-6));
  return round(clamp(0.55 * signalScore + 0.35 * landmarkConfidence + 0.10 * directionConfidence));
}

function buildCycles(events: readonly GaitEvent[]): GaitCycle[] {
  const cycles: GaitCycle[] = [];
  for (const side of SIDES) {
    const contacts = events.filter((event) => event.side === side && event.eventType === "IC");
    const toeOffs = events.filter((event) => event.side === side && event.eventType === "TO");
    for (let index = 0; index < contacts.length - 1; index += 1) {
      const start = contacts[index]!; const end = contacts[index + 1]!; const duration = end.timestampMs - start.timestampMs;
      if (duration < 700 || duration > 2500) continue;
      const candidates = toeOffs.filter((event) => event.timestampMs > start.timestampMs + 0.25 * duration
        && event.timestampMs < start.timestampMs + 0.85 * duration);
      const toeOff = candidates.sort((a, b) => b.confidence - a.confidence)[0];
      let confidence = Math.min(start.confidence, end.confidence);
      confidence = toeOff ? Math.min(confidence, toeOff.confidence) : confidence * 0.6;
      cycles.push({ side, startMs: start.timestampMs, endMs: end.timestampMs,
        toeOffMs: toeOff?.timestampMs ?? null, confidence: round(confidence) });
    }
  }
  const filtered: GaitCycle[] = [];
  for (const side of SIDES) {
    const sideCycles = cycles.filter((cycle) => cycle.side === side);
    if (sideCycles.length < 3) { filtered.push(...sideCycles); continue; }
    const typical = median(sideCycles.map((cycle) => cycle.endMs - cycle.startMs));
    filtered.push(...sideCycles.filter((cycle) => cycle.endMs - cycle.startMs >= 0.65 * typical
      && cycle.endMs - cycle.startMs <= 1.5 * typical));
  }
  return filtered.sort((a, b) => a.startMs - b.startMs);
}

export function calculateJointAngles(frames: readonly { timestampMs: number; landmarks: readonly PoseLandmark[] }[], cycles: readonly GaitCycle[], direction: string): AnglePoint[] {
  const directionSign = direction === "left" ? -1 : 1;
  const points: AnglePoint[] = [];
  for (const frame of frames) {
    const landmarks = byIndex(frame);
    for (const side of SIDES) {
      const index = SIDE_INDICES[side];
      const shoulder = landmarks.get(index.shoulder); const hip = landmarks.get(index.hip);
      const knee = landmarks.get(index.knee); const ankle = landmarks.get(index.ankle);
      const heel = landmarks.get(index.heel); const toe = landmarks.get(index.toe);
      if (!shoulder || !hip || !knee || !ankle || !heel || !toe) continue;
      const mapped = [shoulder, hip, knee, ankle, heel, toe].map((item) => [directionSign * item.x, -item.y] as const);
      const [shoulderP, hipP, kneeP, ankleP, heelP, toeP] = mapped as [readonly [number, number], readonly [number, number], readonly [number, number], readonly [number, number], readonly [number, number], readonly [number, number]];
      const angles: { joint: Joint; angle: number; confidence: number }[] = [
        { joint: "hip_flexion", angle: signedAngle(vector(shoulderP, hipP), vector(hipP, kneeP)),
          confidence: landmarkConfidence([shoulder, hip, knee]) },
        { joint: "knee_flexion", angle: 180 - unsignedAngle(vector(kneeP, hipP), vector(kneeP, ankleP)),
          confidence: landmarkConfidence([hip, knee, ankle]) },
        { joint: "ankle_dorsiflexion", angle: 90 - unsignedAngle(vector(ankleP, kneeP), vector(heelP, toeP)),
          confidence: 0.75 * landmarkConfidence([knee, ankle, heel, toe]) }
      ];
      const cyclePercent = findCyclePercent(frame.timestampMs, side, cycles);
      for (const value of angles) {
        const bounds: Record<Joint, readonly [number, number]> = {
          hip_flexion: [-45, 75], knee_flexion: [-5, 130], ankle_dorsiflexion: [-50, 40]
        };
        if (Number.isFinite(value.angle) && value.confidence >= 0.5
          && value.angle >= bounds[value.joint][0] && value.angle <= bounds[value.joint][1]) {
          points.push({ timestampMs: frame.timestampMs, cyclePercent, side, joint: value.joint,
            angleDegrees: round(value.angle), confidence: round(value.confidence) });
        }
      }
    }
  }
  return points;
}

function landmarkConfidence(landmarks: readonly PoseLandmark[]): number {
  return Math.min(...landmarks.map((item) => Math.min(item.visibility, effectivePresence(item.visibility, item.presence))));
}
function vector(start: readonly [number, number], end: readonly [number, number]): [number, number] { return [end[0] - start[0], end[1] - start[1]]; }
function unsignedAngle(first: readonly [number, number], second: readonly [number, number]): number {
  const denominator = Math.hypot(...first) * Math.hypot(...second);
  if (denominator <= 1e-9) return Number.NaN;
  return Math.acos(clamp((first[0] * second[0] + first[1] * second[1]) / denominator, -1, 1)) * 180 / Math.PI;
}
function signedAngle(first: readonly [number, number], second: readonly [number, number]): number {
  return Math.atan2(first[0] * second[1] - first[1] * second[0], first[0] * second[0] + first[1] * second[1]) * 180 / Math.PI;
}
function findCyclePercent(timestampMs: number, side: Side, cycles: readonly GaitCycle[]): number | null {
  const cycle = cycles.find((item) => item.side === side && timestampMs >= item.startMs && timestampMs <= item.endMs);
  return cycle ? 100 * (timestampMs - cycle.startMs) / (cycle.endMs - cycle.startMs) : null;
}

interface Assessment { report: JointQualityReport; validCycleKeys: Set<string> }
function assessJoint(
  joint: Joint, rawFrames: readonly PoseFrame[], filteredFrames: readonly ProcessedPoseFrame[],
  angles: readonly AnglePoint[], cycles: readonly GaitCycle[], direction: string
): Assessment {
  const expectedLandmarks = Math.max(1, rawFrames.length * SIDES.reduce((sum, side) => sum + JOINT_LANDMARKS[joint][side].length, 0));
  const expectedJointFrames = Math.max(1, filteredFrames.length * 2);
  const visibility: number[] = []; const presence: number[] = [];
  let outliers = 0; let interpolated = 0; let completeJointFrames = 0;
  rawFrames.forEach((rawFrame, frameIndex) => {
    const raw = byIndex(rawFrame); const filtered = byIndex(filteredFrames[frameIndex]!);
    for (const side of SIDES) {
      const indices = JOINT_LANDMARKS[joint][side];
      const rawRequired = indices.map((index) => raw.get(index));
      const filteredRequired = indices.map((index) => filtered.get(index));
      visibility.push(...rawRequired.map((item) => item?.visibility ?? 0));
      presence.push(...rawRequired.map((item) => item ? effectivePresence(item.visibility, item.presence) : 0));
      outliers += filteredRequired.filter((item) => item && "outlierReplaced" in item && item.outlierReplaced).length;
      interpolated += filteredRequired.filter((item) => item && "interpolated" in item && item.interpolated).length;
      completeJointFrames += Number(filteredRequired.every(Boolean));
    }
  });
  const jointAngles = angles.filter((point) => point.joint === joint && point.cyclePercent !== null);
  const validCycleKeys = new Set<string>(); let expectedCycleSamples = 0;
  for (const cycle of cycles) {
    const positions = filteredFrames.map((frame, index) => ({ frame, index }))
      .filter(({ frame }) => frame.timestampMs >= cycle.startMs && frame.timestampMs <= cycle.endMs);
    const expected = positions.length;
    const available = jointAngles.filter((point) => point.side === cycle.side && point.timestampMs >= cycle.startMs && point.timestampMs <= cycle.endMs).length;
    expectedCycleSamples += expected;
    const indices = JOINT_LANDMARKS[joint][cycle.side];
    const rawSamples = positions.flatMap(({ index }) => rawFrames[index]!.landmarks.filter((item) => indices.includes(item.index)));
    const processedSamples = positions.flatMap(({ frame }) => frame.landmarks.filter((item) => indices.includes(item.index)));
    const expectedSamples = Math.max(1, expected * indices.length);
    const cycleConfidence = rawSamples.length ? mean(rawSamples.map((item) => Math.min(item.visibility, effectivePresence(item.visibility, item.presence)))) : 0;
    const cycleInterpolation = processedSamples.filter((item) => item.interpolated).length / expectedSamples;
    const cycleOutliers = processedSamples.filter((item) => item.outlierReplaced).length / expectedSamples;
    const minimumCoverage = joint === "ankle_dorsiflexion" ? 0.65 : 0.60;
    const maximumInterpolation = joint === "ankle_dorsiflexion" ? 0.15 : 0.20;
    const maximumOutliers = joint === "ankle_dorsiflexion" ? 0.10 : 0.15;
    if (expected >= 5 && available / expected >= minimumCoverage && cycleConfidence >= 0.50
      && cycleInterpolation <= maximumInterpolation && cycleOutliers <= maximumOutliers) validCycleKeys.add(cycleKey(cycle));
  }
  const meanVisibility = mean(visibility); const meanPresence = mean(presence);
  const outlierRate = outliers / expectedLandmarks; const interpolationRate = interpolated / expectedLandmarks;
  const continuity = completeJointFrames / expectedJointFrames;
  const usableRate = Math.min(1, jointAngles.length / Math.max(1, expectedCycleSamples));
  const excludedCycles = Math.max(0, cycles.length - validCycleKeys.size);
  const jumpThreshold: Record<Joint, number> = { hip_flexion: 12, knee_flexion: 15, ankle_dorsiflexion: 10 };
  const changes: number[] = [];
  for (const side of SIDES) {
    const ordered = jointAngles.filter((point) => point.side === side).sort((a, b) => a.timestampMs - b.timestampMs);
    for (let index = 0; index < ordered.length - 1; index += 1) {
      const before = ordered[index]!; const after = ordered[index + 1]!;
      if (after.timestampMs > before.timestampMs && after.timestampMs - before.timestampMs <= 100) changes.push(Math.abs(after.angleDegrees - before.angleDegrees));
    }
  }
  const angleJumpRate = changes.length ? changes.filter((change) => change > jumpThreshold[joint]).length / changes.length : 1;
  let segmentConsistency = 1;
  if (joint === "ankle_dorsiflexion") {
    const sign = direction === "left" ? -1 : 1; const directions: boolean[] = [];
    for (const frame of filteredFrames) {
      const points = byIndex(frame);
      for (const side of SIDES) {
        const indices = JOINT_LANDMARKS[joint][side]; const heel = points.get(indices[2]!); const toe = points.get(indices[3]!);
        if (heel && toe) directions.push(sign * (toe.x - heel.x) > 0.005);
      }
    }
    segmentConsistency = directions.length ? directions.filter(Boolean).length / directions.length : 0;
  }
  let difficult = validCycleKeys.size === 0 || continuity < 0.50 || usableRate < 0.35 || meanVisibility < 0.50 || meanPresence < 0.50;
  let high: boolean;
  if (joint === "ankle_dorsiflexion") {
    difficult ||= continuity < 0.65 || usableRate < 0.50 || segmentConsistency < 0.40;
    high = meanVisibility >= 0.80 && meanPresence >= 0.80 && continuity >= 0.85 && usableRate >= 0.75
      && outlierRate <= 0.05 && interpolationRate <= 0.08 && angleJumpRate <= 0.05 && segmentConsistency >= 0.80 && validCycleKeys.size >= 2;
  } else {
    high = meanVisibility >= 0.75 && meanPresence >= 0.75 && continuity >= 0.80 && usableRate >= 0.70
      && outlierRate <= 0.08 && interpolationRate <= 0.12 && angleJumpRate <= 0.08 && validCycleKeys.size >= 2;
  }
  const status = difficult ? "difficult" : high ? "high" : "caution";
  const warnings: string[] = [];
  if (joint === "ankle_dorsiflexion" && status === "caution") warnings.push("足部ランドマークの追跡品質に注意が必要なため参考値です。");
  if (joint === "ankle_dorsiflexion" && status === "difficult") warnings.push("足部の追跡が不安定なため解析困難です。");
  if (angleJumpRate > (joint === "ankle_dorsiflexion" ? 0.05 : 0.08)) warnings.push("短時間の角度変化が複数あり、追跡の安定性に注意が必要です。");
  if (joint === "ankle_dorsiflexion" && segmentConsistency < 0.80) warnings.push("踵から足趾への足部segment方向が一部フレームで不安定です。");
  if (excludedCycles) warnings.push(`品質条件を満たさない${excludedCycles}周期を集計から除外しました。`);
  return { report: {
    joint, status, meanVisibility: round(meanVisibility, 4), meanPresence: round(meanPresence, 4),
    outlierRate: round(outlierRate, 4), interpolationRate: round(interpolationRate, 4),
    trackingContinuity: round(continuity, 4), usablePointRate: round(usableRate, 4),
    angleJumpRate: round(angleJumpRate, 4), segmentConsistency: round(segmentConsistency, 4),
    validCycleCount: validCycleKeys.size, excludedCycleCount: excludedCycles, warnings
  }, validCycleKeys };
}

function cycleKey(cycle: GaitCycle): string { return `${cycle.side}:${cycle.startMs}:${cycle.endMs}`; }
function excludeInvalidCyclePoints(points: readonly AnglePoint[], cycles: readonly GaitCycle[], valid: Map<Joint, Set<string>>): AnglePoint[] {
  return points.filter((point) => {
    if (point.cyclePercent === null) return true;
    const cycle = cycles.find((item) => item.side === point.side && point.timestampMs >= item.startMs && point.timestampMs <= item.endMs);
    return cycle ? valid.get(point.joint)?.has(cycleKey(cycle)) : false;
  });
}
