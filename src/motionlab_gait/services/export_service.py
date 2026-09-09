from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from motionlab_gait.analysis.normal_reference import normal_reference
from motionlab_gait.domain.models import Patient, VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore


def _safe_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


class ResearchExportService:
    def __init__(self, landmark_store: LandmarkStore | None = None) -> None:
        self.landmark_store = landmark_store or LandmarkStore()

    def export_csv_bundle(self, destination: Path, patient: Patient, video: VideoRecord) -> Path:
        if video.result_path is None or video.pose_path is None:
            raise ValueError("解析済み動画を選択してください。")
        destination.mkdir(parents=True, exist_ok=True)
        with video.result_path.open("r", encoding="utf-8") as source:
            result = json.load(source)

        self._write_rows(
            destination / "session.csv",
            ("field", "value"),
            (
                ("patient_code", _safe_cell(patient.patient_code)),
                ("display_name", _safe_cell(patient.name)),
                ("video_id", video.id),
                ("recorded_or_imported_at", video.imported_at.isoformat()),
                ("walking_condition", video.walking_condition),
                ("affected_side", video.affected_side),
                ("orthosis", _safe_cell(video.orthosis)),
                ("walking_aid", _safe_cell(video.walking_aid)),
                ("analysis_version", result.get("analysis_version", "")),
                ("quality_grade", result.get("quality", {}).get("grade", "")),
            ),
        )
        self._write_rows(
            destination / "metrics.csv",
            ("name", "value", "unit", "confidence", "note"),
            (
                (
                    item.get("name"),
                    item.get("value"),
                    item.get("unit"),
                    item.get("confidence"),
                    _safe_cell(item.get("note", "")),
                )
                for item in result.get("temporal_metrics", {}).get("values", [])
            ),
        )
        self._write_rows(
            destination / "events.csv",
            ("event_type", "side", "timestamp_ms", "frame_index", "confidence", "source"),
            (
                (
                    item.get("event_type"),
                    item.get("side"),
                    item.get("timestamp_ms"),
                    item.get("frame_index"),
                    item.get("confidence"),
                    item.get("source"),
                )
                for item in result.get("events", [])
            ),
        )
        self._write_rows(
            destination / "joint_angles.csv",
            ("timestamp_ms", "cycle_percent", "side", "joint", "angle_degrees", "confidence"),
            (
                (
                    item.get("timestamp_ms"),
                    item.get("cycle_percent"),
                    item.get("side"),
                    item.get("joint"),
                    item.get("angle_degrees"),
                    item.get("confidence"),
                )
                for item in result.get("angles", [])
            ),
        )
        self._export_landmarks(destination / "raw_landmarks.csv", video.pose_path)
        if video.processed_pose_path:
            self._export_landmarks(
                destination / "processed_landmarks.csv", video.processed_pose_path
            )
        shutil.copy2(video.result_path, destination / "analysis.json")
        return destination.resolve()

    def _export_landmarks(self, path: Path, pose_path: Path) -> None:
        timeline = self.landmark_store.read(pose_path)
        rows = (
            (
                frame.frame_index,
                frame.timestamp_ms,
                landmark.index,
                landmark.name,
                landmark.x,
                landmark.y,
                landmark.z,
                landmark.visibility,
                landmark.presence,
                landmark.world_x,
                landmark.world_y,
                landmark.world_z,
                landmark.interpolated,
                landmark.outlier_replaced,
            )
            for frame in timeline.frames
            for landmark in frame.landmarks
        )
        self._write_rows(
            path,
            (
                "frame_index",
                "timestamp_ms",
                "landmark_index",
                "landmark_name",
                "x",
                "y",
                "z",
                "visibility",
                "presence",
                "world_x",
                "world_y",
                "world_z",
                "interpolated",
                "outlier_replaced",
            ),
            rows,
        )

    @staticmethod
    def _write_rows(path: Path, header: tuple[str, ...], rows) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(header)
                writer.writerows(rows)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class PdfReportService:
    def export(self, path: Path, patient: Patient, video: VideoRecord) -> Path:
        if video.result_path is None:
            raise ValueError("解析済み動画を選択してください。")
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QFont, QPageSize, QPainter, QPdfWriter

        with video.result_path.open("r", encoding="utf-8") as source:
            result = json.load(source)
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setResolution(120)
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("PDFを作成できませんでした。")

        width = writer.width()
        margin = 70
        y = 85

        def text(value: str, size: int = 10, bold: bool = False, height: int = 32) -> None:
            nonlocal y
            painter.setFont(
                QFont("Yu Gothic", size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
            )
            painter.drawText(
                QRectF(margin, y, width - margin * 2, height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                value,
            )
            y += height

        text("MotionLab Gait  歩行解析レポート", 18, True, 48)
        text("研究・評価用 / 診断支援ではありません", 10, True, 38)
        text(f"患者ID: {_safe_cell(patient.patient_code)}")
        text(f"表示名: {_safe_cell(patient.name) or '未登録'}")
        text(f"解析日時: {result.get('created_at', '')}")
        text(f"動画: {_safe_cell(video.original_name)}")
        text(
            f"条件: {video.walking_condition} / 患側: {video.affected_side} / "
            f"装具: {_safe_cell(video.orthosis)} / 補助具: {_safe_cell(video.walking_aid)}"
        )
        quality = result.get("quality", {})
        text(
            f"品質: {quality.get('grade', '—')} ({quality.get('score', 0):.0f}/100)  "
            f"進行方向: {result.get('direction', 'unknown')}",
            13,
            True,
            42,
        )
        viewpoint = result.get("viewpoint", {})
        if viewpoint:
            start_ms = viewpoint.get("analysis_start_ms")
            end_ms = viewpoint.get("analysis_end_ms")
            interval = (
                f" / 採用区間 {float(start_ms) / 1000:.1f}–{float(end_ms) / 1000:.1f}秒"
                if start_ms is not None and end_ms is not None
                else ""
            )
            text(f"撮影面: {viewpoint.get('classification', 'unknown')}{interval}")
        text("主要指標", 14, True, 40)
        for item in result.get("temporal_metrics", {}).get("values", []):
            if item.get("name") not in {
                "step_time",
                "stride_time",
                "stance_percent",
                "swing_percent",
                "cadence",
                "walking_speed",
                "stride_time_symmetry_index",
                "stance_time_symmetry_index",
            }:
                continue
            value = item.get("value")
            shown = "算出不可" if value is None else f"{float(value):.3f} {item.get('unit', '')}"
            confidence = float(item.get("confidence", 0)) * 100
            text(f"• {item.get('name')}: {shown}  (信頼度 {confidence:.0f}%)")
        representative = self._representative_image(video, result)
        if representative is not None:
            text("代表フレーム（匿名化コピーがある場合は匿名化済み）", 11, True, 35)
            available_width = width - margin * 2
            shown = representative.scaled(
                available_width,
                max(100, writer.height() - y - margin),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage(QRectF(margin, y, shown.width(), shown.height()), shown)

        writer.newPage()
        y = 85
        text("膝関節屈曲（歩行周期正規化中央値＋成人参考帯）", 16, True, 45)
        self._draw_angle_chart(
            painter,
            result.get("angles", []),
            "knee_flexion",
            "膝関節屈曲",
            margin,
            y,
            width - margin * 2,
            230,
        )
        y += 250
        text("注意事項・限界", 16, True, 45)
        for message in (*result.get("warnings", []), *result.get("limitations", [])):
            text(f"• {message}", 10, False, 58)
        text("解析方法", 14, True, 40)
        text(f"解析バージョン: {result.get('analysis_version', '')}")
        text("IC/TO: 股関節相対の踵・足趾軌跡極値と時間制約による自動推定", 10, False, 45)
        text("左右差指標: |左−右| / 左右平均 × 100（0%が左右同等）", 10, False, 45)
        text("速度: 既知距離と計測区間が入力された場合のみ算出", 10, False, 45)
        text("観察された特徴", 14, True, 40)
        for message in result.get("observed_features", []):
            text(f"• {message}", 10, False, 45)
        painter.end()
        return path.resolve()

    @staticmethod
    def _representative_image(video: VideoRecord, result: dict[str, object]):
        import cv2
        from PySide6.QtGui import QImage

        source = (
            video.anonymized_video_path
            if video.anonymized_video_path and video.anonymized_video_path.is_file()
            else video.stored_path
        )
        capture = cv2.VideoCapture(str(source))
        try:
            if not capture.isOpened():
                return None
            viewpoint = result.get("viewpoint", {})
            start_ms = viewpoint.get("analysis_start_ms")
            end_ms = viewpoint.get("analysis_end_ms")
            position_ms = (
                (float(start_ms) + float(end_ms)) / 2.0
                if start_ms is not None and end_ms is not None
                else video.duration_ms / 2.0
            )
            capture.set(cv2.CAP_PROP_POS_MSEC, position_ms)
            ok, frame = capture.read()
            if not ok:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            return QImage(
                rgb.data,
                width,
                height,
                width * channels,
                QImage.Format.Format_RGB888,
            ).copy()
        finally:
            capture.release()

    @staticmethod
    def _draw_angle_chart(painter, angles, joint, label, x, y, width, height) -> None:
        from collections import defaultdict
        from statistics import median

        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QPen, QPolygonF

        buckets = defaultdict(list)
        for point in angles:
            if (
                point.get("joint") == joint
                and point.get("cycle_percent") is not None
                and float(point.get("confidence", 0.0)) >= 0.5
            ):
                key = (str(point.get("side")), round(float(point["cycle_percent"])))
                buckets[key].append(float(point["angle_degrees"]))
        series = {
            side: [
                (percent, median(values))
                for (item_side, percent), values in sorted(buckets.items())
                if item_side == side
            ]
            for side in ("left", "right")
        }
        reference = normal_reference(joint)
        values = [value for items in series.values() for _, value in items]
        values.extend(value for _, _, low, high in reference for value in (low, high))
        painter.setFont(QFont("Yu Gothic", 9))
        painter.drawText(QRectF(x, y, width, 24), label)
        plot = QRectF(x + 45, y + 27, width - 60, height - 42)
        painter.setPen(QPen(QColor("#AAB7BE"), 1))
        painter.drawRect(plot)
        if not any(series.values()):
            painter.drawText(plot, "算出不可")
            return
        minimum, maximum = min(values), max(values)
        if maximum - minimum < 1.0:
            minimum -= 1.0
            maximum += 1.0
        def chart_point(percent: float, value: float) -> QPointF:
            return QPointF(
                plot.left() + percent / 100.0 * plot.width(),
                plot.bottom() - (value - minimum) / (maximum - minimum) * plot.height(),
            )

        band = QPolygonF(
            [chart_point(percent, high) for percent, _, _, high in reference]
            + [chart_point(percent, low) for percent, _, low, _ in reversed(reference)]
        )
        fill = QColor("#A8CFE3")
        fill.setAlpha(70)
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(fill)
        painter.drawPolygon(band)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        reference_line = QPolygonF(
            [chart_point(percent, mean_value) for percent, mean_value, _, _ in reference]
        )
        painter.setPen(QPen(QColor("#718096"), 1, Qt.PenStyle.DashLine))
        painter.drawPolyline(reference_line)

        for side, color in (("left", "#2A74B8"), ("right", "#D0604C")):
            points = QPolygonF(
                [
                    chart_point(percent, value)
                    for percent, value in series[side]
                ]
            )
            painter.setPen(QPen(QColor(color), 2))
            painter.drawPolyline(points)
        painter.setPen(QPen(QColor("#17242D"), 1))
        painter.drawText(
            QRectF(x, y + height - 18, width, 18), "0%                 50%                 100%"
        )
