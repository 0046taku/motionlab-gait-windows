from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from motionlab_gait.config import APP_NAME, AppPaths
from motionlab_gait.persistence.database import Database
from motionlab_gait.persistence.patient_repository import PatientRepository
from motionlab_gait.persistence.video_repository import VideoRepository
from motionlab_gait.services.self_test import verify_model_initialization
from motionlab_gait.services.video_service import VideoService
from motionlab_gait.ui.main_window import MainWindow
from motionlab_gait.ui.styles import APP_STYLESHEET


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MotionLab Gait Windows")
    parser.add_argument("--data-dir", type=Path, help="アプリデータ保存先（テスト用）")
    parser.add_argument("--smoke-test", action="store_true", help="起動後すぐ正常終了する")
    parser.add_argument("--self-test", action="store_true", help="MediaPipeモデル初期化を検査する")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName(APP_NAME)
    application.setOrganizationName("MotionLab")
    application.setStyle("Fusion")
    application.setFont(QFont("Yu Gothic", 10))
    application.setStyleSheet(APP_STYLESHEET)

    try:
        paths = AppPaths.create(arguments.data_dir)
        instance_lock = QLockFile(str(paths.data_root / ".motionlab-gait.lock"))
        instance_lock.setStaleLockTime(30_000)
        if not instance_lock.tryLock(100):
            QMessageBox.information(None, APP_NAME, "MotionLab Gaitはすでに起動しています。")
            return 0
        database = Database(paths.database)
        database.initialize()
        if arguments.self_test:
            verify_model_initialization(paths)
            instance_lock.unlock()
            return 0
    except Exception as error:
        if arguments.self_test:
            print(f"Self-test failed: {error}", file=sys.stderr)
            return 1
        QMessageBox.critical(None, APP_NAME, f"保存先を初期化できませんでした。\n{error}")
        return 1

    window = MainWindow(
        paths=paths,
        patient_repository=PatientRepository(database),
        video_repository=VideoRepository(database),
        video_service=VideoService(paths.videos),
    )
    window.show()
    if arguments.smoke_test:
        QTimer.singleShot(350, application.quit)
    exit_code = application.exec()
    instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    raise SystemExit(main())
