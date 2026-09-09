from __future__ import annotations

from collections.abc import Sequence

import numpy as np

REFERENCE_LABEL = "成人・平地・快適歩行の概略参考（診断基準ではありません）"
REFERENCE_SOURCES = (
    "Michelini et al. Prosthet Orthot Int. 2020;44:245-262. PMID: 32507049",
    "Stenum et al. PLoS Comput Biol. 2021;17:e1008935. PMID: 33891585",
    "成人歩行の概略ROM: 股関節約-10〜35°、膝約5〜60°、足関節約-15〜15°",
)

# Broad illustrative anchors for level, comfortable adult walking. These are intentionally
# wider than a single laboratory's mean curve because 2D MediaPipe angles are not identical
# to a calibrated 3D biomechanical model.
_ANCHORS: dict[str, tuple[Sequence[float], Sequence[float], float]] = {
    "hip_flexion": (
        (0, 10, 30, 50, 60, 75, 100),
        (28, 24, 8, -8, -10, 12, 28),
        10.0,
    ),
    "knee_flexion": (
        (0, 10, 30, 50, 60, 75, 100),
        (5, 15, 5, 10, 35, 60, 5),
        12.0,
    ),
    "ankle_dorsiflexion": (
        (0, 10, 30, 50, 60, 70, 85, 100),
        (0, -7, 5, 10, -15, -5, 3, 0),
        8.0,
    ),
}


def normal_reference(joint: str) -> tuple[tuple[float, float, float, float], ...]:
    percentages, means, half_width = _ANCHORS[joint]
    x = np.arange(101, dtype=float)
    mean = np.interp(x, percentages, means)
    return tuple(
        (float(percent), float(value), float(value - half_width), float(value + half_width))
        for percent, value in zip(x, mean, strict=True)
    )
