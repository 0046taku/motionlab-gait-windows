from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from motionlab_gait.analysis.normal_reference import REFERENCE_LABEL, normal_reference

METRIC_LABELS = {
    "step_time": "ステップ時間",
    "stride_time": "ストライド時間",
    "stance_time": "立脚時間",
    "swing_time": "遊脚時間",
    "stance_percent": "立脚期",
    "swing_percent": "遊脚期",
    "cadence": "ケイデンス",
    "walking_speed": "歩行速度",
    "left_stride_time": "左ストライド時間",
    "right_stride_time": "右ストライド時間",
    "stride_time_symmetry_index": "ストライド時間 左右差",
    "left_stance_time": "左立脚時間",
    "right_stance_time": "右立脚時間",
    "stance_time_symmetry_index": "立脚時間 左右差",
}

JOINT_LABELS = {
    "hip_flexion": "股関節屈曲",
    "knee_flexion": "膝関節屈曲",
    "ankle_dorsiflexion": "足関節背屈",
}

JOINT_SELECTOR_LABELS = {
    "hip_flexion": "股関節",
    "knee_flexion": "膝関節",
    "ankle_dorsiflexion": "足関節",
}

CORE_METRICS = {
    "stride_time",
    "stance_percent",
    "swing_percent",
    "cadence",
    "stance_time_symmetry_index",
}


