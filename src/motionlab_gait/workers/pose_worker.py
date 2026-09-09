from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from motionlab_gait.domain.models import VideoRecord
from motionlab_gait.services.pose_analysis_service import PoseAnalysisService, PoseAnalysisSummary


class PoseAnalysisWorker(QObject):
    progress = Signal(int, int)
    stage_changed = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: PoseAnalysisService, video: VideoRecord) -> None:
        super().__init__()
        self.service = service
        self.video = video
        self._cancelled = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            summary: PoseAnalysisSummary = self.service.analyze(
                self.video,
                progress=lambda current, total: self.progress.emit(current, total),
                is_cancelled=self._cancelled.is_set,
                stage=self.stage_changed.emit,
            )
            self.completed.emit(summary)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self._cancelled.set()
