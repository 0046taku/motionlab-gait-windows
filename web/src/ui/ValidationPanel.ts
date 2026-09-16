import type { GaitPhaseLabel, ManualAngleReference, PoseFrame, VideoStudy } from "../domain/models";
import type { GaitAnalysisResult, Side } from "../analysis/types";
import { nearestPoseFrame } from "../overlay/SkeletonRenderer";
import { buildReference, calculateAccuracyMetrics, suggestKneeReferences } from "../validation/accuracyValidation";

const PHASE_LABELS: Record<GaitPhaseLabel, string> = {
  IC: "Initial Contact", loading_response: "Loading Response", mid_stance: "Mid Stance",
  terminal_stance: "Terminal Stance", pre_swing: "Pre Swing", initial_swing: "Initial Swing",
  mid_swing: "Mid Swing", terminal_swing: "Terminal Swing", other: "その他"
};

export class ValidationPanel {
  private references: ManualAngleReference[];

  constructor(
    private readonly container: HTMLElement,
    private readonly player: HTMLVideoElement,
    private readonly study: VideoStudy,
    private readonly result: GaitAnalysisResult,
    private readonly onSave: (references: ManualAngleReference[]) => Promise<void>
  ) {
    this.references = [...(study.manualAngleReferences ?? [])];
  }

  render(): void {
    const rawMetrics = calculateAccuracyMetrics(this.references, "raw");
    const filteredMetrics = calculateAccuracyMetrics(this.references, "filtered");
    const blur = this.study.videoMetadata?.motionBlurValidation;
    const side = this.result.primarySide;
    this.container.innerHTML = `<details class="validation-panel">
      <summary>Validation Mode（研究・精度確認）</summary>
      <div class="validation-body">
        <p class="validation-warning">通常の臨床結果には表示されません。許容誤差は未設定です。</p>
        <div class="validation-model"><strong>使用Pose model</strong><span>${this.result.versions.poseModelVersion}</span>
          <small>Fullを使用中。Lite / Heavyは同一実動画で未比較のため、優劣を判定していません。</small></div>
        <div class="validation-grid">
          <section><h4>Camera-side / 空間QC</h4>
            <p>ユーザー指定：${sideLabel(side)}　補助推定：${sideLabel(this.result.spatialValidation.cameraSideCheck.inferredSide)}</p>
            <p>中央優先cycle：${this.result.spatialValidation.selectedCycleCount}　方式：threshold固定なしの中央度順位</p>
            ${this.result.spatialValidation.segmentStability.map((item) => `<p>${segmentLabel(item.segment)}：CV ${(item.coefficientOfVariation * 100).toFixed(1)}%・単発変化 ${(item.suddenChangeRate * 100).toFixed(1)}%</p>`).join("")}
          </section>
          <section><h4>Motion blur Validation</h4>
            ${blur ? `<p>camera-side distal sharpness中央値：${blur.medianSharpness.toFixed(2)}</p><p>相対的な低sharpness frame：${(blur.lowSharpnessRate * 100).toFixed(1)}%（最長 ${blur.longestConsecutiveLowFrames} frame）</p>${blur.reviewRecommended ? `<p class="validation-warning">動きがぼやけている可能性があります。明るい場所で撮影した動画と比較してください。</p>` : ""}` : `<p>再解析後に評価できます。</p>`}
            <small>検証用の相対指標です。未検証の合否thresholdは通常QCへ適用していません。</small>
          </section>
          <section><h4>静止立位候補（先頭1〜2秒）</h4>
            ${renderStaticStanding(this.result)}
            <small>候補区間は品質確認だけに使用し、股・膝を0°とは仮定しません。足関節neutral候補も角度へ適用しません。</small>
          </section>
          <section><h4>Knee filter比較</h4>
            ${renderFilterValidation(this.result)}
            <small>4/6/8 Hz候補を同じ周期で比較します。通常解析は検証済み設定の6 Hzを維持し、見た目だけで自動変更しません。</small>
          </section>
        </div>
        <section class="validation-frame-review">
          <div><h4>Raw landmark / Knee angle確認</h4><p id="validation-current-values">動画を再生またはシークしてください。</p></div>
          <canvas id="validation-zoom-canvas" width="520" height="300" aria-label="Camera-side下肢ランドマーク拡大"></canvas>
          <div class="validation-actions">
            <button id="validation-add-current" class="button secondary small" type="button" ${side ? "" : "disabled"}>現在frameを追加</button>
            <button id="validation-suggest" class="button ghost small" type="button" ${this.result.cycles.length >= 2 ? "" : "disabled"}>16代表frame候補を作成</button>
          </div>
        </section>
        <div class="validation-metrics">
          ${metricsCard("Raw Knee Angle", rawMetrics)}${metricsCard("Filtered Knee Angle", filteredMetrics)}
        </div>
        <p class="validation-note">error = MotionLab − Manual。RawとFilteredは別集計です。baseline correctionや正常波形への位置合わせは行っていません。</p>
        ${this.renderReferenceTable()}
      </div>
    </details>`;
    const details = this.container.querySelector<HTMLDetailsElement>(".validation-panel");
    details?.addEventListener("toggle", () => { if (details.open) this.updateFramePreview(); });
    this.container.querySelector("#validation-add-current")?.addEventListener("click", () => void this.addCurrent());
    this.container.querySelector("#validation-suggest")?.addEventListener("click", () => void this.addSuggestions());
    this.container.querySelectorAll<HTMLButtonElement>("[data-validation-seek]").forEach((button) => {
      button.addEventListener("click", () => { this.player.currentTime = Number(button.dataset.validationSeek) / 1000; void this.player.play().then(() => this.player.pause()).catch(() => undefined); });
    });
    this.container.querySelectorAll<HTMLInputElement>("[data-manual-angle]").forEach((input) => {
      input.addEventListener("change", () => void this.updateManual(input.dataset.manualAngle!, input.value));
    });
    this.container.querySelectorAll<HTMLButtonElement>("[data-remove-reference]").forEach((button) => {
      button.addEventListener("click", () => void this.removeReference(button.dataset.removeReference!));
    });
    this.player.addEventListener("timeupdate", this.updateFramePreview);
    this.player.addEventListener("seeked", this.updateFramePreview);
  }

