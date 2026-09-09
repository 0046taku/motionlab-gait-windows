from __future__ import annotations

import json

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore, PoseTimeline
from motionlab_gait.ui.video_player import VideoPlayerWidget


class SynchronizedComparisonWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.baseline_player = VideoPlayerWidget()
        self.followup_player = VideoPlayerWidget()
        self._offsets = (0, 0)
        self._maximum = 0
        self._base_position = 0
        self._elapsed = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)

        videos = QHBoxLayout()
        baseline_layout = QVBoxLayout()
        baseline_layout.addWidget(QLabel("基準"))
        baseline_layout.addWidget(self.baseline_player)
        followup_layout = QVBoxLayout()
        followup_layout.addWidget(QLabel("比較"))
        followup_layout.addWidget(self.followup_player)
        videos.addLayout(baseline_layout, 1)
        videos.addLayout(followup_layout, 1)

        self.play_button = QPushButton("▶ 同期再生")
        self.play_button.clicked.connect(self.toggle)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.seek)
        self.sync_label = QLabel("IC基準同期")
        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.sync_label)
        layout = QVBoxLayout(self)
        layout.addLayout(videos, 1)
        layout.addLayout(controls)

    def load_pair(self, baseline: VideoRecord, followup: VideoRecord) -> None:
        self.pause()
        store = LandmarkStore()
        self.baseline_player.load_video(baseline, self._timeline(store, baseline))
        self.followup_player.load_video(followup, self._timeline(store, followup))
        baseline_events = self._events(baseline)
        followup_events = self._events(followup)
        self.baseline_player.set_events(baseline_events)
        self.followup_player.set_events(followup_events)
        offsets = (self._first_ic(baseline_events), self._first_ic(followup_events))
        self._offsets = offsets
        self._maximum = max(
            0,
            min(baseline.duration_ms - offsets[0], followup.duration_ms - offsets[1]),
        )
        self.slider.setRange(0, self._maximum)
        self.sync_label.setText("最初のICを0秒として同期" if any(offsets) else "動画先頭で同期")
        self.seek(0)
        for player in (self.baseline_player, self.followup_player):
            player.play_button.setEnabled(False)
            player.stop_button.setEnabled(False)

    def toggle(self) -> None:
        if self.timer.isActive():
            self.pause()
            return
        if self.slider.value() >= self._maximum:
            self.seek(0)
        self._base_position = self.slider.value()
        self._elapsed.start()
        self.timer.start()
        self.play_button.setText("Ⅱ 一時停止")

    def pause(self) -> None:
        self.timer.stop()
        self.play_button.setText("▶ 同期再生")

    def seek(self, position: int) -> None:
        position = max(0, min(self._maximum, position))
        self.slider.setValue(position)
        self.baseline_player.seek(self._offsets[0] + position)
        self.followup_player.seek(self._offsets[1] + position)

    def release(self) -> None:
        self.pause()
        self.baseline_player.release()
        self.followup_player.release()

    def _tick(self) -> None:
        position = self._base_position + self._elapsed.elapsed()
        if position >= self._maximum:
            self.seek(self._maximum)
            self.pause()
        else:
            self.seek(position)

    @staticmethod
    def _timeline(store: LandmarkStore, video: VideoRecord) -> PoseTimeline:
        path = video.processed_pose_path or video.pose_path
        return store.read(path) if path and path.is_file() else PoseTimeline([])

    @staticmethod
    def _events(video: VideoRecord) -> list[dict[str, object]]:
        if video.result_path is None or not video.result_path.is_file():
            return []
        with video.result_path.open("r", encoding="utf-8") as source:
            return list(json.load(source).get("events", []))

    @staticmethod
    def _first_ic(events: list[dict[str, object]]) -> int:
        contacts = [int(item["timestamp_ms"]) for item in events if item.get("event_type") == "IC"]
        return min(contacts) if contacts else 0
