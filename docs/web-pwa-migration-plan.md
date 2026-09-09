# Web / PWA移行設計案

調査日: 2026-09-09

この文書は設計案です。Web版の実装はまだ開始しておらず、現在のWindows版とPython解析エンジンを置換しません。

## 結論

第一候補は、同一のTypeScript PWAをWindows、Mac、iPhone、iPadの対応ブラウザで動かし、Pose推論・動画・患者データを端末内だけで扱うlocal-first構成です。Windows版Pythonエンジンは検証基準（reference implementation）として残し、同じ入力Poseに対するgolden testが一致してから解析処理を段階的にTypeScriptへ移します。

自動クラウド同期は行いません。外部サーバーへ患者動画を送らない条件では、患者データは端末ごとに独立します。端末間移行が必要になった場合は、明示操作による暗号化export/importを別要件として設計します。

## 現在のWindows版と移植境界

| 領域 | 現在 | Web/PWA方針 |
|---|---|---|
| UI | PySide6 / Qt Widgets・Charts | React等に依存しない小さなTypeScript UI層、または軽量コンポーネント。タッチ幅とSafariを優先 |
| 患者・動画管理 | SQLite + filesystem | IndexedDBに患者・索引・解析JSON、動画BlobはOPFS優先・IndexedDB fallback |
| 動画入力 | Windows file dialog | `<input type="file" accept="video/*" capture>`で撮影または選択。撮影形式差を起動時検査 |
| Pose | MediaPipe Tasks Python VIDEO mode | `@mediapipe/tasks-vision` PoseLandmarker VIDEO modeをWeb Worker内で実行 |
| 33点・共通schema | JSONL / analysis JSON | `timestamp_ms, index/name, x/y/z, visibility, presence, world_*`を同じversioned schemaで保持 |
| Skeleton同期 | Qt player position + nearest timestamp | `<video>.requestVideoFrameCallback()`のmedia timeで最寄りPoseを選択しCanvas描画 |
| 信号処理 | NumPy / SciPy / Python | TypeScriptへ再実装し、Python golden fixturesと許容誤差テスト。必要時のみ小さなRust/WASM coreを検討 |
| 出力・比較・顔処理 | Windowsに実装済み | 移行後半。初期PWAには含めない |

患者モデル、Pose/解析JSON schema、品質の3段階表示、関節角度の定義、周期正規化の仕様は言語非依存なので移植可能です。一方、NumPy/SciPyのButterworth forward-backward filter、速度/MAD外れ値処理、イベント検出、周期品質除外、中央値代表波形はTypeScript等で同じ数値結果になるよう再実装が必要です。SwiftやPySide6のUIコード自体は移植しません。

## MediaPipe PoseのWeb対応

Google公式の[Pose Landmarker Webガイド](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/web_js)は`@mediapipe/tasks-vision`、WASM、IMAGE/VIDEO mode、正規化landmarkとworld landmarkを提供しています。VIDEO modeでは各フレームに単調増加timestampを渡します。`detect()`/`detectForVideo()`は同期処理でメインスレッドを塞ぐため、公式案内どおりWeb Workerへ分離します。

モデル、WASM、JavaScript、CSSは同一originから配信してService Workerへ事前cacheします。実行時CDN、解析API、telemetryは使いません。CSPは原則`default-src 'self'; connect-src 'self'`とし、開発時にも動画やPoseを送信するPOSTを作りません。

## iPhone / iPad Safariの動画入力と同期

撮影・選択はユーザー操作からfile inputを開く方式を第一候補にします。連続カメラ撮影が必要なら`getUserMedia()` + `MediaRecorder`も利用できます。WebKitの[MediaRecorder API案内](https://webkit.org/blog/11353/mediarecorder-api/)ではiOS Safariのカメラ入力、MP4/H.264/AAC記録、Blobによるローカルpreviewが説明されています。

再生overlayはWebKitが対応する[`requestVideoFrameCallback()`](https://webkit.org/blog/12445/new-webkit-features-in-safari-15-4/)のmedia timestampを基準にします。play/pause/seekごとに動画時刻からPose timelineを二分探索し、表示フレームとCanvas skeletonを同じ描画callbackで更新します。

オフライン動画の全フレーム解析は、video要素で単調増加時刻をdecodeしCanvas/VideoFrame相当をWorkerへ渡す実装を基本にします。WebCodecs等は機能検出し、Safariで未対応または不安定なら使用しません。動画解像度を表示用と推論用に分け、推論はアスペクト比を保った縮小frameを逐次処理します。

## 性能と端末内保存

ブラウザ内Poseは技術的に可能ですが、長い高解像度動画ではiPhone/iPadのメモリ、発熱、battery、Safari tab lifecycleが制約になります。そのため、実機benchmarkで次を合格条件にします。

- 30/60fps、720p/1080p、10/30/60秒の処理時間、peak memory、端末温度、失敗率
- 前景・画面lock・中断復帰、storage不足、長時間taskのcancel
- 33点欠落率とWindows Python版との座標差
- Skeletonの表示時刻差、seek直後の同期

患者・解析metadataはIndexedDB、動画はOPFSを第一候補にします。Safari 17以降のWebKitはStorage API、IndexedDB、File System、Cache API、Service Workerをquota管理対象としており、ブラウザorigin quotaはdiskの最大60%ですが、容量不足やstorage pressureでは削除され得ます。[WebKitのstorage policy](https://webkit.org/blog/14403/updates-to-storage-policy/)に従い、`navigator.storage.estimate()`で取込前容量を確認し、`persist()`を要求し、`QuotaExceededError`を明示表示します。端末内保存だけを唯一の保全手段にせず、暗号化backupを必須運用にします。

## PWA・offline・privacy

- Web App Manifest、icons、standalone display、orientation対応を用意する。
- Service Workerはapp shell、MediaPipe WASM、modelをversion付きcacheへ保存する。患者動画はCache APIへ複製しない。
- 初回install完了後は機内modeでも患者選択、動画取込、Pose、Skeleton、解析結果を使えることをE2E testする。
- 更新は新cacheを準備後、解析中でない時だけユーザーへ通知して切り替える。
- 患者識別情報、動画、landmark、解析結果はnetwork request bodyへ含めない。エラーlogにも患者名・path・frame画像を入れない。
- hosting serverは静的PWA assetだけを配信し、患者API、upload endpoint、analyticsを持たない。
- HTTPSが必要。院内LAN配信の場合も証明書とoriginを固定する。

## 段階移行

1. Windows Python v0.4系の角度・filterを固定し、匿名化したgolden Pose fixtureと期待JSONを作る。
2. Web技術spikeを患者データなしで行い、Safari実機のPose速度、動画format、Worker、storage上限を測る。
3. TypeScript共通domain/schemaとimport/export validatorを作り、Pythonとのround-tripを確認する。
4. Pose Workerと動画同期overlayを作り、Windows/iPhone/iPadで同じ33点とtimestampを比較する。
5. 信号処理を順に移植し、各段階でPythonとの差（角度、ROM、peak timing、除外周期）を固定許容差内にする。
6. 患者管理とlocal storageを統合し、offline・容量不足・backup/restore・削除を検証する。
7. 院内pilot前に基準機器との妥当性、疾患別データ、privacy/security reviewを行う。

Web版を開始する判断条件は、Safari実機spikeでPoseが許容時間内に完了し、30〜60秒の動画をstorage不足なく扱え、Python golden testとの解析差が説明可能であることです。条件を満たさない場合もWindows版は継続利用でき、解析アルゴリズムを失いません。