  dispose(): void {
    this.player.removeEventListener("timeupdate", this.updateFramePreview);
    this.player.removeEventListener("seeked", this.updateFramePreview);
  }

  private readonly updateFramePreview = (): void => {
    if (!this.container.querySelector<HTMLDetailsElement>(".validation-panel")?.open) return;
    const timestampMs = Math.round(this.player.currentTime * 1000);
    const frame = nearestPoseFrame(this.study.poseFrames, timestampMs);
    const side = this.result.primarySide;
    if (!frame || !side || this.player.readyState < 2) return;
    const reference = buildReference(this.result, side, timestampMs, "other", "preview");
    const values = this.container.querySelector<HTMLElement>("#validation-current-values");
    if (values) values.textContent = `${(timestampMs / 1000).toFixed(3)}秒　Raw ${formatAngle(reference.rawAngleDegrees)}　Filtered ${formatAngle(reference.filteredAngleDegrees)}`;
    const canvas = this.container.querySelector<HTMLCanvasElement>("#validation-zoom-canvas");
    if (canvas) drawLandmarkZoom(canvas, this.player, frame, side);
  };

  private async addCurrent(): Promise<void> {
    const side = this.result.primarySide;
    if (!side) return;
    this.references.push(buildReference(this.result, side, Math.round(this.player.currentTime * 1000), "other"));
    await this.persistAndRender();
  }

