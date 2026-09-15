import type { CaptureConditions, Patient } from "../domain/models";

const GUIDE_SEEN_KEY = "motionlab.capture-guide.v2.seen";

export class CaptureGuide {
  private patient: Patient | null = null;
  private action: "capture" | "select" = "capture";
  private onConfirmed: ((conditions: CaptureConditions) => void) | null = null;

  constructor(private readonly host: HTMLElement) {
    this.mount();
    this.bind();
  }

  openForCapture(patient: Patient, onConfirmed: (conditions: CaptureConditions) => void): void {
    this.patient = patient;
    this.action = "capture";
    this.onConfirmed = onConfirmed;
    if (this.hasSeenInitialGuide()) this.openQuickCheck();
    else this.element<HTMLDialogElement>("capture-intro-dialog").showModal();
  }

  openForVideoSelection(patient: Patient, onConfirmed: (conditions: CaptureConditions) => void): void {
    this.patient = patient;
    this.action = "select";
    this.onConfirmed = onConfirmed;
    if (this.hasSeenInitialGuide()) this.openQuickCheck();
    else this.element<HTMLDialogElement>("capture-intro-dialog").showModal();
  }

  openManual(): void {
    this.element<HTMLDialogElement>("capture-manual-dialog").showModal();
  }

  private mount(): void {
    this.host.insertAdjacentHTML("beforeend", `
      <dialog id="capture-intro-dialog" class="guide-dialog">
        <div class="guide-body">
          <p class="eyebrow">MotionLab Gait 標準撮影プロトコル</p>
          <h2>初回60秒ガイド</h2>
          <ol class="guide-steps">
            <li><strong>真横から</strong><span>患者に対してカメラを約90°に設置します。</span></li>
            <li><strong>固定して</strong><span>横向き・背面1×カメラ。撮影中はパンや追従をしません。</span></li>
            <li><strong>全身を入れる</strong><span>頭から踵・足先まで、歩行中ずっと切らさないでください。</span></li>
            <li><strong>定常歩行を撮る</strong><span>歩き始めと停止直前を避け、3周期程度を確保します。</span></li>
          </ol>
          <div class="guide-actions">
            <button id="capture-intro-close" class="button ghost" type="button">あとで</button>
            <button id="capture-intro-next" class="button" type="button">5秒チェックへ</button>
          </div>
        </div>
      </dialog>

      <dialog id="capture-check-dialog" class="guide-dialog compact">
        <form id="capture-check-form" class="guide-body">
          <p class="eyebrow">撮影直前・5秒チェック</p>
          <h2>高精度撮影チェック</h2>
          <ul class="quick-checks">
            <li>真横から撮影</li><li>カメラ固定</li><li>頭から足先まで入れる</li>
            <li>解析したい脚をカメラ側へ</li><li>定常歩行を3周期程度確保</li>
            <li id="affected-side-check" hidden></li>
          </ul>
          <p class="automatic-check-note">横向き・fps・明るさ・全身と足部の検出は、動画読込後に端末内で自動確認します。</p>

          <section class="capture-mode" aria-labelledby="capture-mode-title">
            <h3 id="capture-mode-title">撮影モード</h3>
            <div class="mode-grid">
              <fieldset class="segmented-field"><legend>歩行速度</legend><div class="segmented-options">
                <label><input type="radio" name="gaitMode" value="comfortable" checked><span>快適歩行</span></label>
                <label><input type="radio" name="gaitMode" value="maximum"><span>最大歩行</span></label>
              </div></fieldset>
              <fieldset class="segmented-field"><legend>装具</legend><div class="segmented-options">
                <label><input type="radio" name="orthosis" value="none" checked><span>なし</span></label>
                <label><input type="radio" name="orthosis" value="used"><span>あり</span></label>
              </div></fieldset>
              <label class="mode-select">歩行補助具<select id="capture-aid" name="walkingAid">
                <option value="none">なし</option><option value="cane_single">T字杖</option><option value="cane_multi">多点杖</option><option value="walker">歩行器</option><option value="other">その他</option>
              </select></label>
              <fieldset class="segmented-field"><legend>カメラ側</legend><div class="segmented-options">
                <label><input id="camera-side-left" type="radio" name="cameraSide" value="left" required><span>左</span></label>
                <label><input id="camera-side-right" type="radio" name="cameraSide" value="right"><span>右</span></label>
              </div><small id="camera-side-recommendation">解析を重視する下肢を選択してください。</small></fieldset>
            </div>
          </section>

          <details class="research-record">
            <summary>研究用記録（任意）</summary>
            <div class="condition-grid">
              <label>カメラ高さ（cm）<input name="cameraHeightCm" type="number" min="1" max="300" inputmode="decimal" placeholder="例：85"></label>
              <label>撮影距離（cm）<input name="shootingDistanceCm" type="number" min="1" max="2000" inputmode="decimal" placeholder="例：400"></label>
            </div>
          </details>
          <div class="guide-actions">
            <button id="capture-check-cancel" class="button ghost" type="button">キャンセル</button>
            <button id="capture-check-submit" class="button" type="submit">確認してカメラを開く</button>
          </div>
        </form>
      </dialog>

      <dialog id="capture-manual-dialog" class="guide-dialog manual">
        <div class="guide-body protocol-body">
          <p class="eyebrow">MotionLab Gait 標準撮影プロトコル</p>
          <h2>高精度に撮影する方法</h2>
          <ol class="protocol-steps">
            <li><span>STEP 1</span><div><strong>カメラを固定</strong><p>三脚などを使用し、撮影中はカメラを動かしません。</p></div></li>
            <li><span>STEP 2</span><div><strong>患者の真横へ</strong><p>カメラを歩行路に対して真横に設置します。</p></div></li>
            <li><span>STEP 3</span><div><strong>高さを合わせる</strong><p>カメラの高さは大転子付近を目安にします。</p></div></li>
            <li><span>STEP 4</span><div><strong>全身を入れる</strong><p>頭から踵・つま先まで、歩行中ずっと画面内に入るよう調整します。</p></div></li>
            <li><span>STEP 5</span><div><strong>解析側を手前へ</strong><p>解析したい下肢をカメラ側にします。</p></div></li>
            <li><span>STEP 6</span><div><strong>定常歩行を撮影</strong><p>歩き始め・止まり際ではなく、一定速度で歩いている区間を3周期程度撮影します。</p></div></li>
          </ol>

          <div class="capture-examples" aria-label="良い撮影と悪い撮影">
            <section class="good"><h3>良い撮影</h3><ul><li>真横</li><li>全身が入る</li><li>カメラ固定</li><li>足部が明瞭</li><li>定常歩行</li></ul></section>
            <section class="bad"><h3>悪い撮影</h3><ul><li>斜め前から</li><li>足先が切れる</li><li>カメラを追従させる</li><li>遠すぎる・暗い</li><li>身体が画面外・1周期だけ</li></ul></section>
          </div>

          <details class="protocol-details" open>
            <summary>標準条件を確認</summary>
            <div class="manual-grid">
              <section><h3>カメラ</h3><ul><li>スマートフォン / iPhone / iPad</li><li>背面カメラ・横向き・1×レンズ</li><li>1080p / 60fps推奨（30fpsも解析可能）</li><li>デジタルズームOFF、カメラ固定</li><li>撮影中のパン・追従は禁止</li></ul></section>
              <section><h3>位置と距離</h3><ul><li>患者に対して可能な限り真横（約90°）</li><li>高さは大転子付近、レンズ面は歩行路と平行</li><li>極端な見上げ・見下ろしを避ける</li><li>3〜5m程度から、全身・足部・複数周期が入るよう調整</li><li>距離は固定値ではなく、人物が小さくなりすぎないことを優先</li></ul></section>
              <section><h3>歩行と解析側</h3><ul><li>普段の自然な歩行を基本とする</li><li>歩き始め直後と停止直前を避ける</li><li>最低2〜3周期、可能なら3〜5周期</li><li>解析を重視する下肢をカメラ側へ</li><li>麻痺側設定時は麻痺側をカメラ側へ</li></ul></section>
              <section><h3>服装と環境</h3><ul><li>股・膝・足部の輪郭が分かる服装を推奨</li><li>長い上衣、幅広いパンツ、足部を隠す衣服は可能なら避ける</li><li>十分な照明を確保し、強い逆光を避ける</li><li>患者と背景を区別し、前を他者が横切らないようにする</li><li>可能なら背景の動きを少なくする</li></ul></section>
            </div>
          </details>

          <details class="research-protocol">
            <summary>研究・高再現性撮影</summary>
            <div class="research-protocol-body">
              <p>経時比較や研究では、次の条件を可能な限り統一してください。</p>
              <ul><li>同一端末・同一レンズ・同一解像度・同一fps</li><li>同一カメラ位置・高さ・camera-side</li><li>同一歩行速度・装具・歩行補助具</li><li>可能な限り同一の照明・背景・撮影環境</li><li>床面にカメラ位置と歩行路をマーキング</li></ul>
              <p>三脚高さと撮影距離は、撮影前画面の「研究用記録」へ任意で記録できます。通常撮影では入力不要です。</p>
            </div>
          </details>
          <p class="manual-note">V1の正式解析対象は、固定カメラによる側方歩行動画の矢状面下肢解析です。</p>
          <div class="guide-actions"><button id="capture-manual-close" class="button" type="button">閉じる</button></div>
        </div>
      </dialog>`);
  }

