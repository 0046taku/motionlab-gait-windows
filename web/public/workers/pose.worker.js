const POSE_LANDMARK_NAMES = [
  "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
  "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
  "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
  "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
  "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
  "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
  "right_heel", "left_foot_index", "right_foot_index"
];

let landmarker = null;
let allowedOrigin = null;
const nativeFetch = self.fetch.bind(self);

self.fetch = (input, init) => {
  const target = input instanceof Request ? input.url : input.toString();
  const url = new URL(target, self.location.href);
  if (allowedOrigin === null || (url.origin !== allowedOrigin && url.protocol !== "blob:" && url.protocol !== "data:")) {
    return Promise.reject(new Error("Privacy guard blocked an external request."));
  }
  return nativeFetch(input, init);
};

function reply(message) {
  self.postMessage(message);
}

self.onmessage = async (event) => {
  const request = event.data;
  try {
    if (request.type === "initialize") {
      allowedOrigin = new URL(request.assetBase).origin;
      importScripts(`${request.assetBase}mediapipe/vision_bundle.js`);
      // Self-hosted classic glue avoids dynamic-import differences in Safari Workers.
      importScripts(`${request.assetBase}wasm/vision_wasm_classic_internal.js`);
      const vision = {
        wasmBinaryPath: `${request.assetBase}wasm/vision_wasm_internal.wasm`
      };
      landmarker = await Vision.PoseLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: `${request.assetBase}models/pose_landmarker_full.task`,
          delegate: "CPU"
        },
        runningMode: "VIDEO",
        numPoses: 1,
        minPoseDetectionConfidence: 0.5,
        minPosePresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
        outputSegmentationMasks: false
      });
      reply({ type: "ready", requestId: request.requestId });
      return;
    }

    if (request.type === "detect") {
      if (!landmarker) throw new Error("Poseモデルが初期化されていません。");
      const image = new ImageData(
        new Uint8ClampedArray(request.pixels),
        request.width,
        request.height
      );
      const result = landmarker.detectForVideo(image, request.timestampMs);
      const normalized = result.landmarks[0] || [];
      const world = result.worldLandmarks[0] || [];
      const landmarks = normalized.map((item, index) => {
        const worldItem = world[index];
        return {
          index,
          name: POSE_LANDMARK_NAMES[index] || `landmark_${index}`,
          x: item.x,
          y: item.y,
          z: item.z,
          visibility: item.visibility ?? 0,
          // MediaPipe Tasks Vision for Web 1.0.1 does not expose presence per landmark.
          presence: null,
          worldX: worldItem?.x ?? null,
          worldY: worldItem?.y ?? null,
          worldZ: worldItem?.z ?? null
        };
      });
      reply({
        type: "result",
        requestId: request.requestId,
        frame: {
          frameIndex: request.frameIndex,
          timestampMs: request.timestampMs,
          landmarks
        }
      });
      return;
    }

    landmarker?.close();
    landmarker = null;
    reply({ type: "closed", requestId: request.requestId });
  } catch (error) {
    reply({
      type: "error",
      requestId: request.requestId,
      message: error instanceof Error ? error.message : "Pose解析で不明なエラーが発生しました。"
    });
  }
};
