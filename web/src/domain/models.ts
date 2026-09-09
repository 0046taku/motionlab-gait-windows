export const POSE_LANDMARK_NAMES = [
  "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
  "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
  "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
  "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
  "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
  "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
  "right_heel", "left_foot_index", "right_foot_index"
] as const;

export interface Patient {
  id: string;
  patientCode: string;
  displayName: string;
  note: string;
  createdAt: string;
}

export interface PoseLandmark {
  index: number;
  name: string;
  x: number;
  y: number;
  z: number;
  visibility: number;
  presence: number | null;
  worldX: number | null;
  worldY: number | null;
  worldZ: number | null;
}

export interface PoseFrame {
  frameIndex: number;
  timestampMs: number;
  landmarks: PoseLandmark[];
}

export type VideoStatus = "pending" | "analyzing" | "ready" | "failed";

export interface VideoStudy {
  id: string;
  patientId: string;
  originalName: string;
  createdAt: string;
  durationMs: number;
  status: VideoStatus;
  error: string;
  video: Blob;
  poseFrames: PoseFrame[];
  schema: "motionlab.pose.v1";
  analysisVersion: "motionlab-gait-web/0.1.0";
}

export interface StorageEstimate {
  usage: number;
  quota: number;
}
