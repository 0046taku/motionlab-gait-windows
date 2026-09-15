import { normalReference, REFERENCE_LABEL } from "../analysis/normalReference";
import { median } from "../analysis/statistics";
import type { AnglePoint, GaitAnalysisResult, Joint, Side } from "../analysis/types";

const JOINT_LABELS: Record<Joint, string> = {
  hip_flexion: "股関節屈曲",
  knee_flexion: "膝関節屈曲",
  ankle_dorsiflexion: "足関節背屈"
};
const JOINT_BUTTON_LABELS: Record<Joint, string> = {
  hip_flexion: "股関節", knee_flexion: "膝関節", ankle_dorsiflexion: "足関節"
};
const SIDE_COLORS: Record<Side, string> = { left: "#2674b8", right: "#d15f4b" };

export class AnalysisResultsView {
  private joint: Joint = "knee_flexion";
  private showReference = false;

  constructor(private readonly container: HTMLElement, private readonly result: GaitAnalysisResult) {}

  render(): void {
    const viewpointLabel = {
      sagittal: "矢状面", mixed: "混在（矢状面区間のみ採用）",
      frontal_or_oblique: "前額面・斜め", insufficient: "判定不可"
    }[this.result.viewpoint.classification];
    this.container.innerHTML = `
      <section class="analysis-results" aria-labelledby="analysis-heading">
        <div class="analysis-heading-row">
          <div><p class="eyebrow">解析結果</p><h3 id="analysis-heading">歩行周期で正規化した関節角度</h3></div>
          <span class="viewpoint-badge">${viewpointLabel}</span>
        </div>
        <div class="joint-switcher" role="group" aria-label="表示する関節">
          ${(["hip_flexion", "knee_flexion", "ankle_dorsiflexion"] as Joint[]).map((joint) =>
            `<button type="button" data-joint="${joint}" class="joint-button${joint === this.joint ? " active" : ""}" aria-pressed="${joint === this.joint}">${JOINT_BUTTON_LABELS[joint]}</button>`
          ).join("")}
        </div>
        <div id="joint-analysis-content"></div>
      </section>`;
    this.container.querySelectorAll<HTMLButtonElement>("[data-joint]").forEach((button) => {
      button.addEventListener("click", () => {
        this.joint = button.dataset.joint as Joint;
        this.render();
      });
    });
    this.renderJoint();
  }

  private renderJoint(): void {
    const content = this.container.querySelector<HTMLElement>("#joint-analysis-content");
    if (!content) return;
    const quality = this.result.jointQuality.find((item) => item.joint === this.joint);
    const statusLabel = quality ? { high: "高", caution: "注意", difficult: "解析困難" }[quality.status] : "解析困難";
    const statusClass = quality?.status ?? "difficult";
    if (!this.result.viewpoint.analysisSupported) {
      content.innerHTML = `<div class="analysis-empty"><strong>歩行イベントを確認してください</strong><p>${this.result.viewpoint.warnings.join(" ")}</p></div>`;
      return;
    }
    if (!quality || quality.status === "difficult") {
      content.innerHTML = `<div class="quality-row"><span class="quality-badge ${statusClass}">測定品質：${statusLabel}</span></div>
        <div class="analysis-empty"><strong>歩行イベントを確認してください</strong><p>${quality?.warnings.join(" ") || "この関節の有効な歩行周期を取得できませんでした。"}</p></div>`;
      return;
    }
    const buckets = buildBuckets(this.result.angles, this.joint);
    const left = bucketSeries(buckets, "left"); const right = bucketSeries(buckets, "right");
    const references = this.showReference ? normalReference(this.joint) : [];
    const allValues = [...left.map((point) => point.value), ...right.map((point) => point.value), ...references.map((point) => point.mean)];
    if (!allValues.length) {
      content.innerHTML = `<div class="quality-row"><span class="quality-badge caution">測定品質：注意</span></div>
        <div class="analysis-empty"><strong>歩行イベントを確認してください</strong><p>有効な歩行周期の角度波形を作成できませんでした。</p></div>`;
      return;
    }
    const axis = niceAxis(allValues);
    const chart = renderChart(left, right, references, axis.minimum, axis.maximum, axis.step, this.joint);
    const ankleSuffix = this.joint === "ankle_dorsiflexion" && quality.status === "caution" ? "（参考値）" : "";
    content.innerHTML = `
      <div class="quality-row">
        <span class="quality-badge ${statusClass}">測定品質：${statusLabel}${ankleSuffix}</span>
        <label class="reference-toggle"><input id="reference-toggle" type="checkbox" ${this.showReference ? "checked" : ""} />参考波形</label>
      </div>
      ${quality.warnings.length ? `<p class="joint-warning">${quality.warnings.join(" ")}</p>` : ""}
      <div class="chart-card">${chart}</div>
      ${this.showReference ? `<p class="reference-note">${REFERENCE_LABEL}</p>` : ""}
      <div class="analysis-metrics" aria-label="関節角度の要約">
        ${summaryMetric("左", left)}${summaryMetric("右", right)}
        <div class="analysis-metric"><span>有効周期</span><strong>${quality.validCycleCount}</strong><small>除外 ${quality.excludedCycleCount}周期</small></div>
      </div>
      <p class="analysis-disclaimer">2D Poseによる臨床観察支援値です。診断や治療判断には、動画上の姿勢と併せて確認してください。</p>`;
    content.querySelector<HTMLInputElement>("#reference-toggle")?.addEventListener("change", (event) => {
      this.showReference = (event.currentTarget as HTMLInputElement).checked;
      this.renderJoint();
    });
  }
}

