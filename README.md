# MotionLab Gait for Windows

患者ごとに歩行動画をローカル管理し、MediaPipe Pose Landmarkerの33点推定、Skeleton表示、研究・評価用の時間指標・2D関節角度、顔ぼかし、経時比較、PDF/CSV出力を行うWindowsデスクトップアプリです。

> このアプリのIC/TO、歩行周期、指標、関節角度、観察特徴は未検証の自動推定です。医療機器や診断ソフトではありません。動画・撮影品質・臨床所見を確認し、単独で診断や治療判断に使用しないでください。

## Web / PWA版（Phase 1〜3相当）

`web`には、Windows・Mac・iPhone・iPadの現行ブラウザから利用できるローカル処理型PWAを追加しています。患者登録、動画の撮影・選択、患者への保存、MediaPipe Pose Landmarkerによる33点取得、動画時刻と同期するSkeleton表示までを実装しています。Windows版の定量解析は数値一致の検証前に移植せず、Web版ではまだ表示しません。

使い方:

1. 公開されたHTTPS URLをChrome / Edge / Safariで開く。
2. `＋ 登録`で患者IDを登録する。
3. 患者を選び、`歩行動画を撮影・選択`を押す。iPhone / iPadではカメラ撮影または写真ライブラリを選べます。
4. 解析完了後、再生・停止・シークしてSkeletonの追従を確認する。
5. iPhone / iPadではSafariの共有メニューから`ホーム画面に追加`するとアプリのように起動できます。

iPhone / iPad実機ではiOS / iPadOS 17以降のSafariを使用してください。公開先はHTTPS必須です。通常モードで開き、初回にモデルの読み込みが完了してからホーム画面へ追加します。患者データを継続保存する場合はプライベートブラウズを使用しないでください。ロックダウンモードではIndexedDBやFile APIが無効になるため、本アプリの患者保存・動画読込は利用できません。

実機確認の最短手順:

1. Safariで公開HTTPS URLを開き、画面上部に`外部送信なし・端末内処理`が表示されることを確認する。
2. `＋ 登録`でテスト患者を登録する。
3. `カメラで撮影`を押し、背面カメラで10秒程度の横向き動画を撮影する。または`動画を選択`から写真ライブラリ内のMOV / MP4を選ぶ。
4. Safariを前面にしたまま解析完了まで待つ。
5. 動画を再生・停止し、再生位置をシークしてSkeletonが追従することを確認する。
6. Safari共有メニュー → `ホーム画面に追加`後、ホーム画面版でも患者と動画が表示されることを確認する。

Safariで動画が開けない場合は、写真アプリから書き出したH.264のMP4または標準のQuickTime MOVを使用してください。長時間・4K動画は処理時間と端末容量を大きく使うため、まず10〜30秒の動画で確認してください。

動画、患者情報、33点Poseは外部APIへ送信せず、各ブラウザのIndexedDBに保存します。モデルとWASMも公開サイト自身から読み込み、Content Security Policyと実行時通信ガードの両方で他ドメインへの通信を拒否します。解析、再生、シーク、Skeleton描画はブラウザ内で完結します。端末ごと・ブラウザごとにデータは分離され、自動同期されません。Webサイトのデータを消すと患者データも消えるため、現段階では研究・評価用途です。共有端末ではOSのログインと端末暗号化を使用してください。

このPCだけで開く場合は [start_web_windows.bat](start_web_windows.bat) をダブルクリックします。サーバー停止時は最小化された`MotionLab Gait Web Server`画面を閉じてください。`index.html`を直接ダブルクリックする方式は、WASMとService Workerの制約により使用できません。

開発:

```powershell
cd web
pnpm install
pnpm test
pnpm build
pnpm preview
```

公開は静的HTTPSホスティングに`web/dist`を配置します。[GitHub Pagesの自動公開設定](.github/workflows/deploy-web.yml)を同梱しており、GitHubへpush後にRepository Settings → Pages → Sourceを`GitHub Actions`にすると、`main`更新時に公開されます。患者データはGitHubへ送られません。

Web版は`@mediapipe/tasks-vision 1.0.1`を自己ホストし、Pose推論をWorker内のWASM/CPUで実行します。モデル・WASMを初回に同一サイトから取得し、以後はPWAキャッシュを利用します。Content Security Policyで外部通信を禁止しています。MediaPipe Web公式実装: <https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/web_js>

## いちばん簡単な起動方法

このPCでは設定と`.exe`作成まで完了しています。

