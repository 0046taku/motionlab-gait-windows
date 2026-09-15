import { POSE_LANDMARK_NAMES, type PoseFrame } from "../domain/models";
import { inferSamplingFrequency, interpolateAt, median } from "./statistics";
import type { ProcessedPoseFrame, ProcessingReport } from "./types";

const LANDMARK_COUNT = 33;
const DIMENSION_COUNT = 6;

export interface LandmarkProcessingResult {
  frames: ProcessedPoseFrame[];
  report: ProcessingReport;
  fps: number;
}

export function effectivePresence(visibility: number, presence: number | null): number {
  // Tasks Vision Web 1.0.1 does not expose presence. Visibility is the closest
  // official signal and is used only as a documented fallback in that case.
  return presence ?? visibility;
}

export function processLandmarks(
  frames: readonly PoseFrame[],
  confidenceThreshold = 0.5,
  maxInterpolationGapMs = 100,
  cutoffHz = 6
): LandmarkProcessingResult {
  const fps = inferSamplingFrequency(frames.map((frame) => frame.timestampMs));
  const timestamps = frames.map((frame) => frame.timestampMs);
  const coords = Array.from({ length: frames.length }, () =>
    Array.from({ length: LANDMARK_COUNT }, () => Array<number>(DIMENSION_COUNT).fill(Number.NaN))
  );
  const visibility = Array.from({ length: frames.length }, () => Array<number>(LANDMARK_COUNT).fill(0));
  const presence = Array.from({ length: frames.length }, () => Array<number>(LANDMARK_COUNT).fill(0));
  const originallyValid = Array.from({ length: frames.length }, () => Array<boolean>(LANDMARK_COUNT).fill(false));
  const outlierMask = Array.from({ length: frames.length }, () => Array<boolean>(LANDMARK_COUNT).fill(false));
  const interpolatedMask = Array.from({ length: frames.length }, () => Array<boolean>(LANDMARK_COUNT).fill(false));
  let presenceFallback = false;

  frames.forEach((frame, framePosition) => {
    for (const landmark of frame.landmarks) {
      if (landmark.index < 0 || landmark.index >= LANDMARK_COUNT) continue;
      const index = landmark.index;
      const landmarkPresence = effectivePresence(landmark.visibility, landmark.presence);
      presenceFallback ||= landmark.presence === null;
      visibility[framePosition]![index] = landmark.visibility;
      presence[framePosition]![index] = landmarkPresence;
      if (Math.min(landmark.visibility, landmarkPresence) < confidenceThreshold) continue;
      originallyValid[framePosition]![index] = true;
      coords[framePosition]![index] = [
        landmark.x, landmark.y, landmark.z,
        landmark.worldX ?? Number.NaN, landmark.worldY ?? Number.NaN, landmark.worldZ ?? Number.NaN
      ];
    }
  });

  for (let landmarkIndex = 0; landmarkIndex < LANDMARK_COUNT; landmarkIndex += 1) {
    const rejected = Array<boolean>(frames.length).fill(false);
    for (let dimension = 0; dimension < 3; dimension += 1) {
      const series = coords.map((frame) => frame[landmarkIndex]![dimension]!);
      rejectVelocitySpikes(series, timestamps, 0.015).forEach((value, index) => {
        rejected[index] ||= value;
      });
    }
    rejected.forEach((value, framePosition) => {
      if (!value) return;
      outlierMask[framePosition]![landmarkIndex] = true;
      coords[framePosition]![landmarkIndex]!.fill(Number.NaN);
    });
    for (let dimension = 0; dimension < DIMENSION_COUNT; dimension += 1) {
      const series = coords.map((frame) => frame[landmarkIndex]![dimension]!);
      const filled = interpolateShortGaps(series, timestamps, maxInterpolationGapMs);
      filled.forEach((value, framePosition) => {
        interpolatedMask[framePosition]![landmarkIndex] ||= value;
      });
      const smoothed = smoothFiniteSegments(series, fps, cutoffHz);
      smoothed.forEach((value, framePosition) => {
        coords[framePosition]![landmarkIndex]![dimension] = value;
      });
    }
  }

  const processedFrames = frames.map<ProcessedPoseFrame>((source, framePosition) => ({
    frameIndex: source.frameIndex,
    timestampMs: source.timestampMs,
    landmarks: Array.from({ length: LANDMARK_COUNT }, (_, index) => index)
      .filter((index) => coords[framePosition]![index]!.slice(0, 3).every(Number.isFinite))
      .map((index) => ({
        index,
        name: POSE_LANDMARK_NAMES[index]!,
        x: coords[framePosition]![index]![0]!,
        y: coords[framePosition]![index]![1]!,
        z: coords[framePosition]![index]![2]!,
        visibility: visibility[framePosition]![index]!,
        presence: presence[framePosition]![index]!,
        worldX: finiteOrNull(coords[framePosition]![index]![3]!),
        worldY: finiteOrNull(coords[framePosition]![index]![4]!),
        worldZ: finiteOrNull(coords[framePosition]![index]![5]!),
        interpolated: interpolatedMask[framePosition]![index]!
          || (!originallyValid[framePosition]![index]! && coords[framePosition]![index]!.slice(0, 3).every(Number.isFinite)),
        outlierReplaced: outlierMask[framePosition]![index]!
      }))
  }));

  return {
    frames: processedFrames,
    fps,
    report: {
      frameCount: frames.length,
      interpolatedValues: interpolatedMask.flat().filter(Boolean).length,
      replacedOutliers: outlierMask.flat().filter(Boolean).length,
      confidenceThreshold,
      maxInterpolationGapMs,
      filterType: "butterworth_lowpass",
      filterOrder: 4,
      cutoffHz,
      zeroPhase: true,
      presenceFallback
    }
  };
}

