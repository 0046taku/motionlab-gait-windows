from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from motionlab_gait.config import AppPaths  # noqa: E402
from motionlab_gait.persistence.database import Database  # noqa: E402
from motionlab_gait.persistence.landmark_store import LandmarkStore  # noqa: E402
from motionlab_gait.persistence.patient_repository import PatientRepository  # noqa: E402
from motionlab_gait.persistence.video_repository import VideoRepository  # noqa: E402
from motionlab_gait.pose.mediapipe_provider import MediaPipePoseProvider  # noqa: E402
from motionlab_gait.services.pose_analysis_service import PoseAnalysisService  # noqa: E402
from motionlab_gait.services.video_service import VideoService  # noqa: E402
from motionlab_gait.ui.main_window import MainWindow  # noqa: E402
from motionlab_gait.ui.styles import APP_STYLESHEET  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/simulate_phase3.py <video-path>")
        return 2
    source_video = Path(sys.argv[1]).resolve()
    run_id = uuid.uuid4().hex[:8]
    paths = AppPaths.create(PROJECT_ROOT / ".test-output" / f"simulation-{run_id}")
    database = Database(paths.database)
    database.initialize()
    patients = PatientRepository(database)
    videos = VideoRepository(database)

    patient = patients.create(f"SIM-{run_id}", "Phase 3 動作確認患者", "自動テスト用")
    imported = VideoService(paths.videos).import_for_patient(source_video, patient.id)
    videos.add(imported)
    service = PoseAnalysisService(
        paths.model,
        paths.poses,
        MediaPipePoseProvider,
        LandmarkStore(),
    )
    summary = service.analyze(imported)
    videos.mark_pose_ready(imported.id, summary.output_path)

    application = QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLESHEET)
    window = MainWindow(paths, patients, videos, VideoService(paths.videos))
    window.show()
    application.processEvents()
    window.video_player.seek(imported.duration_ms // 2)
    application.processEvents()
    output = PROJECT_ROOT / ".test-output" / "phase3-simulation.png"
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError("Simulation screenshot could not be saved")
    timeline = LandmarkStore().read(summary.output_path)
    first_detected = next((frame for frame in timeline.frames if frame.landmarks), None)
    if first_detected is None or len(first_detected.landmarks) != 33:
        raise AssertionError("Simulation did not produce 33 landmarks")
    print(
        "Phase 3 simulation OK: "
        f"patient={patient.patient_code}, video={imported.original_name}, "
        f"pose={summary.detected_frame_count}/{summary.frame_count}, screenshot={output}"
    )
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
