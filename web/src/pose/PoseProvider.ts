import type { PoseFrame } from "../domain/models";

/** Pose-engine boundary. Biomechanics code depends on PoseFrame, never MediaPipe APIs. */
export interface PoseProvider {
  initialize(): Promise<void>;
  detect(imageData: ImageData, frameIndex: number, timestampMs: number): Promise<PoseFrame>;
  close(): Promise<void>;
}

export type PoseProviderFactory = () => PoseProvider;
