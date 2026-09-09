# Poseデータ仕様 `motionlab.pose.v1`

Pose結果は患者・UI・将来の歩行解析ロジックから独立したUTF-8 JSON Linesです。1行目はmetadata、2行目以降は動画フレームです。

```json
{"type":"metadata","schema":"motionlab.pose.v1","video_id":"...","timestamp_unit":"milliseconds","landmark_count":33,"landmark_names":["nose","left_eye_inner"]}
{"type":"frame","frame_index":0,"timestamp_ms":0,"landmarks":[{"index":0,"name":"nose","x":0.51,"y":0.23,"z":-0.12,"visibility":0.99,"presence":0.99,"world_x":0.01,"world_y":-0.54,"world_z":-0.08}]}
```

- `timestamp_ms`: 動画デコーダの時刻。取得できない場合だけ `frame_index / fps` から補完
- `x`, `y`, `z`: MediaPipeの正規化画像座標。原点は左上
- `visibility`, `presence`: MediaPipeが返す信頼度
- `world_x`, `world_y`, `world_z`: MediaPipeのworld landmark（m）。取得できない場合は `null`
- 人物が検出されないフレームも `landmarks: []` として保存する

加工済みファイルは同じ座標定義を使い、各landmarkへ次を追加します。

- `interpolated`: 短欠損を補間した点
- `outlier_replaced`: 局所外れ値として除外後、補間できた点

元ファイルは常に保持し、加工済みPoseと`motionlab.gait-analysis.v1`解析JSONを別ファイルへ保存します。CSV列と派生値の定義は [analysis-methods.md](analysis-methods.md) を参照してください。