1. プロジェクト直下の `MotionLab Gait.lnk` をダブルクリックする。
2. ショートカットが使えない場合は `dist\MotionLab Gait\MotionLab Gait.exe` をダブルクリックする。
3. Windows SmartScreenが出た場合は、発行者署名のないローカル開発版であることを確認した上で、`詳細情報` → `実行`を選ぶ。

`MotionLab Gait.exe`だけを別の場所へ移動すると起動しません。移動する場合は`dist\MotionLab Gait`フォルダ全体を移動してください。開発版は [start_windows.bat](start_windows.bat) でも起動できます。

別のPCでソースから設定する場合:

```powershell
setup_windows.bat
start_windows.bat
```

64-bit Python 3.12と初回セットアップ時のインターネット接続が必要です。アプリの解析・患者管理はセットアップ後すべてPC内で動作します。

## 基本操作

1. `＋ 患者を登録`で患者IDを登録する。表示名は任意です。
2. 患者を選択し、`歩行動画を読み込む`から側方歩行動画を選ぶ。
3. 歩行条件、患側、装具、補助具を設定する。歩行速度が必要な場合だけ既知距離と計測区間を入力する。
4. Pose → 歩行解析 → 顔ぼかしコピー作成が順に進む。長い動画では完了まで待つ。
5. `動画・Skeleton`で再生、一時停止、シーク、0.25/0.5倍速、1フレーム送りを確認する。青/赤の目盛りは左/右IC・TO候補です。
6. `解析結果`で撮影面・採用区間、Quality、時間指標、左右差、関節角度、観察特徴を確認する。
7. 自動IC/TOが合わない場合だけ、`イベントを確認・修正`で時刻を直す。
8. 同じ患者に解析が2件以上ある場合は`経時比較`で指標、角度、Timeline、最初のIC基準同期動画を確認する。

顔ぼかしコピーがある場合は再生画面で既定表示されます。自動顔検出は見逃す可能性があるため、共有前に必ず動画全体を目視確認してください。

定量解析は側方の矢状面動画を対象とします。前額面、斜め、旋回が混じる場合は、3秒以上連続する最長の矢状面区間だけを自動採用します。採用できる区間がない場合、誤解を避けるためIC/TO・時間指標・角度は表示しません。同一患者の比較では、カメラの位置・高さ・距離、歩行方向、靴、装具、補助具、歩行条件を揃えてください。

通常画面の主要指標は、ケイデンス、ストライド時間、立脚期、遊脚期、立脚時間左右差に限定します。関節角度はシンプルな選択欄から股関節・膝関節・足関節を切り替えられ、初期表示は膝関節です。各関節は`測定品質：高 / 注意 / 解析困難`だけを通常表示し、足部追跡が不安定な場合は足関節を参考値または解析困難と明示します。

関節角度グラフの`参考波形`は初期OFFです。ONにすると成人の平地快適歩行を示す概略パターンを表示しますが、正常/異常の診断境界ではありません。0°基準線は表示範囲に0°が含まれる場合だけ薄い破線で表示します。

## Research Modeと出力

通常画面にはfilter、confidence、補間率などの詳細を出しません。メニューの`設定` → `Research Mode`をONにすると、Raw/Filtered角度比較、解析JSON詳細、CSV出力が表示されます。Raw Poseとprocessed Poseは別JSONLで保持し、解析JSONには関節別のvisibility、presence、外れ値率、補間率、連続性、有効・除外周期数を保存します。

CSV出力フォルダには次を保存します。

- `raw_landmarks.csv`: 元の33点、x/y/z、world座標、visibility、presence
- `processed_landmarks.csv`: 補間・外れ値置換・平滑化後の33点と処理フラグ
- `events.csv`: IC/TO、側、時刻、信頼度、自動/手動
- `metrics.csv`: 時間指標、左右差、速度、信頼度
- `joint_angles.csv`: 時刻、歩行周期%、関節角度、信頼度
- `analysis.json`: 品質、処理条件、警告、解析バージョンを含む完全な派生結果

PDFは1〜2ページで、患者ID、条件、Quality、主要指標、匿名化代表フレーム、角度波形、観察特徴、限界を出力します。

## 実装済み範囲

