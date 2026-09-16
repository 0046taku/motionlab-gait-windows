import { describe, expect, it } from "vitest";
import type { ManualAngleReference } from "../domain/models";
import { calculateAccuracyMetrics } from "./accuracyValidation";

function reference(id: string, manual: number, raw: number, filtered: number): ManualAngleReference {
  return { id, timestampMs: Number(id), phase: "other", joint: "knee_flexion", side: "right",
    manualAngleDegrees: manual, rawAngleDegrees: raw, filteredAngleDegrees: filtered, analysisVersion: "test" };
}

describe("accuracy acceptance metrics", () => {
  const references = [reference("1", 10, 12, 11), reference("2", 20, 18, 19), reference("3", 30, 35, 31)];

  it("reports raw errors without mixing filtered values", () => {
    const metrics = calculateAccuracyMetrics(references, "raw")!;
    expect(metrics.count).toBe(3);
    expect(metrics.meanBias).toBeCloseTo(5 / 3);
    expect(metrics.meanAbsoluteError).toBeCloseTo(3);
    expect(metrics.rootMeanSquareError).toBeCloseTo(Math.sqrt(11));
    expect(metrics.maximumAbsoluteError).toBe(5);
    expect(metrics.iccAbsoluteAgreement).not.toBeNull();
  });

  it("calculates filtered errors independently", () => {
    const metrics = calculateAccuracyMetrics(references, "filtered")!;
    expect(metrics.meanBias).toBeCloseTo(1 / 3);
    expect(metrics.meanAbsoluteError).toBe(1);
    expect(metrics.maximumAbsoluteError).toBe(1);
  });

  it("does not invent metrics before manual references exist", () => {
    expect(calculateAccuracyMetrics([{ ...references[0]!, manualAngleDegrees: null }], "raw")).toBeNull();
  });
});
