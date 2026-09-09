import { describe, expect, it } from "vitest";
import { isLocalAppResource } from "./egressGuard";

describe("isLocalAppResource", () => {
  const base = "https://motionlab.example/app/";

  it("allows same-origin app and model resources", () => {
    expect(isLocalAppResource("./models/pose.task", base)).toBe(true);
    expect(isLocalAppResource("https://motionlab.example/app/video", base)).toBe(true);
  });

  it("allows in-memory video resources", () => {
    expect(isLocalAppResource("blob:https://motionlab.example/id", base)).toBe(true);
    expect(isLocalAppResource("data:application/octet-stream;base64,AA==", base)).toBe(true);
  });

  it("rejects every external origin", () => {
    expect(isLocalAppResource("https://example.org/telemetry", base)).toBe(false);
    expect(isLocalAppResource("https://storage.googleapis.com/model", base)).toBe(false);
  });
});
