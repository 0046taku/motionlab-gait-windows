import type { GaitPhaseLabel, ManualAngleReference } from "../domain/models";
import type { AnglePoint, GaitAnalysisResult, Side } from "../analysis/types";

export interface AccuracyMetrics {
  count: number;
  meanBias: number;
  meanAbsoluteError: number;
  rootMeanSquareError: number;
  maximumAbsoluteError: number;
  lowerLimitOfAgreement: number;
  upperLimitOfAgreement: number;
  iccAbsoluteAgreement: number | null;
}

const PHASES: readonly { percent: number; phase: GaitPhaseLabel }[] = [
  { percent: 0, phase: "IC" }, { percent: 10, phase: "loading_response" },
  { percent: 30, phase: "mid_stance" }, { percent: 50, phase: "terminal_stance" },
  { percent: 60, phase: "pre_swing" }, { percent: 70, phase: "initial_swing" },
  { percent: 82, phase: "mid_swing" }, { percent: 95, phase: "terminal_swing" }
];

export function suggestKneeReferences(result: GaitAnalysisResult): ManualAngleReference[] {
  const side = result.primarySide;
  if (!side) return [];
  return result.cycles.slice(0, 2).flatMap((cycle, cycleIndex) => PHASES.map(({ percent, phase }) => {
    const timestampMs = Math.round(cycle.startMs + (cycle.endMs - cycle.startMs) * percent / 100);
    return buildReference(result, side, timestampMs, phase, `suggested-${cycleIndex}-${percent}`);
  }));
}

export function buildReference(
  result: GaitAnalysisResult, side: Side, timestampMs: number, phase: GaitPhaseLabel, id: string = crypto.randomUUID()
): ManualAngleReference {
  return {
    id, timestampMs, phase, joint: "knee_flexion", side, manualAngleDegrees: null,
    rawAngleDegrees: nearestAngle(result.continuousRawAngles, side, timestampMs),
    filteredAngleDegrees: nearestAngle(result.continuousFilteredAngles, side, timestampMs),
    analysisVersion: result.analysisVersion
  };
}

export function calculateAccuracyMetrics(
  references: readonly ManualAngleReference[], source: "raw" | "filtered"
): AccuracyMetrics | null {
  const pairs = references.map((reference) => ({
    manual: reference.manualAngleDegrees,
    motionLab: source === "raw" ? reference.rawAngleDegrees : reference.filteredAngleDegrees
  })).filter((pair): pair is { manual: number; motionLab: number } => pair.manual !== null && pair.motionLab !== null);
  if (!pairs.length) return null;
  const errors = pairs.map((pair) => pair.motionLab - pair.manual);
  const meanBias = average(errors);
  const sampleSd = errors.length > 1
    ? Math.sqrt(errors.reduce((sum, error) => sum + (error - meanBias) ** 2, 0) / (errors.length - 1)) : 0;
  return {
    count: pairs.length,
    meanBias,
    meanAbsoluteError: average(errors.map(Math.abs)),
    rootMeanSquareError: Math.sqrt(average(errors.map((error) => error ** 2))),
    maximumAbsoluteError: Math.max(...errors.map(Math.abs)),
    lowerLimitOfAgreement: meanBias - 1.96 * sampleSd,
    upperLimitOfAgreement: meanBias + 1.96 * sampleSd,
    iccAbsoluteAgreement: pairs.length >= 3 ? iccA1(pairs.map((pair) => [pair.manual, pair.motionLab])) : null
  };
}

function nearestAngle(points: readonly AnglePoint[], side: Side, timestampMs: number): number | null {
  const matches = points.filter((point) => point.side === side && point.joint === "knee_flexion");
  if (!matches.length) return null;
  return matches.reduce((best, point) => Math.abs(point.timestampMs - timestampMs) < Math.abs(best.timestampMs - timestampMs) ? point : best)
    .angleDegrees;
}

function iccA1(rows: readonly (readonly [number, number])[]): number | null {
  const n = rows.length; const k = 2;
  if (n < 3) return null;
  const rowMeans = rows.map((row) => average(row));
  const columnMeans = [average(rows.map((row) => row[0])), average(rows.map((row) => row[1]))];
  const grand = average(rowMeans);
  const msRows = k * rowMeans.reduce((sum, value) => sum + (value - grand) ** 2, 0) / (n - 1);
  const msColumns = n * columnMeans.reduce((sum, value) => sum + (value - grand) ** 2, 0) / (k - 1);
  let residual = 0;
  rows.forEach((row, rowIndex) => row.forEach((value, columnIndex) => {
    residual += (value - rowMeans[rowIndex]! - columnMeans[columnIndex]! + grand) ** 2;
  }));
  const msError = residual / ((n - 1) * (k - 1));
  const denominator = msRows + (k - 1) * msError + k * (msColumns - msError) / n;
  return Math.abs(denominator) < 1e-12 ? null : (msRows - msError) / denominator;
}

function average(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}
