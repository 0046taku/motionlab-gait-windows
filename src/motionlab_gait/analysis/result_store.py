from __future__ import annotations

import json
import os
from pathlib import Path

from motionlab_gait.analysis.types import GaitAnalysisResult


class AnalysisResultStore:
    def write(self, path: Path, result: GaitAnalysisResult) -> None:
        self.write_dict(path, result.to_dict())

    def write_dict(self, path: Path, result: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
                json.dump(result, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def read_dict(self, path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as source:
            value = json.load(source)
        if value.get("schema") != "motionlab.gait-analysis.v1":
            raise ValueError("未対応の解析結果形式です。")
        return value
