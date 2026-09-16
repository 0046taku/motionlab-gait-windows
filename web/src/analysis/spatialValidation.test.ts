import { describe, expect, it } from "vitest";
import { POSE_LANDMARK_NAMES, type PoseFrame, type PoseLandmark } from "../domain/models";
import { cyclesSelectedByValidation, validateSpatialBiomechanics } from "./spatialValidation";
import type { AnglePoint, GaitCycle } from "./types";

function frame(frameIndex: number, centerX: number): PoseFrame {
  const positions = new Map<number, [number, number, number]>([
    [11, [centerX, 0.25, -0.20]], [12, [centerX + 0.01, 0.25, 0.20]],
    [23, [centerX, 0.50, -0.20]], [24, [centerX + 0.01, 0.50, 0.20]],
    [25, [centerX, 0.68, -0.20]], [26, [centerX + 0.01, 0.68, 0.20]],
    [27, [centerX, 0.85, -0.20]], [28, [centerX + 0.01, 0.85, 0.20]],
    [29, [centerX - 0.01, 0.90, -0.20]], [30, [centerX, 0.90, 0.20]],
    [31, [centerX + 0.04, 0.90, -0.20]], [32, [centerX + 0.05, 0.90, 0.20]]
  ]);
  const landmarks = POSE_LANDMARK_NAMES.map<PoseLandmark>((name, index) => {
    const point = positions.get(index) ?? [centerX, 0.4, 0];
    return { index, name, x: point[0], y: point[1], z: point[2], visibility: 0.95, presence: 0.95,
      worldX: null, worldY: null, worldZ: null };
  });
  return { frameIndex, timestampMs: frameIndex * 100, landmarks, frameWidth: 640, frameHeight: 640 };
}

function fixture(): { frames: PoseFrame[]; cycles: GaitCycle[]; angles: AnglePoint[] } {
  const centers = [0.10, 0.35, 0.50, 0.65, 0.90];
  const frames = Array.from({ length: 50 }, (_, index) => frame(index, centers[Math.floor(index / 10)]!));
  const cycles = centers.map<GaitCycle>((_, index) => ({
    side: "left", startMs: index * 1_000, endMs: index * 1_000 + 900, toeOffMs: index * 1_000 + 600, confidence: 0.9
  }));
  const angles = frames.map<AnglePoint>((item) => ({
    timestampMs: item.timestampMs, cyclePercent: null, side: "left", joint: "knee_flexion",
    angleDegrees: 15, confidence: 0.95
  }));
  return { frames, cycles, angles };
}

describe("spatial validation", () => {
  it("selects at most three eligible camera-side cycles nearest the image centre", () => {
    const { frames, cycles, angles } = fixture();
    const report = validateSpatialBiomechanics(frames, cycles, angles, "left");
    const selected = cyclesSelectedByValidation(cycles, report);
    expect(selected).toHaveLength(3);
    expect(selected.map((cycle) => cycle.startMs)).toEqual([1_000, 2_000, 3_000]);
    expect(report.cycles.filter((cycle) => cycle.selected).every((cycle) => cycle.side === "left")).toBe(true);
  });

  it("never overrides the user-selected camera side when auxiliary inference conflicts", () => {
    const { frames, cycles, angles } = fixture();
    const report = validateSpatialBiomechanics(frames, cycles.map((cycle) => ({ ...cycle, side: "right" })), angles, "right");
    expect(report.cameraSideCheck.inferredSide).toBe("left");
    expect(report.cameraSideCheck.agreement).toBe("conflict");
    expect(report.cameraSideCheck.userSelectedSide).toBe("right");
  });

  it("keeps static-standing assessment validation-only", () => {
    const { frames, cycles, angles } = fixture();
    const report = validateSpatialBiomechanics(frames, cycles, angles, "left");
    expect(report.staticStanding.appliedAsCalibration).toBe(false);
    expect(report.staticStanding.ankleNeutralCandidateDegrees).toBeNull();
  });
});
