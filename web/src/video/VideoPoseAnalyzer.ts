import type { PoseFrame, VideoAnalysisMetadata } from "../domain/models";
import { MediaPipePoseProvider } from "../pose/MediaPipePoseProvider";
import type { PoseProviderFactory } from "../pose/PoseProvider";

export interface AnalysisProgress {
  completed: number;
  total: number;
  message: string;
}

export interface VideoPoseAnalysisOptions {
  fallbackSampleFps?: number;
  cameraSide?: "left" | "right" | "unspecified";
}

export class VideoPoseAnalyzer {
  private cancelled = false;

  constructor(private readonly poseProviderFactory: PoseProviderFactory = () => new MediaPipePoseProvider()) {}

  cancel(): void {
    this.cancelled = true;
  }

  async analyze(
    blob: Blob,
    onProgress: (progress: AnalysisProgress) => void,
    options: VideoPoseAnalysisOptions = {}
  ): Promise<{ frames: PoseFrame[]; durationMs: number; metadata: VideoAnalysisMetadata }> {
    this.cancelled = false;
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.style.cssText = "position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;left:-10px;top:-10px";
    document.body.append(video);
    const objectUrl = URL.createObjectURL(blob);
    video.src = objectUrl;
    const provider = this.poseProviderFactory();
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

      onProgress({ completed: 0, total: 1, message: "動画の実timestampを確認しています…" });
      const presentationTimestamps = await collectPresentationTimestamps(
        video, () => this.cancelled
      ).catch(() => null);
      if (this.cancelled) throw new Error("解析を中止しました。");
      const timestamps = presentationTimestamps && presentationTimestamps.length >= 10
        ? presentationTimestamps
        : fixedTimestamps(video.duration, options.fallbackSampleFps ?? 30);
      const timestampSource: VideoAnalysisMetadata["timestampSource"] = presentationTimestamps && presentationTimestamps.length >= 10
        ? "presentation_timestamps" : "fixed_30fps_fallback";
      const total = timestamps.length;
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("動画フレームを読み取れませんでした。");

      const frames: PoseFrame[] = [];
      const brightnessValues: number[] = [];
      const sharpnessScores: { timestampMs: number; sharpness: number }[] = [];
      for (let frameIndex = 0; frameIndex < timestamps.length; frameIndex += 1) {
        if (this.cancelled) throw new Error("解析を中止しました。");
        const seconds = Math.min(video.duration - 0.001, timestamps[frameIndex]!);
        await seek(video, Math.max(0, seconds));
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        // ImageData avoids depending on transferable ImageBitmap support,
        // which varies between iOS/iPadOS Safari releases.
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        brightnessValues.push(estimateBrightness(imageData));
        const timestampMs = Math.round(seconds * 1000);
        const frame = await provider.detect(imageData, frameIndex, timestampMs);
        frames.push(frame);
        const sharpness = estimateDistalSharpness(context, canvas.width, canvas.height, frame, options.cameraSide);
        if (sharpness !== null) sharpnessScores.push({ timestampMs, sharpness });
        onProgress({
          completed: frameIndex + 1,
          total,
          message: `端末内でPoseを解析中 ${frameIndex + 1} / ${total}`
        });
        await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
      }
      const intervals = timestamps.slice(1).map((value, index) => value - timestamps[index]!)
        .filter((value) => value > 0 && value <= 1);
      const estimatedFps = intervals.length ? 1 / median(intervals) : options.fallbackSampleFps ?? 30;
      const medianSharpness = median(sharpnessScores.map((item) => item.sharpness));
      const lowSharpnessFlags = sharpnessScores.map((item) => item.sharpness < medianSharpness * 0.55);
      const longestConsecutiveLowFrames = longestTrueRun(lowSharpnessFlags);
      return {
        frames,
        durationMs: Math.round(video.duration * 1000),
        metadata: {
          sourceWidth: video.videoWidth,
          sourceHeight: video.videoHeight,
          frameWidth: canvas.width,
          frameHeight: canvas.height,
          estimatedFps,
          timestampSource,
          averageBrightness: average(brightnessValues),
          lowBrightnessRate: brightnessValues.length
            ? brightnessValues.filter((value) => value < 45).length / brightnessValues.length : 1,
          analyzedFrameCount: frames.length,
          motionBlurValidation: sharpnessScores.length ? {
            method: "camera-side-distal-gradient-v1",
            cameraSide: options.cameraSide ?? "unspecified",
            scores: sharpnessScores,
            medianSharpness,
            lowSharpnessRate: lowSharpnessFlags.filter(Boolean).length / sharpnessScores.length,
            longestConsecutiveLowFrames,
            reviewRecommended: longestConsecutiveLowFrames >= Math.max(3, Math.round(estimatedFps * 0.15))
          } : undefined
        }
      };
    } finally {
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute("src");
      video.load();
      video.remove();
      await provider.close().catch(() => undefined);
    }
  }
}

