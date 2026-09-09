from __future__ import annotations

from collections import defaultdict

from motionlab_gait.analysis.types import AnglePoint, TemporalMetrics


def summarize_observed_features(
    metrics: TemporalMetrics,
    angles: tuple[AnglePoint, ...],
    *,
    affected_side: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    observed: list[str] = []
    checks: list[str] = []
    values = {item.name: item.value for item in metrics.values}
    stance_symmetry = values.get("stance_time_symmetry_index")
    if stance_symmetry is not None and stance_symmetry >= 10.0:
        observed.append(f"立脚時間の左右差指標は {stance_symmetry:.1f}% です。")
        checks.append("疼痛、疲労、補助具・装具条件と立脚時間差の関係を確認してください。")

    if affected_side not in {"left", "right"}:
        if not observed:
            observed.append("患側が未設定のため、患側・非患側の特徴比較は行っていません。")
        return tuple(observed), tuple(checks)

    unaffected = "right" if affected_side == "left" else "left"
    grouped: dict[tuple[str, str], list[AnglePoint]] = defaultdict(list)
    for point in angles:
        if point.cycle_percent is not None and point.confidence >= 0.5:
            grouped[(point.side, point.joint)].append(point)

    affected_knee = [
        item.angle_degrees
        for item in grouped[(affected_side, "knee_flexion")]
        if item.cycle_percent is not None and 55 <= item.cycle_percent <= 90
    ]
    unaffected_knee = [
        item.angle_degrees
        for item in grouped[(unaffected, "knee_flexion")]
        if item.cycle_percent is not None and 55 <= item.cycle_percent <= 90
    ]
    if affected_knee and unaffected_knee:
        difference = max(unaffected_knee) - max(affected_knee)
        if difference >= 10.0:
            observed.append(
                f"患側遊脚期の膝屈曲ピークは非患側より約 {difference:.1f}° 小さく推定されました。"
            )
            checks.append("膝関節可動域、足部クリアランス、歩行速度の影響を確認してください。")

    affected_hip = [
        item.angle_degrees
        for item in grouped[(affected_side, "hip_flexion")]
        if item.cycle_percent is not None and 30 <= item.cycle_percent <= 60
    ]
    unaffected_hip = [
        item.angle_degrees
        for item in grouped[(unaffected, "hip_flexion")]
        if item.cycle_percent is not None and 30 <= item.cycle_percent <= 60
    ]
    if affected_hip and unaffected_hip:
        difference = min(affected_hip) - min(unaffected_hip)
        if difference >= 7.0:
            observed.append(
                "患側terminal stanceの股関節伸展は"
                f"非患側より約 {difference:.1f}° 小さく推定されました。"
            )
            checks.append("股関節伸展可動域、体幹代償、歩幅と撮影方向を確認してください。")

    if not observed:
        observed.append("設定したルール閾値を超える主な左右差は検出されませんでした。")
    return tuple(observed), tuple(checks)
