import type { PoseFrame } from "../domain/models";
import { MediaPipePoseProvider } from "../pose/MediaPipePoseProvider";

export interface AnalysisProgress {
  completed: number;
  total: number;
  message: string;
}

export class VideoPoseAnalyzer {
  private cancelled = false;

  cancel(): void {
    this.cancelled = true;
  }

  async analyze(
    blob: Blob,
    onProgress: (progress: AnalysisProgress) => void,
    sampleFps = 30
  ): Promise<{ frames: PoseFrame[]; durationMs: number }> {
    this.cancelled = false;
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    const objectUrl = URL.createObjectURL(blob);
    video.src = objectUrl;
    const provider = new MediaPipePoseProvider();
    try {
      await waitForMetadata(video);
      if (!Number.isFinite(video.duration) || video.duration <= 0) {
        throw new Error("動画の長さを取得できませんでした。別形式の動画をお試しください。");
      }
      if (video.duration > 120) {
        throw new Error("現在のWeb版は2分以内の動画に対応しています。動画を短くしてください。");
      }
      if (!video.videoWidth || !video.videoHeight) {
        throw new Error("動画の画像サイズを取得できませんでした。");
      }

      onProgress({ completed: 0, total: 1, message: "Poseモデルを準備しています…" });
      await provider.initialize();

      const frameInterval = 1 / sampleFps;
      const total = Math.max(1, Math.floor(video.duration * sampleFps));
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("動画フレームを読み取れませんでした。");

      const frames: PoseFrame[] = [];
      for (let frameIndex = 0; frameIndex < total; frameIndex += 1) {
        if (this.cancelled) throw new Error("解析を中止しました。");
        const seconds = Math.min(video.duration - 0.001, frameIndex * frameInterval);
        await seek(video, Math.max(0, seconds));
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        // ImageData avoids depending on transferable ImageBitmap support,
        // which varies between iOS/iPadOS Safari releases.
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        const timestampMs = Math.round(seconds * 1000);
        const frame = await provider.detect(imageData, frameIndex, timestampMs);
        frames.push(frame);
        onProgress({
          completed: frameIndex + 1,
          total,
          message: `端末内でPoseを解析中 ${frameIndex + 1} / ${total}`
        });
        await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      }
      return { frames, durationMs: Math.round(video.duration * 1000) };
    } finally {
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute("src");
      video.load();
      await provider.close().catch(() => undefined);
    }
  }
}

function waitForMetadata(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("動画の読み込みに時間がかかっています。端末内の短い動画で再試行してください。"));
    }, 20_000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("loadedmetadata", loaded);
      video.removeEventListener("error", failed);
    };
    const loaded = () => {
      cleanup();
      resolve();
    };
    const failed = () => {
      cleanup();
      reject(new Error("この動画をSafari/ブラウザで開けませんでした。"));
    };
    video.addEventListener("loadedmetadata", loaded, { once: true });
    video.addEventListener("error", failed, { once: true });
    video.load();
  });
}

function seek(video: HTMLVideoElement, seconds: number): Promise<void> {
  if (Math.abs(video.currentTime - seconds) < 0.0005 && video.readyState >= 2) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("動画のシークに失敗しました。短いH.264形式の動画で再試行してください。"));
    }, 10_000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("seeked", completed);
      video.removeEventListener("error", failed);
    };
    const completed = () => {
      cleanup();
      resolve();
    };
    const failed = () => {
      cleanup();
      reject(new Error("動画のフレームを読み取れませんでした。"));
    };
    video.addEventListener("seeked", completed, { once: true });
    video.addEventListener("error", failed, { once: true });
    video.currentTime = seconds;
  });
}
