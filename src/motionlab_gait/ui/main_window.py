from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from motionlab_gait.config import AppPaths
from motionlab_gait.domain.models import Patient, VideoRecord
from motionlab_gait.persistence.landmark_store import LandmarkStore, PoseTimeline
from motionlab_gait.persistence.patient_repository import (
    DuplicatePatientCodeError,
    PatientRepository,
)
from motionlab_gait.persistence.video_repository import VideoRepository
from motionlab_gait.pose.mediapipe_provider import MediaPipePoseProvider
from motionlab_gait.privacy.face_anonymizer import FaceAnonymizer
from motionlab_gait.services.export_service import PdfReportService, ResearchExportService
from motionlab_gait.services.pose_analysis_service import (
    PoseAnalysisService,
    PoseAnalysisSummary,
)
from motionlab_gait.services.video_service import VideoImportError, VideoService
from motionlab_gait.ui.analysis_results_widget import AnalysisResultsWidget
from motionlab_gait.ui.analysis_setup_dialog import AnalysisSetupDialog
from motionlab_gait.ui.comparison_dialog import ComparisonDialog
from motionlab_gait.ui.event_editor_dialog import EventEditorDialog
from motionlab_gait.ui.patient_dialog import PatientDialog
from motionlab_gait.ui.video_player import VideoPlayerWidget
from motionlab_gait.workers.pose_worker import PoseAnalysisWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        paths: AppPaths,
        patient_repository: PatientRepository,
        video_repository: VideoRepository,
        video_service: VideoService,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.patient_repository = patient_repository
        self.video_repository = video_repository
        self.video_service = video_service
        self.export_service = ResearchExportService()
        self.pdf_service = PdfReportService()
        self.landmark_store = LandmarkStore()
        self.pose_service = PoseAnalysisService(
            model_path=paths.model,
            landmark_root=paths.poses,
            provider_factory=MediaPipePoseProvider,
            landmark_store=self.landmark_store,
            face_anonymizer=FaceAnonymizer(paths.face_model, self.landmark_store),
        )
        self.current_patient: Patient | None = None
        self.current_video: VideoRecord | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: PoseAnalysisWorker | None = None
        self._analysis_video_id: str | None = None
        self._analysis_stage = "pose"

        self.setWindowTitle("MotionLab Gait — Windows")
        self.resize(1380, 860)
        self.setMinimumSize(1050, 700)
        self._build_ui()
        self._build_menu()
        self._refresh_patients()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 14, 18, 18)
        root_layout.setSpacing(12)

        title = QLabel("MotionLab Gait")
        title.setObjectName("appTitle")
        subtitle = QLabel("患者別 歩行動画・定量解析  /  ローカル処理")
        subtitle.setObjectName("muted")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_patient_panel())
        splitter.addWidget(self._build_content_panel())
        splitter.setSizes([300, 1040])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)
        disclaimer = QLabel(
            "研究・評価用の未検証推定です。診断や治療判断は動画・臨床所見と合わせて行ってください。"
        )
        disclaimer.setObjectName("warningBox")
        disclaimer.setWordWrap(True)
        root_layout.addWidget(disclaimer)
        self.setCentralWidget(root)

    def _build_menu(self) -> None:
        settings = QSettings()
        research_enabled = settings.value("research_mode", False, type=bool)
        self.research_action = QAction("Research Mode", self)
        self.research_action.setCheckable(True)
        self.research_action.setChecked(research_enabled)
        self.research_action.toggled.connect(self._research_mode_changed)
        self.menuBar().addMenu("設定").addAction(self.research_action)
        self.results_widget.set_research_mode(research_enabled)

    def _research_mode_changed(self, enabled: bool) -> None:
        QSettings().setValue("research_mode", enabled)
        self.results_widget.set_research_mode(enabled)

    def _build_patient_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sidebar")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)

        label = QLabel("患者")
        label.setObjectName("sectionTitle")
        self.patient_list = QListWidget()
        self.patient_list.currentItemChanged.connect(self._patient_selected)
        self.add_patient_button = QPushButton("＋ 患者を登録")
        self.add_patient_button.setObjectName("primaryButton")
        self.add_patient_button.clicked.connect(self._add_patient)

        layout.addWidget(label)
        layout.addWidget(self.patient_list, 1)
        layout.addWidget(self.add_patient_button)
        return frame

    def _build_content_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("contentCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        self.patient_title = QLabel("患者を選択してください")
        self.patient_title.setObjectName("sectionTitle")
        self.patient_notes = QLabel("左の一覧から患者を選択すると動画を管理できます。")
        self.patient_notes.setObjectName("muted")
        self.patient_notes.setWordWrap(True)
        header_text.addWidget(self.patient_title)
        header_text.addWidget(self.patient_notes)

        self.import_button = QPushButton("歩行動画を読み込む")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import_video)
        self.compare_button = QPushButton("経時比較")
        self.compare_button.setEnabled(False)
        self.compare_button.clicked.connect(self._show_comparison)
        header_row.addLayout(header_text, 1)
        header_row.addWidget(self.compare_button)
        header_row.addWidget(self.import_button)
        layout.addLayout(header_row)

        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        video_list_container = QWidget()
        video_list_layout = QVBoxLayout(video_list_container)
        video_list_layout.setContentsMargins(0, 0, 0, 0)
        video_list_title = QLabel("保存動画")
        video_list_title.setObjectName("sectionTitle")
        self.video_list = QListWidget()
        self.video_list.setMinimumWidth(250)
        self.video_list.currentItemChanged.connect(self._video_selected)
        self.reanalyze_button = QPushButton("Poseを解析 / 再解析")
        self.reanalyze_button.setEnabled(False)
        self.reanalyze_button.clicked.connect(self._reanalyze_current_video)
        video_list_layout.addWidget(video_list_title)
        video_list_layout.addWidget(self.video_list, 1)
        video_list_layout.addWidget(self.reanalyze_button)

        self.video_player = VideoPlayerWidget()
        self.results_widget = AnalysisResultsWidget()
        self.results_widget.edit_events_requested.connect(self._edit_events)
        self.results_widget.export_csv_requested.connect(self._export_csv)
        self.results_widget.export_pdf_requested.connect(self._export_pdf)
        self.results_widget.anonymize_requested.connect(self._create_anonymized_copy)
        self.content_tabs = QTabWidget()
        self.content_tabs.addTab(self.video_player, "動画・Skeleton")
        self.content_tabs.addTab(self.results_widget, "解析結果")
        body_splitter.addWidget(video_list_container)
        body_splitter.addWidget(self.content_tabs)
        body_splitter.setSizes([270, 800])
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        layout.addWidget(body_splitter, 1)

        progress_row = QHBoxLayout()
        self.analysis_status = QLabel("待機中")
        self.analysis_status.setObjectName("muted")
        self.analysis_progress = QProgressBar()
        self.analysis_progress.setVisible(False)
        self.analysis_progress.setMinimumWidth(260)
        progress_row.addWidget(self.analysis_status, 1)
        progress_row.addWidget(self.analysis_progress)
        layout.addLayout(progress_row)
        return frame

    def _refresh_patients(self, select_id: str | None = None) -> None:
        selected_id = select_id or self._item_id(self.patient_list.currentItem())
        self.patient_list.blockSignals(True)
        self.patient_list.clear()
        selected_item: QListWidgetItem | None = None
        for patient in self.patient_repository.list_all():
            item = QListWidgetItem(f"{patient.name or '匿名患者'}\n{patient.patient_code}")
            item.setData(Qt.ItemDataRole.UserRole, patient.id)
            self.patient_list.addItem(item)
            if patient.id == selected_id:
                selected_item = item
        self.patient_list.blockSignals(False)
        if selected_item:
            self.patient_list.setCurrentItem(selected_item)
        elif self.patient_list.count():
            self.patient_list.setCurrentRow(0)
        else:
            self._show_no_patient()

    def _refresh_videos(self, select_id: str | None = None) -> None:
        if self.current_patient is None:
            self.video_list.clear()
            return
        selected_id = select_id or self._item_id(self.video_list.currentItem())
        self.video_list.blockSignals(True)
        self.video_list.clear()
        selected_item: QListWidgetItem | None = None
        patient_videos = self.video_repository.list_for_patient(self.current_patient.id)
        for video in patient_videos:
            imported = video.imported_at.astimezone().strftime("%Y/%m/%d %H:%M")
            status = {
                "pending": "未解析",
                "processing": "解析中",
                "ready": "Pose準備完了",
                "failed": "解析エラー",
            }.get(video.pose_status, video.pose_status)
            item = QListWidgetItem(f"{video.original_name}\n{imported}  •  {status}")
            item.setData(Qt.ItemDataRole.UserRole, video.id)
            self.video_list.addItem(item)
            if video.id == selected_id:
                selected_item = item
        self.video_list.blockSignals(False)
        analyzed_count = sum(
            bool(video.result_path and video.result_path.is_file()) for video in patient_videos
        )
        self.compare_button.setEnabled(analyzed_count >= 2 and not self._analysis_running())
        if selected_item:
            self.video_list.setCurrentItem(selected_item)
        elif self.video_list.count():
            self.video_list.setCurrentRow(0)
        else:
            self.current_video = None
            self.video_player.release()
            self.reanalyze_button.setEnabled(False)

    def _add_patient(self) -> None:
        dialog = PatientDialog(self)
        if dialog.exec() != PatientDialog.DialogCode.Accepted:
            return
        try:
            patient = self.patient_repository.create(**dialog.values)
        except (ValueError, DuplicatePatientCodeError) as error:
            QMessageBox.warning(self, "患者を登録できません", str(error))
            return
        self._refresh_patients(patient.id)

    def _patient_selected(self, current: QListWidgetItem | None) -> None:
        patient_id = self._item_id(current)
        patient = self.patient_repository.get(patient_id) if patient_id else None
        if patient is None:
            self._show_no_patient()
            return
        self.current_patient = patient
        self.current_video = None
        self.patient_title.setText(f"{patient.name or '匿名患者'}  ({patient.patient_code})")
        self.patient_notes.setText(patient.notes or "患者メモなし")
        self.import_button.setEnabled(not self._analysis_running())
        self._refresh_videos()

    def _video_selected(self, current: QListWidgetItem | None) -> None:
        video_id = self._item_id(current)
        video = self.video_repository.get(video_id) if video_id else None
        if video is None:
            self.current_video = None
            self.reanalyze_button.setEnabled(False)
            return
        self.current_video = video
        timeline = self._load_timeline(video)
        try:
            self.video_player.load_video(video, timeline)
        except Exception as error:
            QMessageBox.critical(self, "動画を再生できません", str(error))
        self._load_results(video)
        self.reanalyze_button.setEnabled(not self._analysis_running())
        if video.pose_status == "failed" and video.pose_error:
            self.analysis_status.setText(f"前回の解析エラー: {video.pose_error}")
        elif video.pose_status == "ready":
            self.analysis_status.setText("Pose解析済み。再生・停止・シークでSkeletonが追従します。")
        else:
            self.analysis_status.setText("Pose未解析です。")

    def _import_video(self) -> None:
        if self.current_patient is None:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "歩行動画を選択",
            "",
            "動画 (*.mp4 *.mov *.avi *.mkv *.m4v *.wmv);;すべてのファイル (*.*)",
        )
        if not selected:
            return
        imported_video: VideoRecord | None = None
        try:
            imported_video = self.video_service.import_for_patient(
                Path(selected), self.current_patient.id
            )
            setup_dialog = AnalysisSetupDialog(imported_video, self.current_patient, self)
            if setup_dialog.exec() != AnalysisSetupDialog.DialogCode.Accepted:
                imported_video.stored_path.unlink(missing_ok=True)
                return
            imported_video = setup_dialog.apply_to(imported_video)
            self.video_repository.add(imported_video)
        except (VideoImportError, OSError, RuntimeError) as error:
            if imported_video:
                imported_video.stored_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "動画を読み込めません", str(error))
            return
        self._refresh_videos(imported_video.id)
        self._start_pose_analysis(imported_video)

    def _reanalyze_current_video(self) -> None:
        if self.current_video:
            self.video_player.pause()
            self._start_pose_analysis(self.current_video)

    def _start_pose_analysis(self, video: VideoRecord) -> None:
        if self._analysis_running():
            QMessageBox.information(
                self,
                "解析中",
                "別の動画をPose解析中です。完了までお待ちください。",
            )
            return
        if not self.paths.model.is_file():
            self.video_repository.mark_pose_failed(video.id, "Poseモデルがありません。")
            QMessageBox.critical(
                self,
                "Poseモデルがありません",
                "models\\pose_landmarker_full.task が見つかりません。\n"
                "setup_windows.bat を実行してください。",
            )
            self._refresh_videos(video.id)
            return

        self.video_repository.mark_pose_processing(video.id)
        self._analysis_video_id = video.id
        self._set_analysis_controls(True)
        self.analysis_status.setText(f"Pose解析中: {video.original_name}")
        self.analysis_progress.setRange(0, max(1, video.frame_count))
        self.analysis_progress.setValue(0)
        self.analysis_progress.setVisible(True)

        thread = QThread(self)
        worker = PoseAnalysisWorker(self.pose_service, video)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._pose_progress)
        worker.stage_changed.connect(self._analysis_stage_changed)
        worker.completed.connect(self._pose_completed)
        worker.failed.connect(self._pose_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._pose_thread_finished)
        self._analysis_thread = thread
        self._analysis_worker = worker
        thread.start()
        self._refresh_videos(video.id)

    def _pose_progress(self, current: int, total: int) -> None:
        self.analysis_progress.setMaximum(max(1, total))
        self.analysis_progress.setValue(current)
        labels = {
            "pose": "33点Pose推定中",
            "gait": "歩行指標を計算中",
            "anonymize": "顔の匿名化中",
        }
        self.analysis_status.setText(
            f"{labels.get(self._analysis_stage, '解析中')}: {current:,} / {total:,} フレーム"
        )

    def _analysis_stage_changed(self, stage: str) -> None:
        self._analysis_stage = stage
        messages = {
            "pose": "33点Pose推定を開始しました。",
            "gait": "品質・IC/TO・歩行周期・時間指標・関節角度を計算しています。",
            "anonymize": "共有用の顔ぼかしコピーを作成しています。",
        }
        self.analysis_status.setText(messages.get(stage, "解析中です。"))

    def _pose_completed(self, result: object) -> None:
        if not isinstance(result, PoseAnalysisSummary) or not self._analysis_video_id:
            return
        video_id = self._analysis_video_id
        self.video_repository.mark_pose_ready(video_id, result.output_path)
        self.video_repository.mark_analysis_ready(
            video_id,
            processed_pose_path=result.processed_pose_path,
            result_path=result.result_path,
            quality_grade=result.analysis_result.quality.grade,
            analysis_version=result.analysis_result.analysis_version,
            anonymized_video_path=(
                result.anonymization_report.output_path if result.anonymization_report else None
            ),
        )
        self.analysis_status.setText(
            f"Pose解析完了: {result.frame_count:,}フレーム中 "
            f"{result.detected_frame_count:,}フレームで33点を取得 / "
            f"品質 {result.analysis_result.quality.grade}"
        )
        self.analysis_progress.setValue(self.analysis_progress.maximum())
        self.results_widget.load_result(result.analysis_result.to_dict())
        if result.anonymization_error:
            QMessageBox.warning(
                self,
                "顔の匿名化を完了できませんでした",
                f"Poseと歩行解析は保存済みです。\n匿名化エラー: {result.anonymization_error}",
            )
        elif result.anonymization_report and result.anonymization_report.needs_review:
            QMessageBox.information(
                self,
                "匿名化コピーを確認してください",
                "顔をぼかしたコピーを作成しました。自動顔検出には見逃しがあり得ます。\n"
                "共有・出力前に動画全体を目視確認してください。元動画は確認用に保持しています。",
            )
        self._refresh_videos(video_id)

    def _pose_failed(self, message: str) -> None:
        if self._analysis_video_id:
            self.video_repository.mark_pose_failed(self._analysis_video_id, message)
            self._refresh_videos(self._analysis_video_id)
        self.analysis_status.setText(f"Pose解析エラー: {message}")
        QMessageBox.critical(self, "Pose解析に失敗しました", message)

    def _pose_thread_finished(self) -> None:
        self._analysis_thread = None
        self._analysis_worker = None
        self._analysis_video_id = None
        self._analysis_stage = "pose"
        self.analysis_progress.setVisible(False)
        self._set_analysis_controls(False)

    def _load_timeline(self, video: VideoRecord) -> PoseTimeline:
        pose_path = video.processed_pose_path or video.pose_path
        if video.pose_status != "ready" or not pose_path:
            return PoseTimeline([])
        if not pose_path.is_file():
            self.analysis_status.setText("Poseデータファイルが見つかりません。再解析してください。")
            return PoseTimeline([])
        try:
            return self.landmark_store.read(pose_path)
        except (OSError, ValueError) as error:
            self.analysis_status.setText(f"Poseデータを読み込めません: {error}")
            return PoseTimeline([])

    def _set_analysis_controls(self, running: bool) -> None:
        self.import_button.setEnabled(not running and self.current_patient is not None)
        self.reanalyze_button.setEnabled(not running and self.current_video is not None)
        self.add_patient_button.setEnabled(not running)
        if running:
            self.compare_button.setEnabled(False)

    def _show_comparison(self) -> None:
        if self.current_patient is None:
            return
        videos = [
            video
            for video in self.video_repository.list_for_patient(self.current_patient.id)
            if video.result_path and video.result_path.is_file()
        ]
        if len(videos) < 2:
            QMessageBox.information(self, "経時比較", "解析済み動画が2件以上必要です。")
            return
        ComparisonDialog(videos, self).exec()

    def _edit_events(self) -> None:
        video = self.current_video
        if video is None or video.result_path is None:
            return
        dialog = EventEditorDialog(video.result_path, video.duration_ms, video.fps, self)
        if dialog.exec() != EventEditorDialog.DialogCode.Accepted:
            return
        try:
            result = self.pose_service.gait_engine.apply_manual_events(video, dialog.events)
            self.results_widget.load_result(result)
            self.video_player.set_events(list(result.get("events", [])))
            self.analysis_status.setText("IC/TOの手動修正を保存し、指標を再計算しました。")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "修正を保存できません", str(error))

    def _export_csv(self) -> None:
        if self.current_patient is None or self.current_video is None:
            return
        selected = QFileDialog.getExistingDirectory(self, "CSVデータの保存先を選択")
        if not selected:
            return
        destination = Path(selected) / f"motionlab_{self.current_video.id[:8]}"
        try:
            exported = self.export_service.export_csv_bundle(
                destination, self.current_patient, self.current_video
            )
            QMessageBox.information(self, "CSV出力完了", f"保存先:\n{exported}")
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "CSVを出力できません", str(error))

    def _export_pdf(self) -> None:
        if self.current_patient is None or self.current_video is None:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "PDFレポートの保存先",
            f"MotionLab_{self.current_patient.patient_code}.pdf",
            "PDF (*.pdf)",
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            exported = self.pdf_service.export(path, self.current_patient, self.current_video)
            QMessageBox.information(self, "PDF出力完了", f"保存先:\n{exported}")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(self, "PDFを出力できません", str(error))

    def _create_anonymized_copy(self) -> None:
        video = self.current_video
        if video is None or video.processed_pose_path is None or video.result_path is None:
            QMessageBox.information(self, "顔の匿名化", "先にPose解析を完了してください。")
            return
        self.video_player.pause()
        self._set_analysis_controls(True)
        self.analysis_progress.setRange(0, max(1, video.frame_count))
        self.analysis_progress.setValue(0)
        self.analysis_progress.setVisible(True)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = self.pose_service.face_anonymizer.anonymize(
                video,
                video.processed_pose_path,
                progress=self._anonymization_progress,
            )
            self.video_repository.mark_analysis_ready(
                video.id,
                processed_pose_path=video.processed_pose_path,
                result_path=video.result_path,
                quality_grade=video.quality_grade or "—",
                analysis_version=video.analysis_version,
                anonymized_video_path=report.output_path,
            )
            self._refresh_videos(video.id)
            QMessageBox.information(
                self,
                "匿名化コピーを作成しました",
                f"保存先:\n{report.output_path}\n\n"
                "自動検出には見逃しがあり得ます。共有前に動画全体を目視確認してください。",
            )
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.critical(self, "匿名化できません", str(error))
        finally:
            QApplication.restoreOverrideCursor()
            self.analysis_progress.setVisible(False)
            self._set_analysis_controls(False)

    def _anonymization_progress(self, current: int, total: int) -> None:
        self.analysis_progress.setMaximum(max(1, total))
        self.analysis_progress.setValue(current)
        self.analysis_status.setText(f"顔の匿名化中: {current:,} / {total:,} フレーム")
        QApplication.processEvents()

    def _load_results(self, video: VideoRecord) -> None:
        if not video.result_path or not video.result_path.is_file():
            self.results_widget.clear()
            self.video_player.set_events([])
            return
        try:
            self.results_widget.load_path(video.result_path)
            result = self.pose_service.gait_engine.result_store.read_dict(video.result_path)
            self.video_player.set_events(list(result.get("events", [])))
        except (OSError, ValueError) as error:
            self.results_widget.clear()
            self.video_player.set_events([])
            self.analysis_status.setText(f"解析結果を読み込めません: {error}")

    def _analysis_running(self) -> bool:
        return self._analysis_thread is not None and self._analysis_thread.isRunning()

    def _show_no_patient(self) -> None:
        self.current_patient = None
        self.current_video = None
        self.patient_title.setText("患者を選択してください")
        self.patient_notes.setText("左の一覧から患者を選択すると動画を管理できます。")
        self.import_button.setEnabled(False)
        self.compare_button.setEnabled(False)
        self.reanalyze_button.setEnabled(False)
        self.video_list.clear()
        self.video_player.release()
        self.results_widget.clear()

    @staticmethod
    def _item_id(item: QListWidgetItem | None) -> str | None:
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._analysis_running() and self._analysis_worker and self._analysis_thread:
            response = QMessageBox.question(
                self,
                "Pose解析中です",
                "解析を中止して終了しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._analysis_worker.cancel()
            if not self._analysis_thread.wait(5_000):
                QMessageBox.information(self, "終了待ち", "解析の安全な終了を待っています。")
                event.ignore()
                return
        self.video_player.release()
        event.accept()
