import type { Joint } from "./types";

export const REFERENCE_LABEL = "成人・平地・快適歩行の概略参考（診断基準ではありません）";

const ANCHORS: Record<Joint, { percentages: number[]; means: number[]; halfWidth: number }> = {
  hip_flexion: { percentages: [0, 10, 30, 50, 60, 75, 100], means: [28, 24, 8, -8, -10, 12, 28], halfWidth: 10 },
  knee_flexion: { percentages: [0, 10, 30, 50, 60, 75, 100], means: [5, 15, 5, 10, 35, 60, 5], halfWidth: 12 },
  ankle_dorsiflexion: { percentages: [0, 10, 30, 50, 60, 70, 85, 100], means: [0, -7, 5, 10, -15, -5, 3, 0], halfWidth: 8 }
};

export function normalReference(joint: Joint): { percent: number; mean: number; lower: number; upper: number }[] {
  const source = ANCHORS[joint];
  return Array.from({ length: 101 }, (_, percent) => {
    let right = source.percentages.findIndex((value) => value >= percent);
    if (right < 0) right = source.percentages.length - 1;
    const left = Math.max(0, right - 1);
    const x0 = source.percentages[left]!; const x1 = source.percentages[right]!;
    const y0 = source.means[left]!; const y1 = source.means[right]!;
    const value = x1 === x0 ? y0 : y0 + ((percent - x0) / (x1 - x0)) * (y1 - y0);
    return { percent, mean: value, lower: value - source.halfWidth, upper: value + source.halfWidth };
  });
}