  private async addSuggestions(): Promise<void> {
    const suggestions = suggestKneeReferences(this.result);
    const existing = new Set(this.references.map((item) => `${item.timestampMs}:${item.side}`));
    this.references.push(...suggestions.filter((item) => !existing.has(`${item.timestampMs}:${item.side}`)));
    await this.persistAndRender();
  }

  private async updateManual(id: string, value: string): Promise<void> {
    const numeric = value.trim() === "" ? null : Number(value);
    if (numeric !== null && (!Number.isFinite(numeric) || numeric < -20 || numeric > 150)) return;
    this.references = this.references.map((item) => item.id === id ? { ...item, manualAngleDegrees: numeric } : item);
    await this.persistAndRender();
  }

  private async removeReference(id: string): Promise<void> {
    this.references = this.references.filter((item) => item.id !== id);
    await this.persistAndRender();
  }

  private async persistAndRender(): Promise<void> {
    this.dispose();
    await this.onSave(this.references);
    this.render();
    this.container.querySelector<HTMLDetailsElement>(".validation-panel")!.open = true;
    this.updateFramePreview();
  }

  private renderReferenceTable(): string {
    if (!this.references.length) return `<p class="validation-empty">代表frame候補を作成し、動画上の膝肢位を手動測定してください。</p>`;
    return `<div class="validation-table-wrap"><table class="validation-table"><thead><tr><th>Phase / 時刻</th><th>Raw</th><th>Filtered</th><th>Manual</th><th>Error</th><th></th></tr></thead><tbody>
      ${this.references.sort((a, b) => a.timestampMs - b.timestampMs).map((item) => {
        const error = item.manualAngleDegrees === null || item.rawAngleDegrees === null ? null : item.rawAngleDegrees - item.manualAngleDegrees;
        return `<tr><td><button class="validation-seek" type="button" data-validation-seek="${item.timestampMs}">${PHASE_LABELS[item.phase]}<br>${(item.timestampMs / 1000).toFixed(3)}s</button></td>
          <td>${formatAngle(item.rawAngleDegrees)}</td><td>${formatAngle(item.filteredAngleDegrees)}</td>
          <td><input data-manual-angle="${item.id}" type="number" min="-20" max="150" step="0.1" value="${item.manualAngleDegrees ?? ""}" aria-label="${PHASE_LABELS[item.phase]}のManual Knee Angle"></td>
          <td>${formatAngle(error)}</td><td><button class="validation-remove" type="button" data-remove-reference="${item.id}" aria-label="削除">×</button></td></tr>`;
      }).join("")}</tbody></table></div>`;
  }
}

function metricsCard(label: string, metrics: ReturnType<typeof calculateAccuracyMetrics>): string {
  if (!metrics) return `<section class="validation-metric-card"><h4>${label}</h4><p>Manual Reference未入力</p></section>`;
  return `<section class="validation-metric-card"><h4>${label}</h4><dl><div><dt>n</dt><dd>${metrics.count}</dd></div><div><dt>MAE</dt><dd>${metrics.meanAbsoluteError.toFixed(2)}°</dd></div><div><dt>RMSE</dt><dd>${metrics.rootMeanSquareError.toFixed(2)}°</dd></div><div><dt>最大誤差</dt><dd>${metrics.maximumAbsoluteError.toFixed(2)}°</dd></div><div><dt>Mean Bias</dt><dd>${metrics.meanBias.toFixed(2)}°</dd></div><div><dt>95% LoA</dt><dd>${metrics.lowerLimitOfAgreement.toFixed(2)}〜${metrics.upperLimitOfAgreement.toFixed(2)}°</dd></div><div><dt>ICC(A,1)</dt><dd>${metrics.iccAbsoluteAgreement === null ? "算出不可" : metrics.iccAbsoluteAgreement.toFixed(3)}</dd></div></dl></section>`;
}

