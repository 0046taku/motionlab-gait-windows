import type { CaptureConditions, VideoStudy } from "../domain/models";

export interface CaptureConditionComparison {
  status: "same" | "different" | "insufficient";
  differences: string[];
}

export function compareCaptureConditions(
  current: VideoStudy,
  previous: VideoStudy
): CaptureConditionComparison {
  const currentConditions = current.captureConditions;
  const previousConditions = previous.captureConditions;
  if (!hasDocumentedConditions(currentConditions) || !hasDocumentedConditions(previousConditions)
    || !current.videoMetadata || !previous.videoMetadata) {
    return { status: "insufficient", differences: [] };
  }
  const differences: string[] = [];
  if (currentConditions.gaitMode !== previousConditions.gaitMode) differences.push("歩行速度");
  if (currentConditions.orthosis !== previousConditions.orthosis) differences.push("装具");
  if (currentConditions.walkingAid !== previousConditions.walkingAid) differences.push("歩行補助具");
  if (currentConditions.cameraSide !== previousConditions.cameraSide) differences.push("カメラ側");
  if (nominalFps(current.videoMetadata.estimatedFps) !== nominalFps(previous.videoMetadata.estimatedFps)) {
    differences.push("fps");
  }
  return { status: differences.length ? "different" : "same", differences };
}

export function previousReadyStudy(current: VideoStudy, studies: readonly VideoStudy[]): VideoStudy | null {
  return studies
    .filter((study) => study.id !== current.id && study.status === "ready" && study.createdAt < current.createdAt)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0] ?? null;
}

function hasDocumentedConditions(conditions: CaptureConditions | undefined): conditions is CaptureConditions {
  return Boolean(conditions && conditions.gaitMode !== "unspecified" && conditions.orthosis !== "unspecified"
    && conditions.walkingAid !== "unspecified" && conditions.cameraSide !== "unspecified");
}

function nominalFps(fps: number): number {
  if (fps >= 50) return 60;
  if (fps >= 24) return 30;
  return Math.round(fps);
}