  private bind(): void {
    this.element("capture-intro-close").addEventListener("click", () => this.element<HTMLDialogElement>("capture-intro-dialog").close());
    this.element("capture-intro-next").addEventListener("click", () => {
      this.markInitialGuideSeen();
      this.element<HTMLDialogElement>("capture-intro-dialog").close();
      this.openQuickCheck();
    });
    this.element("capture-check-cancel").addEventListener("click", () => {
      this.onConfirmed = null;
      this.element<HTMLDialogElement>("capture-check-dialog").close();
    });
    this.element<HTMLFormElement>("capture-check-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.currentTarget as HTMLFormElement;
      if (!form.reportValidity()) return;
      const data = new FormData(form);
      const cameraHeightCm = optionalPositiveNumber(data.get("cameraHeightCm"));
      const shootingDistanceCm = optionalPositiveNumber(data.get("shootingDistanceCm"));
      const conditions: CaptureConditions = {
        gaitMode: String(data.get("gaitMode")) as CaptureConditions["gaitMode"],
        orthosis: String(data.get("orthosis")) as CaptureConditions["orthosis"],
        walkingAid: String(data.get("walkingAid")) as CaptureConditions["walkingAid"],
        cameraSide: String(data.get("cameraSide")) as CaptureConditions["cameraSide"],
        ...(cameraHeightCm === undefined ? {} : { cameraHeightCm }),
        ...(shootingDistanceCm === undefined ? {} : { shootingDistanceCm })
      };
      this.element<HTMLDialogElement>("capture-check-dialog").close();
      const callback = this.onConfirmed;
      this.onConfirmed = null;
      callback?.(conditions);
    });
    this.element("capture-manual-close").addEventListener("click", () => this.element<HTMLDialogElement>("capture-manual-dialog").close());
  }

  private openQuickCheck(): void {
    const form = this.element<HTMLFormElement>("capture-check-form");
    form.reset();
    const affected = this.patient?.affectedSide;
    const affectedCheck = this.element<HTMLElement>("affected-side-check");
    const recommendation = this.element<HTMLElement>("camera-side-recommendation");
    affectedCheck.hidden = affected !== "left" && affected !== "right";
    if (affected === "left" || affected === "right") {
      const sideLabel = affected === "left" ? "左" : "右";
      affectedCheck.textContent = `麻痺側（${sideLabel}）をカメラ側`;
      recommendation.textContent = `推奨：麻痺側（${sideLabel}）をカメラ側にしてください。`;
      this.element<HTMLInputElement>(affected === "left" ? "camera-side-left" : "camera-side-right").checked = true;
    } else {
      affectedCheck.textContent = "";
      recommendation.textContent = "解析を重視する下肢を選択してください。";
    }
    this.element<HTMLButtonElement>("capture-check-submit").textContent = this.action === "capture"
      ? "確認してカメラを開く" : "確認して動画を選ぶ";
    this.element<HTMLDialogElement>("capture-check-dialog").showModal();
  }

  private hasSeenInitialGuide(): boolean {
    try { return localStorage.getItem(GUIDE_SEEN_KEY) === "1"; } catch { return false; }
  }

  private markInitialGuideSeen(): void {
    try { localStorage.setItem(GUIDE_SEEN_KEY, "1"); } catch { /* Private browsing can deny storage. */ }
  }

  private element<T extends HTMLElement = HTMLElement>(id: string): T {
    const value = document.getElementById(id);
    if (!value) throw new Error(`撮影ガイド要素 ${id} が見つかりません。`);
    return value as T;
  }
}

function optionalPositiveNumber(value: FormDataEntryValue | null): number | undefined {
  const text = String(value ?? "").trim();
  if (!text) return undefined;
  const number = Number(text);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}
