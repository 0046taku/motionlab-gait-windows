from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)


class PatientDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("患者登録")
        self.setMinimumWidth(420)

        self.patient_code_edit = QLineEdit()
        self.patient_code_edit.setPlaceholderText("例: PT-001")
        self.patient_code_edit.setMaxLength(64)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("任意。匿名ID運用を推奨")
        self.name_edit.setMaxLength(128)
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("任意。撮影時の注意事項など")
        self.notes_edit.setFixedHeight(90)
        self.side_combo = QComboBox()
        for label, value in (("なし/不明", "none"), ("左", "left"), ("右", "right")):
            self.side_combo.addItem(label, value)
        self.diagnosis_edit = QLineEdit()
        self.diagnosis_edit.setPlaceholderText("任意")
        self.onset_edit = QLineEdit()
        self.onset_edit.setPlaceholderText("任意。YYYY-MM-DD")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.0, 250.0)
        self.height_spin.setDecimals(1)
        self.height_spin.setSuffix(" cm")
        self.height_spin.setSpecialValueText("未入力")

        form = QFormLayout()
        form.addRow("患者ID *", self.patient_code_edit)
        form.addRow("表示名", self.name_edit)
        form.addRow("患側", self.side_combo)
        form.addRow("診断名", self.diagnosis_edit)
        form.addRow("発症日", self.onset_edit)
        form.addRow("身長", self.height_spin)
        form.addRow("メモ", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("登録")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def values(self) -> dict[str, object]:
        height = self.height_spin.value()
        return {
            "patient_code": self.patient_code_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "affected_side": str(self.side_combo.currentData()),
            "diagnosis": self.diagnosis_edit.text().strip(),
            "onset_date": self.onset_edit.text().strip() or None,
            "height_cm": height if height > 0 else None,
        }

    def _validate_and_accept(self) -> None:
        if not self.patient_code_edit.text().strip():
            QMessageBox.warning(self, "入力を確認", "患者IDは必須です。")
            return
        if len(self.notes_edit.toPlainText()) > 2_000:
            QMessageBox.warning(self, "入力を確認", "メモは2000文字以内で入力してください。")
            return
        self.accept()
