import { describe, expect, it } from "vitest";
import type { VideoStudy } from "../domain/models";
import { compareCaptureConditions, previousReadyStudy } from "./captureConditions";

function study(overrides: Partial<VideoStudy> = {}): VideoStudy {
  return {
    id: "current", patientId: "p1", originalName: "test.mp4", createdAt: "2026-09-15T10:00:00Z",
    durationMs: 1000, status: "ready", error: "", video: new Blob(), poseFrames: [],
    schema: "motionlab.pose.v1", analysisVersion: "motionlab-gait-web/0.3.0",
    captureConditions: { gaitMode: "comfortable", orthosis: "none", walkingAid: "none", cameraSide: "left" },
    videoMetadata: { frameWidth: 1920, frameHeight: 1080, estimatedFps: 59.94,
      timestampSource: "presentation_timestamps", averageBrightness: 100, lowBrightnessRate: 0, analyzedFrameCount: 60 },
    ...overrides
  };
}

describe("capture-condition comparison", () => {
  it("treats 59.94 and 60 fps as the same protocol", () => {
    expect(compareCaptureConditions(study(), study({ id: "previous", videoMetadata: {
      ...study().videoMetadata!, estimatedFps: 60
    } }))).toEqual({ status: "same", differences: [] });
  });

  it("reports clinically relevant condition differences", () => {
    const result = compareCaptureConditions(study(), study({ id: "previous", captureConditions: {
      gaitMode: "maximum", orthosis: "used", walkingAid: "cane_single", cameraSide: "right"
    }, videoMetadata: { ...study().videoMetadata!, estimatedFps: 30 } }));
    expect(result.status).toBe("different");
    expect(result.differences).toEqual(["歩行速度", "装具", "歩行補助具", "カメラ側", "fps"]);
  });

  it("does not claim equivalence when old studies lack protocol data", () => {
    expect(compareCaptureConditions(study(), study({ id: "previous", captureConditions: undefined })).status)
      .toBe("insufficient");
  });

  it("selects the nearest earlier ready study", () => {
    const current = study();
    const previous = study({ id: "previous", createdAt: "2026-09-14T10:00:00Z" });
    const older = study({ id: "older", createdAt: "2026-09-13T10:00:00Z" });
    const failed = study({ id: "failed", createdAt: "2026-09-14T12:00:00Z", status: "failed" });
    expect(previousReadyStudy(current, [older, failed, previous])?.id).toBe("previous");
  });
});