- Phase 1〜3: 患者管理、動画取込・保存・再生、MediaPipe 33点、時刻同期Skeleton
- Phase 4: 全動画Pose保持、矢状面区間の自動選択、撮影面を含むQuality A〜D
- Phase 5: 信頼度処理、短欠損補間、速度/MAD外れ値抑制、zero-phase Butterworth平滑化、自動IC/TO、歩行周期、手動修正
- Phase 6: step/stride/stance/swing、割合、cadence、条件付き速度、左右差、股・膝・足関節2D角度、グラフ
- Phase 7: MediaPipe Face DetectorとPose頭部補完による顔ぼかしコピー
- Phase 8: 同一患者内Timeline、Before/After指標・角度比較、条件差警告、最初のIC基準動画同期
- Phase 9: PDF、Research Mode、raw/processed/events/metrics/angles CSV・JSON
- Phase 10: 後方互換DB移行、単一起動、例外処理、テスト、実動画性能確認、Windows `.exe` 配布

観察特徴は測定結果だけを記述し、原因を断定しません。追加評価の候補は別の青い欄へ分離します。

## 技術構成

- Python 3.12.14
- PySide6 6.11.2 / Qt Widgets・Qt Charts
- SQLite（標準`sqlite3`）
- OpenCV 5.0.0.93（wheel内蔵FFmpeg）
- MediaPipe Tasks 1.0.1 / CPU XNNPACK
- SciPy 1.18.1（zero-phase Butterworth、ピーク候補抽出）
- PyInstaller 6.22.2（Windows onedir配布）

UI、患者管理、動画、PoseProvider、加工処理、イベント、運動学、ランドマーク保存、Overlay、匿名化、出力は別モジュールです。生Poseは上書きせず、processed Poseと解析結果を別ファイルへ保存します。

MediaPipe 1.0.1は「最新だから」ではなく、公式Tasks VIDEO API、Windows x86-64/Python 3.12 wheel、このPCでのPose/Faceモデル生成と実推論が成立したため採用しています。公式の[Pose Landmarker Pythonガイド](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python)と[Face Detector Pythonガイド](https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector/python)に沿っています。

詳細:

- [PC環境調査](docs/environment-audit.md)
- [Poseデータ仕様](docs/pose-data-schema.md)
- [解析定義と制約](docs/analysis-methods.md)
- [プライバシー設計](docs/privacy.md)
- [Web/PWA移行設計案（調査のみ・未実装）](docs/web-pwa-migration-plan.md)
- [v0.4 zero-phase実動画検証](docs/zero-phase-validation-v040.md)

## データ保存とバックアップ

ソース起動ではプロジェクト内の`data`、`.exe`起動では`dist\MotionLab Gait\data`に保存します。SQLite、元動画、匿名化動画、生/加工Pose、解析JSONが含まれます。アプリ更新前には`data`フォルダ全体を別ドライブへコピーしてください。

患者名・動画・解析結果は暗号化していません。Windowsログイン、BitLocker/デバイス暗号化、アクセス権を設定した院内管理PCで使い、クラウド同期フォルダへ置かないでください。

## 開発・検証

```powershell
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m pytest -q --basetemp .test-output\pytest-temp -p no:cacheprovider
$env:PYTHONPATH="src"
$env:QT_QPA_PLATFORM="offscreen"
.venv\Scripts\python.exe -m motionlab_gait --smoke-test --data-dir .test-output\smoke-data
```

配布版を再作成:

```powershell
build_windows_exe.bat
```

再ビルド時は`dist\MotionLab Gait\data`を自動退避・復元します。v0.3更新前データは`data-backup\2026-09-09-before-v0.3`、3関節UI更新前データは`data-backup\2026-09-09-before-three-joint-ui`、zero-phase処理更新前データは`data-backup\2026-09-09-before-zero-phase-v031`にも複製してあります。

このPCでは1,137フレームの実Poseから品質・イベント・周期・指標・角度JSONを作成し、19秒/1080×1920/約60fpsの実動画コピーから540×960の匿名化動画を約57秒で作成しました。速度は動画内容、解像度、CPU、ウイルス対策ソフトで変わります。

## 重要な未検証事項

- IC/TOと角度の基準機器（床反力計・3D motion capture）に対する妥当性、疾患別精度、検者間/再検査信頼性
- 正面、斜め、遮蔽、補助者同伴、装具、ゆっくり/病的歩行での精度
- 可変フレームレート全形式、長時間動画、複数顔の全条件での匿名化完全性
- Windows 11以外のPCと、コード署名済みインストーラー配布

このため現段階は臨床導入版ではなく、アルゴリズム検証が可能なローカル研究・評価版です。
