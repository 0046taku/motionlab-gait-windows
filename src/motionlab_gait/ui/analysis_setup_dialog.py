from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from motionlab_gait.domain.models import Patient, VideoRecord


class AnalysisSetupDialog(QDialog):
    def __init__(self, video: VideoRecord, patient: Patient, parent=None) -> None:
        super().__init__(parent)
        self.video = video
        self.setWindowTitle("歩行条件と解析設定")
        self.setMinimumWidth(460)

        self.condition_combo = QComboBox()
        for label, value in (
            ("快適歩行", "comfortable"),
            ("速歩", "fast"),
            ("低速歩行", "slow"),
            ("その他", "other"),
        ):
            self.condition_combo.addItem(label, value)
        self.side_combo = QComboBox()
        for label, value in (("なし/不明", "none"), ("左", "left"), ("右", "right")):
            self.side_combo.addItem(label, value)
        self.side_combo.setCurrentIndex(max(0, self.side_combo.findData(patient.affected_side)))
        self.orthosis_combo = QComboBox()
        self.orthosis_combo.addItems(("なし", "AFO", "KAFO", "その他"))
        self.aid_combo = QComboBox()
        self.aid_combo.addItems(("なし", "杖", "歩行器", "平行棒", "その他"))

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.0, 1000.0)
        self.distance_spin.setDecimals(2)
        self.distance_spin.setSuffix(" m")
        self.distance_spin.setSpecialValueText("未設定")
        maximum_seconds = max(0.1, video.duration_ms / 1000.0)
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, maximum_seconds)
        self.start_spin.setDecimals(3)
        self.start_spin.setSuffix(" 秒")
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0.0, maximum_seconds)
        self.end_spin.setValue(maximum_seconds)
        self.end_spin.setDecimals(3)
        self.end_spin.setSuffix(" 秒")
        self.anonymize_check = QCheckBox("解析後に顔をぼかした共有用コピーを作成")
        self.anonymize_check.setChecked(True)

        form = QFormLayout()
        form.addRow("歩行条件", self.condition_combo)
        form.addRow("患側", self.side_combo)
        form.addRow("装具", self.orthosis_combo)
        form.addRow("歩行補助具", self.aid_combo)
        form.addRow("既知の歩行距離", self.distance_spin)
        form.addRow("距離計測 開始", self.start_spin)
        form.addRow("距離計測 終了", self.end_spin)
        note = QLabel(
            "速度は距離を入力した場合のみ算出します。\n"
            "自動の顔ぼかしには見逃しがあり得るため、共有前に必ず目視確認してください。"
        )
        note.setObjectName("muted")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存して解析")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.anonymize_check)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def apply_to(self, video: VideoRecord) -> VideoRecord:
        distance = self.distance_spin.value()
        has_distance = distance > 0
        return replace(
            video,
            walking_condition=str(self.condition_combo.currentData()),
            affected_side=str(self.side_combo.currentData()),
            orthosis=self.orthosis_combo.currentText(),
            walking_aid=self.aid_combo.currentText(),
            known_distance_m=distance if has_distance else None,
            distance_start_ms=round(self.start_spin.value() * 1000) if has_distance else None,
            distance_end_ms=round(self.end_spin.value() * 1000) if has_distance else None,
            anonymize_face=self.anonymize_check.isChecked(),
        )

    def _validate(self) -> None:
        if self.distance_spin.value() > 0 and self.end_spin.value() <= self.start_spin.value():
            QMessageBox.warning(self, "計測区間を確認", "終了時刻を開始時刻より後にしてください。")
            return
        self.accept()
