from __future__ import annotations

import math

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.overlay.renderer import SkeletonOverlayRenderer
from motionlab_gait.persistence.landmark_store import PoseTimeline


class EventSlider(QSlider):
    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._events: list[dict[str, object]] = []

    def set_events(self, events: list[dict[str, object]]) -> None:
        self._events = events
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._events or self.maximum() <= self.minimum():
            return
        painter = QPainter(self)
        for item in self._events:
            timestamp = int(item.get("timestamp_ms", 0))
            fraction = (timestamp - self.minimum()) / (self.maximum() - self.minimum())
            x = round(8 + fraction * max(1, self.width() - 16))
            color = QColor("#2A74B8" if item.get("side") == "left" else "#D0604C")
            painter.setPen(QPen(color, 2))
            top = 1 if item.get("event_type") == "IC" else self.height() - 7
            painter.drawLine(x, top, x, top + 6)


class VideoPlayerWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._capture: cv2.VideoCapture | None = None
        self._video: VideoRecord | None = None
        self._timeline = PoseTimeline([])
        self._overlay = SkeletonOverlayRenderer()
        self._source_pixmap: QPixmap | None = None
        self._resume_after_seek = False
        self._events: list[dict[str, object]] = []

        self.video_label = QLabel("患者を選び、歩行動画を読み込んでください")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet(
            "background:#132127; color:#B9C8CF; border-radius:8px; font-size:15px;"
        )
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.play_button = QPushButton("▶ 再生")
        self.play_button.clicked.connect(self.toggle_playback)
        self.stop_button = QPushButton("■ 停止")
        self.stop_button.clicked.connect(self.stop)
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.previous_frame_button = QPushButton("◀ 1F")
        self.previous_frame_button.clicked.connect(lambda: self._step_frame(-1))
        self.next_frame_button = QPushButton("1F ▶")
        self.next_frame_button.clicked.connect(lambda: self._step_frame(1))
        self.speed_combo = QComboBox()
        for label, speed in (("0.25×", 0.25), ("0.5×", 0.5), ("1.0×", 1.0)):
            self.speed_combo.addItem(label, speed)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self._update_timer_interval)

        self.position_slider = EventSlider()
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._seek_started)
        self.position_slider.sliderMoved.connect(self.seek)
        self.position_slider.sliderReleased.connect(self._seek_finished)

        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(155)
        self.pose_label = QLabel("Skeleton: 未解析")
        self.pose_label.setObjectName("muted")
        self.event_label = QLabel("IC/TO: 未解析")
        self.event_label.setObjectName("muted")
        self.source_combo = QComboBox()
        self.source_combo.addItem("元動画", "original")
        self.source_combo.setEnabled(False)
        self.source_combo.currentIndexChanged.connect(self._source_changed)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.previous_frame_button)
        controls.addWidget(self.next_frame_button)
        controls.addWidget(self.speed_combo)
        controls.addWidget(self.source_combo)
        controls.addWidget(self.position_slider, 1)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_label, 1)
        layout.addLayout(controls)
        layout.addWidget(self.pose_label)
        layout.addWidget(self.event_label)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._next_frame)

    def load_video(self, video: VideoRecord, timeline: PoseTimeline | None = None) -> None:
        self.release()
        self._video = video
        self._timeline = timeline or PoseTimeline([])
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("元動画", "original")
        if video.anonymized_video_path and video.anonymized_video_path.is_file():
            self.source_combo.addItem("顔ぼかしコピー", "anonymized")
        self.source_combo.setCurrentIndex(self.source_combo.count() - 1)
        self.source_combo.setEnabled(self.source_combo.count() > 1)
        self.source_combo.blockSignals(False)
        selected_path = (
            video.anonymized_video_path
            if video.anonymized_video_path and video.anonymized_video_path.is_file()
            else video.stored_path
        )
        self._open_video_path(selected_path)

    def _open_video_path(self, path) -> None:
        if self._capture is not None:
            self._capture.release()
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("保存動画を再生用に開けませんでした。")
        self._capture = capture
        if self._video is None:
            return
        video = self._video
        self._update_timer_interval()
        self.position_slider.setRange(0, max(1, video.duration_ms))
        self.play_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.pose_label.setText(
            f"Skeleton: {len(self._timeline):,}フレーム"
            if len(self._timeline)
            else "Skeleton: 未解析"
        )
        self.seek(0)

    def set_events(self, events: list[dict[str, object]]) -> None:
        self._events = sorted(events, key=lambda item: int(item.get("timestamp_ms", 0)))
        self.position_slider.set_events(self._events)
        self.event_label.setText(
            f"IC/TO: {len(self._events)}件（青=左 / 赤=右）" if self._events else "IC/TO: 未検出"
        )

    def _source_changed(self) -> None:
        if self._video is None:
            return
        self.pause()
        path = (
            self._video.anonymized_video_path
            if self.source_combo.currentData() == "anonymized"
            else self._video.stored_path
        )
        if path:
            self._open_video_path(path)

    def set_timeline(self, timeline: PoseTimeline) -> None:
        self._timeline = timeline
        self.pose_label.setText(f"Skeleton: {len(timeline):,}フレーム")
        if self._video:
            self.seek(self.position_slider.value())

    def toggle_playback(self) -> None:
        if self._capture is None:
            return
        if self._timer.isActive():
            self.pause()
        else:
            if self.position_slider.value() >= self.position_slider.maximum() - 1:
                self.seek(0)
            self._timer.start()
            self.play_button.setText("Ⅱ 一時停止")

    def pause(self) -> None:
        self._timer.stop()
        self.play_button.setText("▶ 再生")

    def stop(self) -> None:
        self.pause()
        if self._video:
            self.seek(0)

    def seek(self, timestamp_ms: int) -> None:
        if self._capture is None or self._video is None:
            return
        timestamp_ms = min(max(0, timestamp_ms), self._video.duration_ms)
        self._capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp_ms))
        ok, frame = self._capture.read()
        if ok:
            actual_timestamp = self._frame_timestamp(timestamp_ms)
            self._display_frame(frame, actual_timestamp)
            self._update_position(actual_timestamp)

    def release(self) -> None:
        self.pause()
        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self._video = None
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("元動画", "original")
        self.source_combo.setEnabled(False)
        self.source_combo.blockSignals(False)
        self.set_events([])

    def _next_frame(self) -> None:
        if self._capture is None or self._video is None:
            self.pause()
            return
        ok, frame = self._capture.read()
        if not ok:
            self.pause()
            self._update_position(self._video.duration_ms)
            return
        timestamp_ms = self._frame_timestamp(self.position_slider.value())
        self._display_frame(frame, timestamp_ms)
        self._update_position(timestamp_ms)

    def _step_frame(self, direction: int) -> None:
        if self._video is None:
            return
        self.pause()
        step_ms = round(1000.0 / max(self._video.fps, 1.0))
        self.seek(self.position_slider.value() + direction * step_ms)

    def _update_timer_interval(self) -> None:
        if self._video is None:
            return
        speed = float(self.speed_combo.currentData() or 1.0)
        self._timer.setInterval(max(1, round(1000.0 / self._video.fps / speed)))

    def _frame_timestamp(self, fallback_ms: int) -> int:
        if self._capture is None or self._video is None:
            return fallback_ms
        decoded = round(float(self._capture.get(cv2.CAP_PROP_POS_MSEC)))
        frame_index = max(0, round(float(self._capture.get(cv2.CAP_PROP_POS_FRAMES))) - 1)
        frame_based = round(frame_index * 1000.0 / self._video.fps)
        if decoded > 0 or frame_index == 0:
            return min(self._video.duration_ms, max(0, decoded))
        return min(self._video.duration_ms, max(0, frame_based))

    def _display_frame(self, frame, timestamp_ms: int) -> None:
        if self._video is None:
            return
        tolerance = max(40, math.ceil(1000.0 / self._video.fps))
        pose_frame = self._timeline.nearest(timestamp_ms, tolerance)
        landmarks = pose_frame.landmarks if pose_frame else ()
        rendered = self._overlay.draw(frame, landmarks)
        rgb = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._fit_pixmap()

    def _fit_pixmap(self) -> None:
        if self._source_pixmap is None:
            return
        self.video_label.setPixmap(
            self._source_pixmap.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_position(self, timestamp_ms: int) -> None:
        if self._video is None:
            return
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(timestamp_ms)
        self.position_slider.blockSignals(False)
        self.time_label.setText(
            f"{self._format_time(timestamp_ms)} / {self._format_time(self._video.duration_ms)}"
        )

    def _seek_started(self) -> None:
        self._resume_after_seek = self._timer.isActive()
        self.pause()

    def _seek_finished(self) -> None:
        self.seek(self.position_slider.value())
        if self._resume_after_seek:
            self._timer.start()
            self.play_button.setText("Ⅱ 一時停止")
        self._resume_after_seek = False

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_pixmap()

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        milliseconds = max(0, milliseconds)
        minutes, remainder = divmod(milliseconds, 60_000)
        seconds, millis = divmod(remainder, 1_000)
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"