class AnalysisResultsWidget(QWidget):
    edit_events_requested = Signal()
    export_pdf_requested = Signal()
    export_csv_requested = Signal()
    anonymize_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._result: dict[str, object] | None = None
        self._research_mode = False

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 8, 8)
        layout.setSpacing(10)

        self.empty_label = QLabel("Pose解析が完了すると、品質・時間指標・関節角度を表示します。")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("resultCard")
        summary_layout = QGridLayout(self.summary_frame)
        self.quality_label = QLabel("—")
        self.quality_label.setObjectName("qualityGrade")
        self.direction_label = QLabel("—")
        self.cycle_label = QLabel("—")
        self.viewpoint_label = QLabel("—")
        summary_layout.addWidget(QLabel("撮影・Pose品質"), 0, 0)
        summary_layout.addWidget(QLabel("進行方向"), 0, 1)
        summary_layout.addWidget(QLabel("解析周期"), 0, 2)
        summary_layout.addWidget(QLabel("撮影面・採用区間"), 0, 3)
        summary_layout.addWidget(self.quality_label, 1, 0)
        summary_layout.addWidget(self.direction_label, 1, 1)
        summary_layout.addWidget(self.cycle_label, 1, 2)
        summary_layout.addWidget(self.viewpoint_label, 1, 3)
        layout.addWidget(self.summary_frame)

        self.warning_label = QLabel()
        self.warning_label.setObjectName("warningBox")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

        metric_title = QLabel("主要指標（必要最小限）")
        metric_title.setObjectName("sectionTitle")
        layout.addWidget(metric_title)
        self.metric_table = QTableWidget(0, 4)
        self.metric_table.setHorizontalHeaderLabels(("指標", "値", "信頼度", "定義・注記"))
        self.metric_table.horizontalHeader().setStretchLastSection(True)
        self.metric_table.verticalHeader().setVisible(False)
        self.metric_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metric_table.setMinimumHeight(280)
        layout.addWidget(self.metric_table)

        chart_header = QHBoxLayout()
        chart_title = QLabel("歩行周期で正規化した関節角度")
        chart_title.setObjectName("sectionTitle")
        self.joint_combo = QComboBox()
        for key, label in JOINT_SELECTOR_LABELS.items():
            self.joint_combo.addItem(label, key)
        self.joint_combo.setCurrentIndex(self.joint_combo.findData("knee_flexion"))
        self.joint_combo.currentIndexChanged.connect(self._update_chart)
        self.reference_checkbox = QCheckBox("参考波形")
        self.reference_checkbox.setChecked(False)
        self.reference_checkbox.toggled.connect(self._reference_toggled)
        self.raw_compare_checkbox = QCheckBox("Raw / Filtered比較（Debug）")
        self.raw_compare_checkbox.setChecked(False)
        self.raw_compare_checkbox.toggled.connect(self._update_chart)
        chart_header.addWidget(chart_title, 1)
        chart_header.addWidget(self.joint_combo)
        chart_header.addWidget(self.reference_checkbox)
        chart_header.addWidget(self.raw_compare_checkbox)
        layout.addLayout(chart_header)

        self.chart = QChart()
        self.chart.legend().setVisible(True)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(300)
        layout.addWidget(self.chart_view)
        self.joint_quality_label = QLabel("測定品質：—")
        self.joint_quality_label.setObjectName("qualityGrade")
        self.joint_quality_label.setWordWrap(True)
        layout.addWidget(self.joint_quality_label)
        self.reference_note = QLabel(REFERENCE_LABEL)
        self.reference_note.setObjectName("muted")
        self.reference_note.setWordWrap(True)
        layout.addWidget(self.reference_note)

        findings_title = QLabel("観察された特徴")
        findings_title.setObjectName("sectionTitle")
        self.findings_label = QLabel()
        self.findings_label.setWordWrap(True)
        checks_title = QLabel("確認候補（原因の断定ではありません）")
        checks_title.setObjectName("sectionTitle")
        self.checks_label = QLabel()
        self.checks_label.setWordWrap(True)
        self.checks_label.setObjectName("hypothesisBox")
        layout.addWidget(findings_title)
        layout.addWidget(self.findings_label)
        layout.addWidget(checks_title)
        layout.addWidget(self.checks_label)
        self.findings_widgets = (
            findings_title,
            self.findings_label,
            checks_title,
            self.checks_label,
        )

        action_row = QHBoxLayout()
        self.edit_button = QPushButton("イベントを確認・修正")
        self.edit_button.clicked.connect(self.edit_events_requested)
        self.anonymize_button = QPushButton("顔をぼかしたコピーを作成")
        self.anonymize_button.clicked.connect(self.anonymize_requested)
        self.csv_button = QPushButton("CSV出力")
        self.csv_button.clicked.connect(self.export_csv_requested)
        self.pdf_button = QPushButton("PDFレポート")
        self.pdf_button.clicked.connect(self.export_pdf_requested)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.anonymize_button)
        action_row.addStretch(1)
        action_row.addWidget(self.csv_button)
        action_row.addWidget(self.pdf_button)
        layout.addLayout(action_row)

        self.research_button = QPushButton("研究用データ詳細を表示")
        self.research_button.setCheckable(True)
        self.research_button.toggled.connect(self._toggle_research)
        self.research_text = QPlainTextEdit()
        self.research_text.setReadOnly(True)
        self.research_text.setVisible(False)
        self.research_text.setMinimumHeight(240)
        layout.addWidget(self.research_button)
        layout.addWidget(self.research_text)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.clear()

    def clear(self) -> None:
        self._result = None
        self.empty_label.setVisible(True)
        for widget in (
            self.summary_frame,
            self.warning_label,
            self.metric_table,
            self.chart_view,
            self.joint_combo,
            self.reference_checkbox,
            self.raw_compare_checkbox,
            self.joint_quality_label,
            self.reference_note,
            self.edit_button,
            self.anonymize_button,
            self.csv_button,
            self.pdf_button,
            self.research_button,
            self.research_text,
            *self.findings_widgets,
        ):
            widget.setVisible(False)
        self.research_button.setChecked(False)

    def load_path(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as source:
            result = json.load(source)
        if result.get("schema") != "motionlab.gait-analysis.v1":
            raise ValueError("未対応の解析結果形式です。")
        self.load_result(result)

    def load_result(self, result: dict[str, object]) -> None:
        self._result = result
        self.empty_label.setVisible(False)
        for widget in (
            self.summary_frame,
            self.warning_label,
            self.metric_table,
            self.chart_view,
            self.joint_combo,
            self.reference_checkbox,
            self.joint_quality_label,
            self.edit_button,
            self.anonymize_button,
            self.csv_button,
            self.pdf_button,
        ):
            widget.setVisible(True)
        self.csv_button.setVisible(self._research_mode)
        self.research_button.setVisible(self._research_mode)
        self.joint_combo.setVisible(True)
        self.raw_compare_checkbox.setVisible(self._research_mode)
        self.reference_note.setVisible(self.reference_checkbox.isChecked())
        for widget in self.findings_widgets:
            widget.setVisible(self._research_mode)

        quality = result.get("quality", {})
        grade = quality.get("grade", "—")
        score = quality.get("score", 0)
        self.quality_label.setText(f"{grade}  ({score:.0f}/100)")
        direction = {"left": "← 左", "right": "右 →", "unknown": "判定困難"}.get(
            str(result.get("direction")), "—"
        )
        self.direction_label.setText(direction)
        temporal = result.get("temporal_metrics", {})
        complete_cycle_count = int(temporal.get("left_cycle_count", 0)) + int(
            temporal.get("right_cycle_count", 0)
        )
        self.cycle_label.setText(f"{complete_cycle_count} 完全周期")
        viewpoint = result.get("viewpoint", {})
        classification = str(viewpoint.get("classification", "unavailable"))
        viewpoint_name = {
            "sagittal": "矢状面",
            "mixed": "混在（矢状面のみ採用）",
            "frontal_or_oblique": "前額面・斜め",
            "insufficient": "判定不可",
        }.get(classification, "未判定・再解析推奨")
        start_ms = viewpoint.get("analysis_start_ms")
        end_ms = viewpoint.get("analysis_end_ms")
        interval = (
            f"\n{float(start_ms) / 1000:.1f}–{float(end_ms) / 1000:.1f}秒"
            if start_ms is not None and end_ms is not None
            else ""
        )
        self.viewpoint_label.setText(f"{viewpoint_name}{interval}")
        reference_allowed = bool(viewpoint.get("analysis_supported", False))
        self.reference_checkbox.setEnabled(reference_allowed)
        self.reference_checkbox.setToolTip(
            "矢状面解析が成立した場合だけ表示できます。"
            if not reference_allowed
            else REFERENCE_LABEL
        )
        warnings = [*result.get("warnings", []), *result.get("limitations", [])]
        if not viewpoint:
            warnings.insert(0, "旧解析結果です。撮影面判定を適用するため再解析してください。")
        self.warning_label.setText("\n".join(f"• {message}" for message in warnings))
        self.warning_label.setVisible(bool(warnings))
        self._load_metrics(result)
        self._update_chart()
        self.research_text.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.findings_label.setText(
            "\n".join(f"• {item}" for item in result.get("observed_features", []))
            or "主な特徴は算出できませんでした。"
        )
        self.checks_label.setText(
            "\n".join(f"• {item}" for item in result.get("clinical_check_candidates", []))
            or "追加の確認候補はありません。"
        )

    def set_research_mode(self, enabled: bool) -> None:
        self._research_mode = enabled
        has_result = self._result is not None
        self.csv_button.setVisible(enabled and has_result)
        self.research_button.setVisible(enabled and has_result)
        self.joint_combo.setVisible(has_result)
        self.raw_compare_checkbox.setVisible(enabled and has_result)
        for widget in self.findings_widgets:
            widget.setVisible(enabled and has_result)
        if not enabled:
            self.research_button.setChecked(False)
            self.raw_compare_checkbox.setChecked(False)
        if self._result:
            self._load_metrics(self._result)
            self._update_chart()

    def _load_metrics(self, result: dict[str, object]) -> None:
        temporal = result.get("temporal_metrics", {})
        metrics = temporal.get("values", [])
        if not result.get("viewpoint", {}).get("analysis_supported", False):
            metrics = []
        if not self._research_mode:
            metrics = [item for item in metrics if item.get("name") in CORE_METRICS]
        self.metric_table.setColumnHidden(2, not self._research_mode)
        self.metric_table.setColumnHidden(2, not self._research_mode)
        self.metric_table.setRowCount(len(metrics))
        for row, metric in enumerate(metrics):
            value = metric.get("value")
            value_text = (
                "算出不可" if value is None else f"{float(value):.3f} {metric.get('unit', '')}"
            )
            confidence = float(metric.get("confidence", 0.0))
            cells = (
                METRIC_LABELS.get(metric.get("name"), metric.get("name", "")),
                value_text,
                f"{confidence * 100:.0f}%",
                metric.get("note", ""),
            )
            for column, text in enumerate(cells):
                self.metric_table.setItem(row, column, QTableWidgetItem(str(text)))
        self.metric_table.resizeColumnsToContents()

    def _update_chart(self) -> None:
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)
        if not self._result:
            return
        joint = str(self.joint_combo.currentData())
        joint_quality = self._joint_quality(joint)
        status = str(joint_quality.get("status", "caution"))
        status_label = {"high": "高", "caution": "注意", "difficult": "解析困難"}.get(
            status, "注意"
        )
        quality_warnings = [str(item) for item in joint_quality.get("warnings", [])]
        quality_text = f"測定品質：{status_label}"
        if joint == "ankle_dorsiflexion" and status == "caution":
            quality_text += "（足関節角度は参考値）"
        if quality_warnings:
            quality_text += "\n" + " ".join(quality_warnings)
        self.joint_quality_label.setText(quality_text)
        viewpoint = self._result.get("viewpoint", {})
        if not viewpoint.get("analysis_supported", False):
            self.chart.setTitle("矢状面判定後の再解析が必要です")
            return
        if status == "difficult":
            self.chart.setTitle(f"{JOINT_LABELS.get(joint, joint)} — 解析困難")
            return
        buckets: dict[tuple[str, int], list[float]] = defaultdict(list)
        for point in self._result.get("angles", []):
            if (
                point.get("joint") != joint
                or point.get("cycle_percent") is None
                or float(point.get("confidence", 0.0)) < 0.5
            ):
                continue
            bucket = int(round(float(point["cycle_percent"])))
            buckets[(str(point["side"]), bucket)].append(float(point["angle_degrees"]))
        colors = {"left": "#2A74B8", "right": "#D0604C"}
        affected_side = str(self._result.get("provenance", {}).get("affected_side", "none"))
        labels = {
            "left": "左（麻痺側）" if affected_side == "left" else "左",
            "right": "右（麻痺側）" if affected_side == "right" else "右",
        }
        y_values: list[float] = []
        if self.reference_checkbox.isChecked() and viewpoint.get("analysis_supported", False):
            reference_mean = QLineSeries()
            reference_mean.setName("成人参考（概略）")
            reference_mean.setPen(QPen(QColor("#718096"), 1.5, Qt.PenStyle.DashLine))
            for percent, mean_value, _, _ in normal_reference(joint):
                reference_mean.append(percent, mean_value)
                y_values.append(mean_value)
            self.chart.addSeries(reference_mean)
        if self._research_mode and self.raw_compare_checkbox.isChecked():
            raw_buckets = self._angle_buckets("raw_angles", joint)
            for side in ("left", "right"):
                raw_series = QLineSeries()
                raw_series.setName(f"{labels[side]} Raw")
                raw_series.setPen(QPen(QColor(colors[side]), 1.0, Qt.PenStyle.DotLine))
                for percent in range(101):
                    values = raw_buckets.get((side, percent), [])
                    if values:
                        raw_value = median(values)
                        raw_series.append(percent, raw_value)
                        y_values.append(raw_value)
                self.chart.addSeries(raw_series)
        for side in ("left", "right"):
            series = QLineSeries()
            series.setName(labels[side])
            series.setPen(QPen(QColor(colors[side]), 2.0))
            for percent in range(101):
                values = buckets.get((side, percent), [])
                if values:
                    value = median(values)
                    series.append(percent, value)
                    y_values.append(value)
            self.chart.addSeries(series)
        x_axis = QValueAxis()
        x_axis.setTitleText("歩行周期 (%)")
        x_axis.setRange(0, 100)
        x_axis.setTickCount(6)
        x_axis.setLabelFormat("%.0f")
        y_axis = QValueAxis()
        y_axis.setTitleText("角度 (°)")
        if y_values:
            minimum, maximum, tick_count = self._nice_axis_range(y_values)
            y_axis.setRange(minimum, maximum)
            y_axis.setTickCount(tick_count)
            y_axis.setLabelFormat("%.0f")
            if minimum <= 0.0 <= maximum:
                zero_line = QLineSeries()
                zero_line.setName("0°基準")
                zero_line.setPen(QPen(QColor("#B8C0C8"), 1.0, Qt.PenStyle.DashLine))
                zero_line.append(0.0, 0.0)
                zero_line.append(100.0, 0.0)
                self.chart.addSeries(zero_line)
        self.chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        for series in self.chart.series():
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)
        for series in self.chart.series():
            if series.name() == "0°基準":
                for marker in self.chart.legend().markers(series):
                    marker.setVisible(False)
        self.chart.setTitle(JOINT_LABELS.get(joint, joint))

    def _reference_toggled(self, checked: bool) -> None:
        self.reference_note.setVisible(checked and self._result is not None)
        self._update_chart()

    def _joint_quality(self, joint: str) -> dict[str, object]:
        if not self._result:
            return {}
        for report in self._result.get("joint_quality", []):
            if report.get("joint") == joint:
                return report
        points = [
            point
            for point in self._result.get("angles", [])
            if point.get("joint") == joint and point.get("cycle_percent") is not None
        ]
        return {
            "status": "caution" if points else "difficult",
            "warnings": ("旧解析結果です。関節別品質を得るには再解析してください。",),
        }

    def _angle_buckets(
        self, source_key: str, joint: str
    ) -> dict[tuple[str, int], list[float]]:
        buckets: dict[tuple[str, int], list[float]] = defaultdict(list)
        if not self._result:
            return buckets
        for point in self._result.get(source_key, []):
            if (
                point.get("joint") != joint
                or point.get("cycle_percent") is None
                or float(point.get("confidence", 0.0)) < 0.5
            ):
                continue
            bucket = int(round(float(point["cycle_percent"])))
            buckets[(str(point["side"]), bucket)].append(float(point["angle_degrees"]))
        return buckets

    @staticmethod
    def _nice_axis_range(values: list[float]) -> tuple[float, float, int]:
        minimum = min(values)
        maximum = max(values)
        span = max(maximum - minimum, 10.0)
        raw_step = span / 4.0
        magnitude = 10.0 ** math.floor(math.log10(raw_step))
        normalized = raw_step / magnitude
        nice_factor = 1.0 if normalized <= 1.0 else 2.0 if normalized <= 2.0 else 5.0
        step = nice_factor * magnitude
        lower = math.floor(minimum / step) * step
        upper = math.ceil(maximum / step) * step
        if upper <= lower:
            upper = lower + step
        tick_count = int(round((upper - lower) / step)) + 1
        return lower, upper, max(2, tick_count)

    def _toggle_research(self, checked: bool) -> None:
        self.research_text.setVisible(checked)
        self.research_button.setText(
            "研究用データ詳細を隠す" if checked else "研究用データ詳細を表示"
        )
