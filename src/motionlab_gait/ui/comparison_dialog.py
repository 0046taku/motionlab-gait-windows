from __future__ import annotations

import json
from collections import defaultdict
from statistics import median

from PySide6.QtCharts import QCategoryAxis, QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.ui.analysis_results_widget import METRIC_LABELS
from motionlab_gait.ui.synchronized_comparison_widget import SynchronizedComparisonWidget


class ComparisonDialog(QDialog):
    def __init__(self, videos: list[VideoRecord], parent=None) -> None:
        super().__init__(parent)
        self.videos = {video.id: video for video in videos if video.result_path}
        self.ordered = sorted(self.videos.values(), key=lambda item: item.imported_at)
        self.setWindowTitle("同一患者の経時比較・Timeline")
        self.resize(1200, 800)

        self.baseline_combo = QComboBox()
        self.followup_combo = QComboBox()
        for video in self.ordered:
            label = f"{video.imported_at.astimezone():%Y/%m/%d %H:%M}  {video.original_name}"
            self.baseline_combo.addItem(label, video.id)
            self.followup_combo.addItem(label, video.id)
        if self.followup_combo.count() > 1:
            self.followup_combo.setCurrentIndex(self.followup_combo.count() - 1)
        form = QFormLayout()
        form.addRow("基準", self.baseline_combo)
        form.addRow("比較", self.followup_combo)
        self.warning_label = QLabel()
        self.warning_label.setObjectName("warningBox")
        self.warning_label.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("指標", "基準", "比較", "変化量"))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        metrics_tab = QWidget()
        metrics_layout = QVBoxLayout(metrics_tab)
        metrics_layout.addWidget(self.table)

        angle_tab = QWidget()
        angle_layout = QVBoxLayout(angle_tab)
        self.angle_combo = QComboBox()
        for label, value in (
            ("左 膝関節屈曲", "left:knee_flexion"),
            ("右 膝関節屈曲", "right:knee_flexion"),
        ):
            self.angle_combo.addItem(label, value)
        self.angle_chart = QChart()
        self.angle_chart_view = QChartView(self.angle_chart)
        self.angle_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        angle_header = QHBoxLayout()
        angle_header.addWidget(QLabel("同じ歩行周期%で重ねて表示"), 1)
        angle_header.addWidget(self.angle_combo)
        angle_layout.addLayout(angle_header)
        angle_layout.addWidget(self.angle_chart_view, 1)

        timeline_tab = QWidget()
        timeline_layout = QVBoxLayout(timeline_tab)
        self.timeline_combo = QComboBox()
        for name in ("cadence", "stance_percent", "stride_time_symmetry_index"):
            self.timeline_combo.addItem(METRIC_LABELS.get(name, name), name)
        self.timeline_chart = QChart()
        self.timeline_chart_view = QChartView(self.timeline_chart)
        self.timeline_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        timeline_layout.addWidget(self.timeline_combo)
        timeline_layout.addWidget(self.timeline_chart_view, 1)

        self.sync_widget = SynchronizedComparisonWidget()
        tabs = QTabWidget()
        tabs.addTab(metrics_tab, "指標")
        tabs.addTab(angle_tab, "関節角度")
        tabs.addTab(timeline_tab, "Timeline")
        tabs.addTab(self.sync_widget, "IC同期動画")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.warning_label)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)
        self.baseline_combo.currentIndexChanged.connect(self._update)
        self.followup_combo.currentIndexChanged.connect(self._update)
        self.angle_combo.currentIndexChanged.connect(self._update_angle_chart)
        self.timeline_combo.currentIndexChanged.connect(self._update_timeline_chart)
        self._update()

    def _update(self) -> None:
        baseline = self.videos.get(str(self.baseline_combo.currentData()))
        followup = self.videos.get(str(self.followup_combo.currentData()))
        if baseline is None or followup is None:
            return
        warnings: list[str] = []
        if baseline.id == followup.id:
            warnings.append("同じ解析が選択されています。")
        for label, first, second in (
            ("歩行条件", baseline.walking_condition, followup.walking_condition),
            ("装具", baseline.orthosis, followup.orthosis),
            ("歩行補助具", baseline.walking_aid, followup.walking_aid),
        ):
            if first != second:
                warnings.append(f"{label}が異なります（{first} / {second}）。")
        for label, video in (("基準", baseline), ("比較", followup)):
            result = self._read_result(video)
            viewpoint = result.get("viewpoint", {})
            if not viewpoint.get("analysis_supported", False):
                warnings.append(f"{label}動画は矢状面解析が成立していません。再解析してください。")
            elif viewpoint.get("classification") == "mixed":
                warnings.append(f"{label}動画は撮影面が混在し、矢状面区間だけを比較しています。")
        if baseline.analysis_version != followup.analysis_version:
            warnings.append("解析バージョンが異なります。両方を再解析して揃えてください。")
        self.warning_label.setText("\n".join(f"• {item}" for item in warnings))
        self.warning_label.setVisible(bool(warnings))
        baseline_metrics = self._metrics(baseline)
        followup_metrics = self._metrics(followup)
        names = [name for name in baseline_metrics if name in followup_metrics]
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            first_value, unit = baseline_metrics[name]
            second_value, _ = followup_metrics[name]
            delta = (
                second_value - first_value
                if first_value is not None and second_value is not None
                else None
            )
            cells = (
                METRIC_LABELS.get(name, name),
                self._format(first_value, unit),
                self._format(second_value, unit),
                self._format(delta, unit, signed=True),
            )
            for column, value in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self._update_angle_chart()
        self._update_timeline_chart()
        self.sync_widget.load_pair(baseline, followup)

    def _update_angle_chart(self) -> None:
        self.angle_chart.removeAllSeries()
        for axis in self.angle_chart.axes():
            self.angle_chart.removeAxis(axis)
        baseline = self.videos.get(str(self.baseline_combo.currentData()))
        followup = self.videos.get(str(self.followup_combo.currentData()))
        if baseline is None or followup is None:
            return
        side, joint = str(self.angle_combo.currentData()).split(":", maxsplit=1)
        for video, label, color in (
            (baseline, "基準", "#2A74B8"),
            (followup, "比較", "#D0604C"),
        ):
            series = QLineSeries()
            series.setName(label)
            series.setColor(QColor(color))
            for percent, angle in self._mean_angle(video, side, joint):
                series.append(percent, angle)
            self.angle_chart.addSeries(series)
        x_axis = QValueAxis()
        x_axis.setRange(0, 100)
        x_axis.setTitleText("歩行周期 (%)")
        y_axis = QValueAxis()
        y_axis.setTitleText("角度 (°)")
        self.angle_chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        self.angle_chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        for series in self.angle_chart.series():
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

    def _update_timeline_chart(self) -> None:
        self.timeline_chart.removeAllSeries()
        for axis in self.timeline_chart.axes():
            self.timeline_chart.removeAxis(axis)
        metric_name = str(self.timeline_combo.currentData())
        series = QLineSeries()
        series.setName(METRIC_LABELS.get(metric_name, metric_name))
        x_axis = QCategoryAxis()
        y_values: list[float] = []
        for index, video in enumerate(self.ordered):
            value = self._metrics(video).get(metric_name, (None, ""))[0]
            if value is None:
                continue
            series.append(index, value)
            y_values.append(value)
            x_axis.append(video.imported_at.astimezone().strftime("%m/%d"), index)
        self.timeline_chart.addSeries(series)
        if not y_values:
            return
        y_axis = QValueAxis()
        span = max(y_values) - min(y_values)
        margin = max(0.1, span * 0.15)
        y_axis.setRange(min(y_values) - margin, max(y_values) + margin)
        self.timeline_chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        self.timeline_chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(x_axis)
        series.attachAxis(y_axis)

    @staticmethod
    def _mean_angle(video: VideoRecord, side: str, joint: str) -> list[tuple[int, float]]:
        if video.result_path is None:
            return []
        with video.result_path.open("r", encoding="utf-8") as source:
            result = json.load(source)
        buckets: dict[int, list[float]] = defaultdict(list)
        for point in result.get("angles", []):
            if (
                point.get("side") == side
                and point.get("joint") == joint
                and point.get("cycle_percent") is not None
                and float(point.get("confidence", 0.0)) >= 0.5
            ):
                buckets[round(float(point["cycle_percent"]))].append(float(point["angle_degrees"]))
        return [(percent, median(values)) for percent, values in sorted(buckets.items())]

    @staticmethod
    def _read_result(video: VideoRecord) -> dict[str, object]:
        if video.result_path is None:
            return {}
        with video.result_path.open("r", encoding="utf-8") as source:
            return json.load(source)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.sync_widget.release()
        super().closeEvent(event)

    @staticmethod
    def _metrics(video: VideoRecord) -> dict[str, tuple[float | None, str]]:
        if video.result_path is None:
            return {}
        with video.result_path.open("r", encoding="utf-8") as source:
            result = json.load(source)
        return {
            str(item["name"]): (
                float(item["value"]) if item.get("value") is not None else None,
                str(item.get("unit", "")),
            )
            for item in result.get("temporal_metrics", {}).get("values", [])
        }

    @staticmethod
    def _format(value: float | None, unit: str, *, signed: bool = False) -> str:
        if value is None:
            return "算出不可"
        number = f"{value:+.3f}" if signed else f"{value:.3f}"
        return f"{number} {unit}".strip()
