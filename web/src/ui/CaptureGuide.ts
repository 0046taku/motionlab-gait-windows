import type { CaptureConditions, Patient } from "../domain/models";

const GUIDE_SEEN_KEY = "motionlab.capture-guide.v1.seen";

export class CaptureGuide {
  private patient: Patient | null = null;
  private onConfirmed: ((conditions: CaptureConditions) => void) | null = null;

  constructor(private readonly host: HTMLElement) {
    this.mount();
    this.bind();
  }

  openForCapture(patient: Patient, onConfirmed: (conditions: CaptureConditions) => void): void {
    this.patient = patient;
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
          <p class="eyebrow">初回だけ・60秒撮影ガイド</p>
          <h2>正確さは、撮影で決まります</h2>
          <ol class="guide-steps">
            <li><strong>真横から</strong><span>患者に対してカメラを約90°へ置きます。</span></li>
            <li><strong>固定して</strong><span>横向き・背面1×カメラ。パンやズームはしません。</span></li>
            <li><strong>全身を入れる</strong><span>頭から踵・足先まで、歩行中ずっと切らさないでください。</span></li>
            <li><strong>定常歩行を撮る</strong><span>歩き始めと停止直前を避け、2〜3周期以上を確保します。</span></li>
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
          <h2>この5点だけ確認</h2>
          <ul class="quick-checks">
            <li>iPhone / iPadを横向き</li>
            <li>患者の真横</li>
            <li>全身と踵・足先が入る</li>
            <li>カメラを固定</li>
            <li>十分な明るさ</li>
            <li id="affected-side-check" hidden></li>
          </ul>
          <details class="capture-conditions">
            <summary>撮影条件を記録（任意）</summary>
            <div class="condition-grid">
              <label>歩行速度<select id="capture-gait-mode"><option value="unspecified">未指定</option><option value="comfortable">快適歩行</option><option value="maximum">最大歩行</option></select></label>
              <label>装具<select id="capture-orthosis"><option value="unspecified">未指定</option><option value="none">なし</option><option value="used">あり</option></select></label>
              <label>杖・歩行補助具<select id="capture-aid"><option value="unspecified">未指定</option><option value="none">なし</option><option value="used">あり</option></select></label>
              <label>カメラ側<select id="capture-camera-side"><option value="unspecified">未指定</option><option value="left">左側</option><option value="right">右側</option></select></label>
            </div>
          </details>
          <div class="guide-actions">
            <button id="capture-check-cancel" class="button ghost" type="button">キャンセル</button>
            <button class="button" type="submit">確認してカメラを開く</button>
          </div>
        </form>
      </dialog>
      <dialog id="capture-manual-dialog" class="guide-dialog manual">
        <div class="guide-body">
          <p class="eyebrow">必要なときに確認</p>
          <h2>高精度に測るための撮影方法</h2>
          <div class="manual-grid">
            <section><h3>カメラ</h3><ul><li>smartphone / iPhone / iPad</li><li>横向き・背面カメラ・1× lens</li><li>1080p / 60fps推奨（30fpsも使用可）</li><li>三脚などで固定</li><li>digital zoom・camera panはOFF</li></ul></section>
            <section><h3>位置</h3><ul><li>患者の真横90°を目標</li><li>高さは骨盤〜大転子付近</li><li>距離は固定せず、頭から足先と2〜3周期が入る位置</li><li>麻痺側をカメラ側にすることを推奨</li></ul></section>
            <section><h3>画角と歩行</h3><ul><li>十分な照明を確保</li><li>全身を歩行中ずっと画角内へ</li><li>踵・足先を絶対に切らない</li><li>歩き始め・停止直前を避けて定常歩行を撮影</li></ul></section>
          </div>
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
    this.element("capture-check-cancel").addEventListener("click", () => this.element<HTMLDialogElement>("capture-check-dialog").close());
    this.element<HTMLFormElement>("capture-check-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const conditions: CaptureConditions = {
        gaitMode: this.element<HTMLSelectElement>("capture-gait-mode").value as CaptureConditions["gaitMode"],
        orthosis: this.element<HTMLSelectElement>("capture-orthosis").value as CaptureConditions["orthosis"],
        walkingAid: this.element<HTMLSelectElement>("capture-aid").value as CaptureConditions["walkingAid"],
        cameraSide: this.element<HTMLSelectElement>("capture-camera-side").value as CaptureConditions["cameraSide"]
      };
      this.element<HTMLDialogElement>("capture-check-dialog").close();
      this.onConfirmed?.(conditions);
    });
    this.element("capture-manual-close").addEventListener("click", () => this.element<HTMLDialogElement>("capture-manual-dialog").close());
  }

  private openQuickCheck(): void {
    const affected = this.patient?.affectedSide;
    const affectedCheck = this.element<HTMLElement>("affected-side-check");
    affectedCheck.hidden = affected !== "left" && affected !== "right";
    affectedCheck.textContent = affected === "left" ? "麻痺側（左）をカメラ側" : "麻痺側（右）をカメラ側";
    this.element<HTMLSelectElement>("capture-camera-side").value = affected === "left" || affected === "right" ? affected : "unspecified";
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
