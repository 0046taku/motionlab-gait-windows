# Windows環境調査（更新: 2026-09-09）

実装前にこのPCで確認した内容です。

| 項目 | 結果 | 採用判断 |
|---|---|---|
| OS | Windows 11 Home 64-bit, build 26200 | 対象環境 |
| CPU | Intel Core Ultra 7 258V, 8 cores | CPU/XNNPACK推論を基準にする |
| RAM | 約32 GB | 動画を全展開せず1フレームずつ処理する |
| GPU | Intel Arc 140V | Phase 1〜3ではGPU固有delegateを使わない |
| Python | Codex同梱 3.12.14。開始時はシステムPATHになし | project-local `.venv` を作成 |
| MediaPipe | 開始時なし | 1.0.1 Windows x86-64 wheelを導入 |
| PySide6 | 開始時なし | 6.11.2 Windows x86-64 wheelを導入 |
| OpenCV | 開始時なし | MediaPipe正式依存のcontrib 5.0.0を1種類だけ導入 |
| FFmpeg | システムPATHになし | OpenCV wheel内蔵FFmpeg 61系が有効なため追加不要 |
| SciPy | 1.18.1 Windows CPython 3.12 wheel | filterとevent候補抽出 |
| PyInstaller | 6.22.2 | onedir `.exe` を作成 |

検証後の `pip check` は `No broken requirements found`。MediaPipe Pose LandmarkerはCPU XNNPACK delegateで起動し、全身画像を動画化した8フレームすべてから33 landmarksを取得しました。Face Detectorモデル生成、1,137フレームの実Pose解析、実動画コピーの匿名化、CSV/PDF出力、Python版と`.exe`版の起動スモーク試験も完了しています。

PyInstaller実行時、開発環境PATHに含まれるPopplerのICU 78がQt 6.11と衝突しました。`build_windows_exe.bat`は誤って収集された`icuuc.dll`/`icudt78.dll`を除外し、PySide同梱MSVC runtimeを配置します。この修正後の`.exe`で起動を確認しました。
