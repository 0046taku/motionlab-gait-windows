import type { PoseFrame, VideoAnalysisMetadata } from "../domain/models";
import { effectivePresence } from "./landmarkProcessor";
import { clamp, mean, standardDeviation } from "./statistics";
import type { AcquisitionQuality, GaitCycle, Side, ViewpointReport } from "./types";

const FULL_BODY = [0, 11, 12, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32] as const;
const LOWER_LIMB: Record<Side, readonly number[]> = {
  left: [23, 25, 27, 29, 31], right: [24, 26, 28, 30, 32]
};
const FOOT: Record<Side, readonly number[]> = {
  left: [27, 29, 31], right: [28, 30, 32]
};

export function assessAcquisitionQuality(
  frames: readonly PoseFrame[],
  metadata: VideoAnalysisMetadata | undefined,
  viewpoint: ViewpointReport,
  cycles: readonly GaitCycle[],
  primarySide: Side | null
): AcquisitionQuality {
  const fullBodyCoverage = coverage(frames, FULL_BODY);
  const lowerCoverage = {
    left: coverage(frames, LOWER_LIMB.left), right: coverage(frames, LOWER_LIMB.right)
  };
  const footCoverageBySide = {
    left: coverage(frames, FOOT.left), right: coverage(frames, FOOT.right)
  };
  const primaryLimbCoverage = primarySide
    ? lowerCoverage[primarySide] : Math.max(lowerCoverage.left, lowerCoverage.right);
  const footCoverage = primarySide
    ? footCoverageBySide[primarySide] : Math.max(footCoverageBySide.left, footCoverageBySide.right);
  const cameraStability = cameraStabilityScore(frames, metadata);
  const framing = framingHeight(frames);
  const hardReasons: string[] = [];
  const cautionReasons: string[] = [];

  if (!hasFrameGeometry(frames, metadata)) hardReasons.push("解析フレーム寸法がないため、Poseの再解析が必要です");
  if (!viewpoint.analysisSupported) hardReasons.push("安定した真横の歩行区間を確認できません");
  if (primaryLimbCoverage < 0.55) hardReasons.push(`${sideLabel(primarySide)}下肢の追跡が途中で失われています`);
  else if (primaryLimbCoverage < 0.78) cautionReasons.push(`${sideLabel(primarySide)}下肢に遮蔽または追跡欠損があります`);
  if (footCoverage < 0.50) hardReasons.push(`${sideLabel(primarySide)}踵・足先の追跡が不十分です`);
  else if (footCoverage < 0.75) cautionReasons.push(`${sideLabel(primarySide)}踵・足先が一部不安定です`);
  if (cycles.length < 2) hardReasons.push("解析可能な歩行周期が2周期未満です");
  else if (cycles.length < 4) cautionReasons.push("解析可能な歩行周期が少ないため再現性に注意が必要です");
  if (cameraStability < 0.45) hardReasons.push("カメラ移動または画角変化の可能性があります");
  else if (cameraStability < 0.72) cautionReasons.push("カメラの固定状態を確認してください");
  if (metadata) {
    const sourceWidth = metadata.sourceWidth ?? metadata.frameWidth;
    const sourceHeight = metadata.sourceHeight ?? metadata.frameHeight;
    if (sourceHeight > sourceWidth) hardReasons.push("動画が縦向きです。横向きで撮影してください");
    if (metadata.lowBrightnessRate > 0.60 || metadata.averageBrightness < 35) hardReasons.push("暗いフレームが多く、Pose追跡が不安定です");
    else if (metadata.lowBrightnessRate > 0.25 || metadata.averageBrightness < 55) cautionReasons.push("照明が不足している可能性があります");
    if (metadata.estimatedFps < 24) cautionReasons.push("動画fpsが低く、歩行イベントの時間精度に注意が必要です");
    if (metadata.timestampSource === "fixed_30fps_fallback") cautionReasons.push("実timestampを取得できず30fps間隔で解析しました");
  }
  if (viewpoint.analysisSupported && viewpoint.stableSagittalScore < 0.72) cautionReasons.push("カメラが完全な真横ではない可能性があります");
  if (fullBodyCoverage < 0.70) cautionReasons.push("全身ランドマークが一部フレームで欠けています");
  if (framing > 0.94) hardReasons.push("全身が画角ぎりぎりです。少し離れてください");
  else if (framing > 0.88) cautionReasons.push("全身が画角に近すぎます。少し離れてください");
  else if (framing > 0 && framing < 0.30) cautionReasons.push("人物が小さいため、少し近づいてください");

  const status = hardReasons.length ? "retake" : cautionReasons.length ? "caution" : "high";
  const reasons = [...hardReasons, ...cautionReasons].filter((value, index, values) => values.indexOf(value) === index).slice(0, 3);
  return {
    status, reasons, fullBodyCoverage, footCoverage, primaryLimbCoverage,
    cameraStability, sideViewScore: viewpoint.stableSagittalScore, cycleCount: cycles.length
  };
}

