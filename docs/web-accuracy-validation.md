# Web版 Accuracy Validation

Web版の通常画面は、1動画につきユーザーが指定したcamera-side下肢だけを正式解析します。右側面動画は右、左側面動画は左だけを表示し、左右比較には2本の動画を使います。Poseによるcamera-side推定は入力ミス確認の補助であり、選択側を自動変更しません。

## Validation Mode

ローカルURLまたはGitHub Pages URLの末尾に `?validation=1` を付けて開きます。例: `http://localhost:5173/?validation=1`。

通常画面には出さない次の情報を確認できます。

- camera-side指定と補助推定の一致
- 画面中央に近い良質な2〜3周期の選択結果
- 肩–股、股–膝、膝–足、踵–足先のsegment長安定性
- out-of-plane riskと単発kinematic jump
- camera-side KNEE / ANKLE / HEEL / FOOT_INDEX周辺の相対sharpness
- 先頭1〜2秒の静止立位候補（品質確認のみ）
- 拡大したRaw landmarkと動画上の位置
- 動画全体のRaw Knee AngleとFiltered Knee Angle

中央周期は固定した画面幅パーセントで切り捨てず、品質条件を満たすcamera-side周期を中心への近さで順位付けします。最大3周期を正式波形候補にします。

Motion blurの値は同一動画内の相対値です。端末・衣服・背景・圧縮の影響を受けるため、現時点では通常撮影QCの合否に使いません。連続した低sharpness区間はValidation Modeで再撮影検討として表示します。

静止立位候補から股関節・膝関節を0°とは仮定しません。足関節neutral候補も表示だけで、Raw/Filtered角度へのoffset補正には使いません。baseline correction、正常波形への位置合わせ、minimum/最初のframeを0°にする処理はありません。

## Manual Knee Angle比較

1. camera-sideを明示して動画を解析する。
2. Validation Modeを開き、`16代表frame候補を作成`を押す。
3. Initial Contact、Loading Response、Mid/Terminal Stance、Pre/Initial/Mid/Terminal Swingの各候補へ、動画上で別途測定したManual Knee Angleを入力する。
4. RawとFilteredを別々に確認する。

計算する指標は、absolute error、MAE、RMSE、最大絶対誤差、Mean Bias、95% Limits of Agreement、ICC(A,1)です。errorは `MotionLab - Manual` です。現時点では正式な許容誤差を設定せず、合否判定は行いません。

代表frameの候補は2周期×8相で最大16 frameです。歩行イベントや周期の信頼性が不足する動画では候補を作成しません。Manual値は患者動画と同様に端末内IndexedDBへ保存され、外部サーバーへ送信しません。

## Pose modelと現在の限界

現在のWeb版は `@mediapipe/tasks-vision@1.0.1/pose_landmarker_full` を使用します。Lite / Full / Heavyの同一実動画比較は未実施です。モデル名だけでHeavyを採用せず、手動角度差、segment安定性、Raw角度安定性、処理時間、iPhone Safari実用性を同一動画で測定してから決定します。

2D動画だけからcamera yaw/pitch/roll、透視歪み、真の3D関節角度を復元・補正することはしません。side-view proxyが不十分な周期は代表波形から除外し、撮り直しを優先します。足関節はHEEL / FOOT_INDEX、靴、装具、遮蔽の影響が大きく、股・膝と同等精度を前提にしません。

実動画とManual Referenceがリポジトリに含まれていないため、MAE等の実測値、画面中央と端の差、Lite/Full/Heavy比較値は未算出です。これらを根拠なく生成しないでください。
