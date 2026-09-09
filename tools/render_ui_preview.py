from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOTIONLAB_DATA_DIR", str(PROJECT_ROOT / ".test-output" / "preview-data"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from motionlab_gait.config import AppPaths  # noqa: E402
from motionlab_gait.persistence.database import Database  # noqa: E402
from motionlab_gait.persistence.patient_repository import PatientRepository  # noqa: E402
from motionlab_gait.persistence.video_repository import VideoRepository  # noqa: E402
from motionlab_gait.services.video_service import VideoService  # noqa: E402
from motionlab_gait.ui.main_window import MainWindow  # noqa: E402
from motionlab_gait.ui.styles import APP_STYLESHEET  # noqa: E402


def main() -> int:
    application = QApplication([])
    application.setStyle("Fusion")
    application.setFont(QFont("Yu Gothic", 10))
    application.setStyleSheet(APP_STYLESHEET)
    paths = AppPaths.create()
    database = Database(paths.database)
    database.initialize()
    patients = PatientRepository(database)
    if not patients.list_all():
        patients.create("PT-001", "サンプル患者", "右側方から撮影した歩行動画")
    window = MainWindow(paths, patients, VideoRepository(database), VideoService(paths.videos))
    window.show()
    application.processEvents()
    output = PROJECT_ROOT / ".test-output" / "ui-preview.png"
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError("UI preview could not be saved")
    print(output)
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