function drawLandmarkZoom(canvas: HTMLCanvasElement, video: HTMLVideoElement, frame: PoseFrame, side: Side): void {
  const context = canvas.getContext("2d"); if (!context) return;
  const indices = side === "left" ? [11, 23, 25, 27, 29, 31] : [12, 24, 26, 28, 30, 32];
  const points = frame.landmarks.filter((item) => indices.includes(item.index));
  if (!points.length) return;
  const minX = Math.max(0, Math.min(...points.map((point) => point.x)) - 0.14);
  const maxX = Math.min(1, Math.max(...points.map((point) => point.x)) + 0.14);
  const minY = Math.max(0, Math.min(...points.map((point) => point.y)) - 0.08);
  const maxY = Math.min(1, Math.max(...points.map((point) => point.y)) + 0.08);
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(video, minX * video.videoWidth, minY * video.videoHeight,
    (maxX - minX) * video.videoWidth, (maxY - minY) * video.videoHeight, 0, 0, canvas.width, canvas.height);
  context.font = "bold 12px sans-serif"; context.lineWidth = 2;
  for (const point of points) {
    const x = (point.x - minX) / (maxX - minX) * canvas.width;
    const y = (point.y - minY) / (maxY - minY) * canvas.height;
    context.fillStyle = "#ffcf40"; context.strokeStyle = "#073f3b";
    context.beginPath(); context.arc(x, y, 5, 0, Math.PI * 2); context.fill(); context.stroke();
    context.fillStyle = "white"; context.strokeStyle = "#073f3b";
    const label = point.name.replace(`${side}_`, "").toUpperCase();
    context.strokeText(label, x + 7, y - 7); context.fillText(label, x + 7, y - 7);
  }
}

function formatAngle(value: number | null): string { return value === null ? "—" : `${value.toFixed(1)}°`; }
function sideLabel(side: Side | null): string { return side === "left" ? "左" : side === "right" ? "右" : "判定不可"; }
function segmentLabel(segment: string): string { return { shoulder_hip: "肩–股", hip_knee: "股–膝", knee_ankle: "膝–足", heel_toe: "踵–足先" }[segment] ?? segment; }
function renderStaticStanding(result: GaitAnalysisResult): string {
  const report = result.spatialValidation.staticStanding;
  const status = { candidate: "静止候補", moving: "歩行または移動あり", insufficient: "判定材料不足" }[report.status];
  const format = (value: number | null, suffix: string) => value === null ? "—" : `${value.toFixed(2)}${suffix}`;
  return `<p>判定：${status}</p><p>骨盤移動/体幹長：${format(report.pelvisTravelTorsoRatio, "")}　膝Raw jitter：${format(report.kneeRawJitterDegrees, "°")}</p><p>segment CV：${format(report.segmentLengthCoefficientOfVariation === null ? null : report.segmentLengthCoefficientOfVariation * 100, "%")}　足関節neutral候補：${format(report.ankleNeutralCandidateDegrees, "°")}</p>`;
}
function renderFilterValidation(result: GaitAnalysisResult): string {
  const side = result.primarySide;
  const rows = side ? result.filterValidation.filter((item) => item.side === side && item.joint === "knee_flexion") : [];
  if (!rows.length) return `<p>比較可能なKnee angleがありません。</p>`;
  return `<div class="validation-table-wrap"><table class="validation-table"><thead><tr><th>Cutoff</th><th>Peak差</th><th>ROM差</th><th>Peak時刻差</th><th>frame差 Raw→Filtered</th></tr></thead><tbody>${rows.map((item) => `<tr><td>${item.cutoffHz} Hz</td><td>${item.peakAttenuation.toFixed(2)}°</td><td>${item.romAttenuation.toFixed(2)}°</td><td>${item.peakTimingShiftMs} ms</td><td>${item.rawFrameToFrameVariation.toFixed(2)}→${item.filteredFrameToFrameVariation.toFixed(2)}°</td></tr>`).join("")}</tbody></table></div>`;
}
