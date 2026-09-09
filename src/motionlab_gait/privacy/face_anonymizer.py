from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from motionlab_gait.domain.models import PoseFrame, VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore

Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class AnonymizationReport:
    output_path: Path
    frame_count: int
    detector_frames: int
    pose_fallback_frames: int
    tracked_fallback_frames: int
    unblurred_frames: int
    output_width: int
    output_height: int

    @property
    def needs_review(self) -> bool:
        return self.unblurred_frames > 0 or self.pose_fallback_frames > 0


class FaceAnonymizer:
    """Create a blurred copy while retaining the original for visual review."""

    def __init__(self, model_path: Path, landmark_store: LandmarkStore | None = None) -> None:
        self.model_path = model_path
        self.landmark_store = landmark_store or LandmarkStore()

    def anonymize(
        self,
        video: VideoRecord,
        processed_pose_path: Path,
        *,
        is_cancelled=None,
        progress=None,
    ) -> AnonymizationReport:
        if not self.model_path.is_file():
            raise FileNotFoundError(f"顔検出モデルが見つかりません: {self.model_path}")

        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        timeline = self.landmark_store.read(processed_pose_path)
        capture = cv2.VideoCapture(str(video.stored_path))
        if not capture.isOpened():
            raise RuntimeError("匿名化する動画を開けませんでした。")
        output_path = video.stored_path.with_name(f"{video.stored_path.stem}.anonymized.mp4")
        temporary_path = output_path.with_name(f"{output_path.stem}.writing.mp4")
        output_scale = min(1.0, 960.0 / max(video.width, video.height))
        output_width = max(2, round(video.width * output_scale / 2) * 2)
        output_height = max(2, round(video.height * output_scale / 2) * 2)
        writer = cv2.VideoWriter(
            str(temporary_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            video.fps,
            (output_width, output_height),
        )
        if not writer.isOpened():
            capture.release()
            raise RuntimeError("匿名化動画のエンコーダーを開始できませんでした。")

        options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.45,
            min_suppression_threshold=0.3,
        )
        frame_index = 0
        detector_frames = 0
        pose_fallback_frames = 0
        tracked_fallback_frames = 0
        unblurred_frames = 0
        last_boxes: list[Box] = []
        missing_run = 0
        inference_scale = min(1.0, 640.0 / max(output_width, output_height))
        try:
            with vision.FaceDetector.create_from_options(options) as detector:
                while True:
                    if is_cancelled and is_cancelled():
                        raise RuntimeError("匿名化処理を中止しました。")
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if output_scale < 1.0:
                        frame = cv2.resize(
                            frame,
                            (output_width, output_height),
                            interpolation=cv2.INTER_AREA,
                        )
                    timestamp_ms = max(0, round(frame_index * 1000.0 / video.fps))
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if inference_scale < 1.0:
                        inference_rgb = cv2.resize(
                            rgb,
                            None,
                            fx=inference_scale,
                            fy=inference_scale,
                            interpolation=cv2.INTER_AREA,
                        )
                    else:
                        inference_rgb = rgb
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=inference_rgb)
                    result = detector.detect_for_video(image, timestamp_ms)
                    boxes = [
                        self._expand_box(
                            self._scale_box(
                                (
                                    int(item.bounding_box.origin_x),
                                    int(item.bounding_box.origin_y),
                                    int(item.bounding_box.width),
                                    int(item.bounding_box.height),
                                ),
                                1.0 / inference_scale,
                            ),
                            output_width,
                            output_height,
                        )
                        for item in result.detections
                    ]
                    if boxes:
                        detector_frames += 1
                    pose_frame = timeline.nearest(
                        timestamp_ms, max(40, round(1000.0 / max(video.fps, 1.0)))
                    )
                    pose_box = self._pose_face_box(pose_frame, output_width, output_height)
                    if pose_box is not None and not any(
                        self._intersection_over_union(pose_box, box) > 0.25 for box in boxes
                    ):
                        boxes.append(pose_box)
                        pose_fallback_frames += 1

                    if boxes:
                        last_boxes = boxes
                        missing_run = 0
                    elif last_boxes and missing_run < 8:
                        boxes = last_boxes
                        missing_run += 1
                        tracked_fallback_frames += 1
                    else:
                        last_boxes = []
                        unblurred_frames += 1

                    for box in boxes:
                        self._blur_box(frame, box)
                    writer.write(frame)
                    frame_index += 1
                    if progress:
                        progress(frame_index, video.frame_count)
        except Exception:
            capture.release()
            writer.release()
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            capture.release()
            writer.release()

        if frame_index == 0:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError("匿名化する動画のフレームを読み取れませんでした。")
        temporary_path.replace(output_path)
        return AnonymizationReport(
            output_path=output_path.resolve(),
            frame_count=frame_index,
            detector_frames=detector_frames,
            pose_fallback_frames=pose_fallback_frames,
            tracked_fallback_frames=tracked_fallback_frames,
            unblurred_frames=unblurred_frames,
            output_width=output_width,
            output_height=output_height,
        )

    @staticmethod
    def _pose_face_box(frame: PoseFrame | None, width: int, height: int) -> Box | None:
        if frame is None:
            return None
        head = [
            item
            for item in frame.landmarks
            if item.index <= 10 and min(item.visibility, item.presence) >= 0.45
        ]
        if len(head) < 3:
            return None
        x_values = [item.x * width for item in head]
        y_values = [item.y * height for item in head]
        center_x = (min(x_values) + max(x_values)) / 2.0
        center_y = (min(y_values) + max(y_values)) / 2.0
        box_width = max(40.0, (max(x_values) - min(x_values)) * 2.4)
        box_height = max(50.0, (max(y_values) - min(y_values)) * 2.8)
        return FaceAnonymizer._clip_box(
            (
                round(center_x - box_width / 2),
                round(center_y - box_height / 2),
                round(box_width),
                round(box_height),
            ),
            width,
            height,
        )

    @staticmethod
    def _expand_box(box: Box, width: int, height: int) -> Box:
        x, y, box_width, box_height = box
        margin_x = round(box_width * 0.30)
        margin_y = round(box_height * 0.40)
        return FaceAnonymizer._clip_box(
            (x - margin_x, y - margin_y, box_width + 2 * margin_x, box_height + 2 * margin_y),
            width,
            height,
        )

    @staticmethod
    def _scale_box(box: Box, scale: float) -> Box:
        return tuple(round(value * scale) for value in box)

    @staticmethod
    def _clip_box(box: Box, width: int, height: int) -> Box:
        x, y, box_width, box_height = box
        left = max(0, min(width - 1, x))
        top = max(0, min(height - 1, y))
        right = max(left + 1, min(width, x + box_width))
        bottom = max(top + 1, min(height, y + box_height))
        return left, top, right - left, bottom - top

    @staticmethod
    def _blur_box(frame, box: Box) -> None:
        import cv2

        x, y, width, height = box
        region = frame[y : y + height, x : x + width]
        if region.size == 0:
            return
        sigma = max(14.0, min(width, height) / 4.0)
        frame[y : y + height, x : x + width] = cv2.GaussianBlur(
            region, (0, 0), sigmaX=sigma, sigmaY=sigma
        )

    @staticmethod
    def _intersection_over_union(first: Box, second: Box) -> float:
        ax, ay, aw, ah = first
        bx, by, bw, bh = second
        intersection_width = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        intersection_height = max(0, min(ay + ah, by + bh) - max(ay, by))
        intersection = intersection_width * intersection_height
        union = aw * ah + bw * bh - intersection
        return intersection / union if union else 0.0