type SeriesPoint = { percent: number; value: number };
function buildBuckets(points: readonly AnglePoint[], joint: Joint): Map<string, number[]> {
  const buckets = new Map<string, number[]>();
  for (const point of points) {
    if (point.joint !== joint || point.cyclePercent === null || point.confidence < 0.5) continue;
    const percent = Math.max(0, Math.min(100, Math.round(point.cyclePercent)));
    const key = `${point.side}:${percent}`;
    const values = buckets.get(key) ?? [];
    values.push(point.angleDegrees); buckets.set(key, values);
  }
  return buckets;
}
function bucketSeries(buckets: Map<string, number[]>, side: Side): SeriesPoint[] {
  const output: SeriesPoint[] = [];
  for (let percent = 0; percent <= 100; percent += 1) {
    const values = buckets.get(`${side}:${percent}`);
    if (values?.length) output.push({ percent, value: median(values) });
  }
  return output;
}
function summaryMetric(side: string, points: readonly SeriesPoint[]): string {
  if (!points.length) return `<div class="analysis-metric"><span>${side}</span><strong>算出不可</strong><small>有効値なし</small></div>`;
  const values = points.map((point) => point.value); const minimum = Math.min(...values); const maximum = Math.max(...values);
  return `<div class="analysis-metric"><span>${side}</span><strong>${minimum.toFixed(1)}〜${maximum.toFixed(1)}°</strong><small>ROM ${(maximum - minimum).toFixed(1)}°</small></div>`;
}
function niceAxis(values: readonly number[]): { minimum: number; maximum: number; step: number } {
  const minimumValue = Math.min(...values); const maximumValue = Math.max(...values);
  const span = Math.max(maximumValue - minimumValue, 10); const rawStep = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep)); const normalized = rawStep / magnitude;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : 5; const step = factor * magnitude;
  const minimum = Math.floor(minimumValue / step) * step; let maximum = Math.ceil(maximumValue / step) * step;
  if (maximum <= minimum) maximum = minimum + step;
  return { minimum, maximum, step };
}
function renderChart(
  left: readonly SeriesPoint[], right: readonly SeriesPoint[],
  reference: readonly { percent: number; mean: number }[], minimum: number, maximum: number, step: number, joint: Joint
): string {
  const width = 720; const height = 360; const margin = { left: 64, right: 24, top: 52, bottom: 58 };
  const plotWidth = width - margin.left - margin.right; const plotHeight = height - margin.top - margin.bottom;
  const x = (percent: number) => margin.left + percent / 100 * plotWidth;
  const y = (value: number) => margin.top + (maximum - value) / (maximum - minimum) * plotHeight;
  const path = (points: readonly SeriesPoint[]) => points.map((point, index) => `${index ? "L" : "M"}${x(point.percent).toFixed(2)},${y(point.value).toFixed(2)}`).join(" ");
  const yTicks: number[] = [];
  for (let value = minimum; value <= maximum + step * 0.1; value += step) yTicks.push(value);
  const referencePoints = reference.map((point) => ({ percent: point.percent, value: point.mean }));
  const zeroLine = minimum <= 0 && maximum >= 0 ? `<line class="chart-zero" x1="${x(0)}" x2="${x(100)}" y1="${y(0)}" y2="${y(0)}" />` : "";
  return `<svg class="joint-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${JOINT_LABELS[joint]}の左・右波形">
    <text class="chart-title" x="${width / 2}" y="25" text-anchor="middle">${JOINT_LABELS[joint]}</text>
    ${yTicks.map((value) => `<line class="chart-grid" x1="${x(0)}" x2="${x(100)}" y1="${y(value)}" y2="${y(value)}"/><text class="chart-tick" x="${margin.left - 10}" y="${y(value) + 4}" text-anchor="end">${value.toFixed(0)}</text>`).join("")}
    ${[0, 25, 50, 75, 100].map((value) => `<line class="chart-grid vertical" x1="${x(value)}" x2="${x(value)}" y1="${margin.top}" y2="${height - margin.bottom}"/><text class="chart-tick" x="${x(value)}" y="${height - margin.bottom + 22}" text-anchor="middle">${value}</text>`).join("")}
    ${zeroLine}
    ${reference.length ? `<path class="chart-reference" d="${path(referencePoints)}"/>` : ""}
    ${left.length ? `<path class="chart-wave left" d="${path(left)}"/>` : ""}
    ${right.length ? `<path class="chart-wave right" d="${path(right)}"/>` : ""}
    <g class="chart-legend"><line x1="${width - 164}" x2="${width - 140}" y1="25" y2="25" stroke="${SIDE_COLORS.left}" stroke-width="3"/><text x="${width - 134}" y="29">左</text><line x1="${width - 94}" x2="${width - 70}" y1="25" y2="25" stroke="${SIDE_COLORS.right}" stroke-width="3"/><text x="${width - 64}" y="29">右</text></g>
    <text class="chart-axis-label" x="${width / 2}" y="${height - 10}" text-anchor="middle">歩行周期（%）</text>
    <text class="chart-axis-label" transform="translate(17 ${height / 2}) rotate(-90)" text-anchor="middle">角度（°）</text>
  </svg>`;
}