function estimateDistalSharpness(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  frame: PoseFrame,
  side: "left" | "right" | "unspecified" | undefined
): number | null {
  if (side !== "left" && side !== "right") return null;
  const indices = side === "left" ? [25, 27, 29, 31] : [26, 28, 30, 32];
  const landmarks = frame.landmarks.filter((item) => indices.includes(item.index) && item.visibility >= 0.5);
  if (landmarks.length < 3) return null;
  const radius = Math.max(4, Math.round(Math.min(width, height) * 0.025));
  const scores: number[] = [];
  for (const landmark of landmarks) {
    const left = Math.max(0, Math.round(landmark.x * width) - radius);
    const top = Math.max(0, Math.round(landmark.y * height) - radius);
    const patchWidth = Math.min(width - left, radius * 2 + 1);
    const patchHeight = Math.min(height - top, radius * 2 + 1);
    if (patchWidth < 5 || patchHeight < 5) continue;
    const patch = context.getImageData(left, top, patchWidth, patchHeight);
    scores.push(meanGradientMagnitude(patch));
  }
  return scores.length ? average(scores) : null;
}

function meanGradientMagnitude(image: ImageData): number {
  const gray = (index: number) => 0.2126 * image.data[index]! + 0.7152 * image.data[index + 1]! + 0.0722 * image.data[index + 2]!;
  let total = 0; let count = 0;
  for (let y = 1; y < image.height - 1; y += 1) {
    for (let x = 1; x < image.width - 1; x += 1) {
      const center = 4 * (y * image.width + x);
      const gx = gray(center + 4) - gray(center - 4);
      const gy = gray(center + 4 * image.width) - gray(center - 4 * image.width);
      total += Math.hypot(gx, gy); count += 1;
    }
  }
  return count ? total / count : 0;
}

function fixedTimestamps(duration: number, fps: number): number[] {
  const total = Math.max(1, Math.floor(duration * fps));
  return Array.from({ length: total }, (_, index) => index / fps);
}

function collectPresentationTimestamps(
  video: HTMLVideoElement,
  isCancelled: () => boolean
): Promise<number[] | null> {
  if (typeof video.requestVideoFrameCallback !== "function") return Promise.resolve(null);
  return new Promise((resolve) => {
    const timestamps: number[] = [];
    let settled = false;
    let handle: number | null = null;
    const finish = (value: number[] | null) => {
      if (settled) return;
      settled = true;
      if (handle !== null && typeof video.cancelVideoFrameCallback === "function") {
        video.cancelVideoFrameCallback(handle);
      }
      window.clearTimeout(timeout);
      video.removeEventListener("ended", ended);
      video.pause();
      resolve(value);
    };
    const callback: VideoFrameRequestCallback = (_now, metadata) => {
      if (isCancelled()) { finish(timestamps); return; }
      const mediaTime = metadata.mediaTime;
      if (Number.isFinite(mediaTime) && (timestamps.length === 0 || mediaTime - timestamps.at(-1)! > 0.0001)) {
        timestamps.push(mediaTime);
      }
      if (!video.ended) handle = video.requestVideoFrameCallback(callback);
    };
    const ended = () => finish(timestamps);
    const timeout = window.setTimeout(
      () => finish(null),
      Math.min(150_000, Math.max(20_000, video.duration * 2_000 + 10_000))
    );
    video.addEventListener("ended", ended, { once: true });
    video.currentTime = 0;
    handle = video.requestVideoFrameCallback(callback);
    void video.play().catch(() => finish(null));
  });
}

function estimateBrightness(image: ImageData): number {
  const data = image.data;
  let total = 0;
  let samples = 0;
  const stride = 4 * 64;
  for (let index = 0; index < data.length; index += stride) {
    total += 0.2126 * data[index]! + 0.7152 * data[index + 1]! + 0.0722 * data[index + 2]!;
    samples += 1;
  }
  return samples ? total / samples : 0;
}

function average(values: readonly number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function median(values: readonly number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle]! : (sorted[middle - 1]! + sorted[middle]!) / 2;
}

function longestTrueRun(values: readonly boolean[]): number {
  let longest = 0; let current = 0;
  for (const value of values) {
    current = value ? current + 1 : 0;
    longest = Math.max(longest, current);
  }
  return longest;
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
