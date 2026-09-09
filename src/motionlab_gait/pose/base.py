from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any

from motionlab_gait.domain.models import PoseLandmark


class PoseProvider(ABC):
    @abstractmethod
    def detect(self, rgb_frame: Any, timestamp_ms: int) -> tuple[PoseLandmark, ...]:
        """Detect landmarks for one RGB video frame."""

    @abstractmethod
    def close(self) -> None:
        """Release provider resources."""

    def __enter__(self) -> PoseProvider:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
