import type { PoseFrame } from "../domain/models";

const CONNECTIONS: ReadonlyArray<readonly [number, number]> = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24], [23, 25], [25, 27],
  [27, 29], [29, 31], [27, 31], [24, 26], [26, 28],
  [28, 30], [30, 32], [28, 32]
];

export class SkeletonRenderer {
  private readonly context: CanvasRenderingContext2D;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Skeleton Canvasを作成できません。");
    this.context = context;
  }

  draw(frame: PoseFrame | undefined, video: HTMLVideoElement): void {
    const rectangle = this.canvas.getBoundingClientRect();
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rectangle.width * pixelRatio));
    const height = Math.max(1, Math.round(rectangle.height * pixelRatio));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.context.clearRect(0, 0, width, height);
    if (!frame || !video.videoWidth || !video.videoHeight) return;

    const contentScale = Math.min(width / video.videoWidth, height / video.videoHeight);
    const contentWidth = video.videoWidth * contentScale;
    const contentHeight = video.videoHeight * contentScale;
    const offsetX = (width - contentWidth) / 2;
    const offsetY = (height - contentHeight) / 2;
    const points = new Map(
      frame.landmarks
        .filter((item) => item.visibility >= 0.45)
        .map((item) => [
          item.index,
          { x: offsetX + item.x * contentWidth, y: offsetY + item.y * contentHeight }
        ])
    );

    this.context.lineCap = "round";
    this.context.lineJoin = "round";
    this.context.lineWidth = Math.max(2, 3 * pixelRatio);
    this.context.strokeStyle = "rgba(29, 226, 182, 0.95)";
    this.context.shadowColor = "rgba(0, 0, 0, 0.55)";
    this.context.shadowBlur = 3 * pixelRatio;
    for (const [startIndex, endIndex] of CONNECTIONS) {
      const start = points.get(startIndex);
      const end = points.get(endIndex);
      if (!start || !end) continue;
      this.context.beginPath();
      this.context.moveTo(start.x, start.y);
      this.context.lineTo(end.x, end.y);
      this.context.stroke();
    }
    this.context.shadowBlur = 0;
    this.context.fillStyle = "#fff7d6";
    for (const point of points.values()) {
      this.context.beginPath();
      this.context.arc(point.x, point.y, Math.max(2.5, 3.5 * pixelRatio), 0, Math.PI * 2);
      this.context.fill();
    }
  }
}

export function nearestPoseFrame(frames: PoseFrame[], timestampMs: number): PoseFrame | undefined {
  if (!frames.length) return undefined;
  let low = 0;
  let high = frames.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const timestamp = frames[middle]?.timestampMs ?? 0;
    if (timestamp < timestampMs) low = middle + 1;
    else high = middle - 1;
  }
  const candidates = [frames[Math.max(0, high)], frames[Math.min(frames.length - 1, low)]]
    .filter((item): item is PoseFrame => Boolean(item));
  return candidates.reduce((best, item) =>
    Math.abs(item.timestampMs - timestampMs) < Math.abs(best.timestampMs - timestampMs)
      ? item
      : best
  );
}
