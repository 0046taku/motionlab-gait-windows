import type { PoseFrame } from "../domain/models";
import type { PoseWorkerRequest, PoseWorkerResponse } from "./messages";

interface PendingRequest {
  resolve: (response: PoseWorkerResponse) => void;
  reject: (error: Error) => void;
}

type PoseWorkerRequestInput =
  | { type: "initialize"; assetBase: string }
  | {
      type: "detect";
      frameIndex: number;
      timestampMs: number;
      pixels: ArrayBuffer;
      width: number;
      height: number;
    }
  | { type: "close" };

export class MediaPipePoseProvider {
  private readonly worker: Worker;
  private readonly assetBase: string;
  private readonly pending = new Map<number, PendingRequest>();
  private nextRequestId = 1;

  constructor() {
    this.assetBase = new URL(import.meta.env.BASE_URL, window.location.href).href;
    // MediaPipe's Emscripten loader expects importScripts. A classic Worker keeps
    // inference off the UI thread while remaining compatible with that loader.
    this.worker = new Worker(`${this.assetBase}workers/pose.worker.js`);
    this.worker.onmessage = (event: MessageEvent<PoseWorkerResponse>) => {
      const response = event.data;
      const request = this.pending.get(response.requestId);
      if (!request) return;
      this.pending.delete(response.requestId);
      if (response.type === "error") request.reject(new Error(response.message));
      else request.resolve(response);
    };
    this.worker.onerror = (event) => {
      const error = new Error(event.message || "Pose Workerを開始できませんでした。");
      for (const request of this.pending.values()) request.reject(error);
      this.pending.clear();
    };
  }

  async initialize(): Promise<void> {
    await this.request({ type: "initialize", assetBase: this.assetBase });
  }

  async detect(
    imageData: ImageData,
    frameIndex: number,
    timestampMs: number
  ): Promise<PoseFrame> {
    const pixels = imageData.data.buffer as ArrayBuffer;
    const response = await this.request(
      {
        type: "detect",
        frameIndex,
        timestampMs,
        pixels,
        width: imageData.width,
        height: imageData.height
      },
      [pixels]
    );
    if (response.type !== "result") throw new Error("Pose結果を取得できませんでした。");
    return response.frame;
  }

  async close(): Promise<void> {
    await this.request({ type: "close" });
    this.worker.terminate();
  }

  private request(
    value: PoseWorkerRequestInput,
    transfer: Transferable[] = []
  ): Promise<PoseWorkerResponse> {
    const requestId = this.nextRequestId++;
    return new Promise((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject });
      const message = { ...value, requestId } as PoseWorkerRequest;
      this.worker.postMessage(message, transfer);
    });
  }
}