function finiteOrNull(value: number): number | null {
  return Number.isFinite(value) ? value : null;
}

function rejectVelocitySpikes(values: readonly number[], timestamps: readonly number[], positionFloor: number): boolean[] {
  const rejected = Array<boolean>(values.length).fill(false);
  if (values.length < 5) return rejected;
  const dt = values.slice(1).map((_, index) => (timestamps[index + 1]! - timestamps[index]!) / 1000);
  const velocity = dt.map((seconds, index) => {
    const before = values[index]!;
    const after = values[index + 1]!;
    return Number.isFinite(before) && Number.isFinite(after) && seconds > 0 && seconds <= 0.1
      ? (after - before) / seconds : Number.NaN;
  });
  const finiteVelocity = velocity.filter(Number.isFinite);
  if (finiteVelocity.length < 4) return rejected;
  const medianVelocity = median(finiteVelocity);
  const robustScale = 1.4826 * median(finiteVelocity.map((value) => Math.abs(value - medianVelocity)));
  const positiveDt = dt.filter((value) => value > 0);
  const velocityFloor = positionFloor / Math.max(median(positiveDt), 0.001);
  const threshold = Math.max(velocityFloor, 6 * robustScale);
  for (const gap of [1, 2]) {
    for (let left = 0; left < values.length - gap - 1; left += 1) {
      const right = left + gap + 1;
      if (!Number.isFinite(values[left]) || !Number.isFinite(values[right])) continue;
      const firstEdge = velocity[left]!;
      const lastEdge = velocity[right - 1]!;
      if (!Number.isFinite(firstEdge) || !Number.isFinite(lastEdge)
        || Math.abs(firstEdge) <= threshold || Math.abs(lastEdge) <= threshold
        || firstEdge * lastEdge >= 0) continue;
      let maximumDeviation = 0;
      let complete = true;
      for (let position = left + 1; position < right; position += 1) {
        if (!Number.isFinite(values[position])) { complete = false; break; }
        const expected = interpolateAt(timestamps[position]!, timestamps[left]!, timestamps[right]!, values[left]!, values[right]!);
        maximumDeviation = Math.max(maximumDeviation, Math.abs(values[position]! - expected));
      }
      if (complete && maximumDeviation > positionFloor) {
        for (let position = left + 1; position < right; position += 1) rejected[position] = true;
      }
    }
  }
  return rejected;
}

function interpolateShortGaps(values: number[], timestamps: readonly number[], maximumGapMs: number): boolean[] {
  const filled = Array<boolean>(values.length).fill(false);
  const valid = values.map((value, index) => Number.isFinite(value) ? index : -1).filter((index) => index >= 0);
  for (let index = 0; index < valid.length - 1; index += 1) {
    const left = valid[index]!;
    const right = valid[index + 1]!;
    if (right === left + 1 || timestamps[right]! - timestamps[left]! > maximumGapMs) continue;
    for (let position = left + 1; position < right; position += 1) {
      values[position] = interpolateAt(timestamps[position]!, timestamps[left]!, timestamps[right]!, values[left]!, values[right]!);
      filled[position] = true;
    }
  }
  return filled;
}

interface Biquad { b0: number; b1: number; b2: number; a1: number; a2: number }

function butterworthSections(fps: number, cutoffHz: number): Biquad[] {
  const cutoff = Math.min(cutoffHz, 0.45 * fps);
  if (fps <= 0 || cutoff <= 0) return [];
  const k = Math.tan(Math.PI * cutoff / fps);
  return [0.541196100146197, 1.306562964876377].map((q) => {
    const norm = 1 / (1 + k / q + k * k);
    return {
      b0: k * k * norm,
      b1: 2 * k * k * norm,
      b2: k * k * norm,
      a1: 2 * (k * k - 1) * norm,
      a2: (1 - k / q + k * k) * norm
    };
  });
}

function filterCascade(values: readonly number[], sections: readonly Biquad[]): number[] {
  let output = [...values];
  for (const section of sections) {
    const filtered = Array<number>(output.length);
    const initial = output[0] ?? 0;
    let z1 = (1 - section.b0) * initial;
    let z2 = (section.b2 - section.a2) * initial;
    output.forEach((sample, index) => {
      const result = section.b0 * sample + z1;
      z1 = section.b1 * sample - section.a1 * result + z2;
      z2 = section.b2 * sample - section.a2 * result;
      filtered[index] = result;
    });
    output = filtered;
  }
  return output;
}

function zeroPhaseFilter(values: readonly number[], sections: readonly Biquad[]): number[] {
  const padding = Math.min(values.length - 1, 15);
  const first = values[0]!;
  const last = values.at(-1)!;
  const before = values.slice(1, padding + 1).reverse().map((value) => 2 * first - value);
  const after = values.slice(values.length - padding - 1, values.length - 1).reverse().map((value) => 2 * last - value);
  const extended = [...before, ...values, ...after];
  const forward = filterCascade(extended, sections);
  const backward = filterCascade(forward.reverse(), sections).reverse();
  return backward.slice(padding, padding + values.length);
}

function smoothFiniteSegments(values: readonly number[], fps: number, cutoffHz: number): number[] {
  const output = [...values];
  const sections = butterworthSections(fps, cutoffHz);
  if (!sections.length) return output;
  let start = 0;
  while (start < values.length) {
    while (start < values.length && !Number.isFinite(values[start])) start += 1;
    let end = start;
    while (end < values.length && Number.isFinite(values[end])) end += 1;
    if (end - start >= 15) {
      zeroPhaseFilter(values.slice(start, end), sections).forEach((value, offset) => {
        output[start + offset] = value;
      });
    }
    start = end + 1;
  }
  return output;
}

