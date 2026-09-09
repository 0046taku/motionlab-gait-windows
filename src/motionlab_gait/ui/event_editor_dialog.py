from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from motionlab_gait.analysis.types import GaitEvent


class EventEditorDialog(QDialog):
    def __init__(self, result_path: Path, duration_ms: int, fps: float, parent=None) -> None:
        super().__init__(parent)
        self.duration_ms = duration_ms
        self.fps = fps
        self.setWindowTitle("IC / TOイベントの確認・修正")
        self.resize(650, 600)
        with result_path.open("r", encoding="utf-8") as source:
            result = json.load(source)

        note = QLabel(
            "自動検出は未検証の推定です。動画を確認し、必要な場合だけ時刻を修正してください。"
        )
        note.setObjectName("warningBox")
        note.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("イベント", "側", "時刻（秒）", "自動信頼度"))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        for event in result.get("events", []):
            self._append_row(event)

        add_button = QPushButton("イベントを追加")
        add_button.clicked.connect(lambda: self._append_row({}))
        delete_button = QPushButton("選択行を削除")
        delete_button.clicked.connect(self._delete_selected)
        row = QHBoxLayout()
        row.addWidget(add_button)
        row.addWidget(delete_button)
        row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("修正を保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(self.table, 1)
        layout.addLayout(row)
        layout.addWidget(buttons)

    @property
    def events(self) -> tuple[GaitEvent, ...]:
        events: list[GaitEvent] = []
        for row in range(self.table.rowCount()):
            event_combo = self.table.cellWidget(row, 0)
            side_combo = self.table.cellWidget(row, 1)
            time_spin = self.table.cellWidget(row, 2)
            if not isinstance(event_combo, QComboBox):
                continue
            if not isinstance(side_combo, QComboBox) or not isinstance(time_spin, QDoubleSpinBox):
                continue
            timestamp_ms = round(time_spin.value() * 1000)
            events.append(
                GaitEvent(
                    event_type=str(event_combo.currentData()),
                    side=str(side_combo.currentData()),
                    timestamp_ms=timestamp_ms,
                    frame_index=round(timestamp_ms * self.fps / 1000.0),
                    confidence=0.5,
                    source="manual",
                )
            )
        return tuple(sorted(events, key=lambda item: item.timestamp_ms))

    def _append_row(self, event: dict[str, object]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        event_combo = QComboBox()
        event_combo.addItem("IC（初期接地）", "IC")
        event_combo.addItem("TO（足趾離地）", "TO")
        event_combo.setCurrentIndex(max(0, event_combo.findData(event.get("event_type", "IC"))))
        side_combo = QComboBox()
        side_combo.addItem("左", "left")
        side_combo.addItem("右", "right")
        side_combo.setCurrentIndex(max(0, side_combo.findData(event.get("side", "left"))))
        time_spin = QDoubleSpinBox()
        time_spin.setRange(0.0, self.duration_ms / 1000.0)
        time_spin.setDecimals(3)
        time_spin.setValue(float(event.get("timestamp_ms", 0)) / 1000.0)
        confidence = float(event.get("confidence", 0.0))
        self.table.setCellWidget(row, 0, event_combo)
        self.table.setCellWidget(row, 1, side_combo)
        self.table.setCellWidget(row, 2, time_spin)
        self.table.setItem(row, 3, QTableWidgetItem(f"{confidence * 100:.0f}%"))

    def _delete_selected(self) -> None:
        rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
