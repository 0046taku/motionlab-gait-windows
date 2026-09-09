from __future__ import annotations

import hashlib
import ssl
import urllib.request
from pathlib import Path

import certifi

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    (
        "pose_landmarker_full.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_full/float16/1/pose_landmarker_full.task",
        "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1",
    ),
    (
        "blaze_face_short_range.tflite",
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
        "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f",
    ),
)


def download(filename: str, url: str, expected_sha256: str) -> None:
    destination = PROJECT_ROOT / "models" / filename
    temporary = destination.with_suffix(destination.suffix + ".download")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "MotionLabGait/0.2"})
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, context=context, timeout=120) as response:
            temporary.write_bytes(response.read())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise RuntimeError(f"Model checksum mismatch: {digest}")
        if not expected_sha256:
            print(f"SHA256 {filename}: {digest}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Downloaded: {destination}")


def main() -> int:
    for filename, url, expected_sha256 in MODELS:
        destination = PROJECT_ROOT / "models" / filename
        if not destination.is_file():
            download(filename, url, expected_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
