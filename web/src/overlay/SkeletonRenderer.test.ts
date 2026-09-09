import { describe, expect, it } from "vitest";
import type { PoseFrame } from "../domain/models";
import { nearestPoseFrame } from "./SkeletonRenderer";

const frame = (timestampMs: number): PoseFrame => ({
  frameIndex: timestampMs / 100,
  timestampMs,
  landmarks: []
});

describe("nearestPoseFrame", () => {
  const frames = [frame(0), frame(100), frame(200)];

  it("returns the closest frame while playing", () => {
    expect(nearestPoseFrame(frames, 149)?.timestampMs).toBe(100);
    expect(nearestPoseFrame(frames, 151)?.timestampMs).toBe(200);
  });

  it("clamps seeks before and after the analyzed range", () => {
    expect(nearestPoseFrame(frames, -10)?.timestampMs).toBe(0);
    expect(nearestPoseFrame(frames, 1000)?.timestampMs).toBe(200);
  });

  it("handles an empty analysis", () => {
    expect(nearestPoseFrame([], 0)).toBeUndefined();
  });
});
