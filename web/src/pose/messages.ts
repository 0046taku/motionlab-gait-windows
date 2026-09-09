import type { PoseFrame } from "../domain/models";

export type PoseWorkerRequest =
  | { type: "initialize"; requestId: number; assetBase: string }
  | {
      type: "detect";
      requestId: number;
      frameIndex: number;
      timestampMs: number;
      pixels: ArrayBuffer;
      width: number;
      height: number;
    }
  | { type: "close"; requestId: number };

export type PoseWorkerResponse =
  | { type: "ready"; requestId: number }
  | { type: "result"; requestId: number; frame: PoseFrame }
  | { type: "closed"; requestId: number }
  | { type: "error"; requestId: number; message: string };