function framingHeight(frames: readonly PoseFrame[]): number {
  const heights: number[] = [];
  for (const frame of frames) {
    const visible = frame.landmarks.filter((item) =>
      Math.min(item.visibility, effectivePresence(item.visibility, item.presence)) >= 0.5
    );
    if (visible.length < 10) continue;
    const values = visible.map((item) => item.y);
    heights.push(Math.max(...values) - Math.min(...values));
  }
  if (!heights.length) return 0;
  return [...heights].sort((a, b) => a - b)[Math.floor(heights.length / 2)]!;
}

function hasFrameGeometry(frames: readonly PoseFrame[], metadata: VideoAnalysisMetadata | undefined): boolean {
  if (metadata && metadata.frameWidth > 0 && metadata.frameHeight > 0) return true;
  return frames.some((frame) => (frame.frameWidth ?? 0) > 0 && (frame.frameHeight ?? 0) > 0);
}

function coverage(frames: readonly PoseFrame[], indices: readonly number[]): number {
  if (!frames.length) return 0;
  let valid = 0;
  for (const frame of frames) {
    const points = new Map(frame.landmarks.map((item) => [item.index, item]));
    for (const index of indices) {
      const point = points.get(index);
      if (point && Math.min(point.visibility, effectivePresence(point.visibility, point.presence)) >= 0.5) valid += 1;
    }
  }
  return valid / (frames.length * indices.length);
}

function cameraStabilityScore(frames: readonly PoseFrame[], metadata: VideoAnalysisMetadata | undefined): number {
  const torsoLengths: number[] = [];
  for (const frame of frames) {
    const width = frame.frameWidth ?? metadata?.frameWidth;
    const height = frame.frameHeight ?? metadata?.frameHeight;
    if (!width || !height) continue;
    const points = new Map(frame.landmarks.map((item) => [item.index, item]));
    const shoulders = [points.get(11), points.get(12)]; const hips = [points.get(23), points.get(24)];
    if (shoulders.some((item) => !item) || hips.some((item) => !item)) continue;
    const shoulderX = mean(shoulders.map((item) => item!.x * width));
    const shoulderY = mean(shoulders.map((item) => item!.y * height));
    const hipX = mean(hips.map((item) => item!.x * width));
    const hipY = mean(hips.map((item) => item!.y * height));
    torsoLengths.push(Math.hypot(shoulderX - hipX, shoulderY - hipY));
  }
  if (torsoLengths.length < 10) return 0;
  const average = mean(torsoLengths);
  if (average <= 1e-6) return 0;
  const coefficientOfVariation = standardDeviation(torsoLengths) / average;
  return clamp(1 - coefficientOfVariation / 0.15);
}

function sideLabel(side: Side | null): string {
  return side === "left" ? "カメラ側（左）の" : side === "right" ? "カメラ側（右）の" : "カメラ側の";
}
