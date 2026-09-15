import type { CaptureConditions, Patient, VideoStudy } from "../domain/models";
import { analyzeGait } from "../analysis/gaitAnalysis";
import type { GaitAnalysisResult } from "../analysis/types";
import { compareCaptureConditions, previousReadyStudy } from "../capture/captureConditions";
import { nearestPoseFrame, SkeletonRenderer } from "../overlay/SkeletonRenderer";
import { MotionLabDatabase } from "../storage/database";
import { VideoPoseAnalyzer } from "../video/VideoPoseAnalyzer";
import { AnalysisResultsView } from "./AnalysisResultsView";
import { CaptureGuide } from "./CaptureGuide";

export class App {
  private readonly database = new MotionLabDatabase();
  private patients: Patient[] = [];
  private videos: VideoStudy[] = [];
  private selectedPatientId: string | null = null;
  private selectedVideoId: string | null = null;
  private objectUrl: string | null = null;
  private analyzer: VideoPoseAnalyzer | null = null;
  private videoFrameHandle: number | null = null;
  private overlayResizeObserver: ResizeObserver | null = null;
  private viewerTab: "video" | "analysis" = "video";
  private readonly gaitAnalysisCache = new Map<string, GaitAnalysisResult>();
  private captureGuide: CaptureGuide | null = null;

  constructor(private readonly root: HTMLElement) {}

  async start(): Promise<void> {
    this.renderShell();
    this.captureGuide = new CaptureGuide(this.root);
    this.bindGlobalActions();
    try {
      this.patients = await this.database.listPatients();
      if (this.patients[0]) await this.selectPatient(this.patients[0].id);
      else this.renderContent();
      void this.database.requestPersistence();
    } catch (error) {
      this.showGlobalError(error);
    }
  }

  private renderShell(): void {
    this.root.innerHTML = `
      <header class="app-header">
        <div class="brand"><div class="brand-mark" aria-hidden="true">ML</div><div>
          <h1>MotionLab Gait</h1><p>Local-first gait video workspace</p>
        </div></div>
        <div class="header-actions">
          <span class="privacy-pill">外部送信なし・端末内処理</span>
          <span id="network-status" class="network-pill" aria-live="polite"></span>
        </div>
      </header>
      <p id="ios-install-hint" class="ios-install-hint" hidden>
        Safariの共有ボタンから「ホーム画面に追加」すると、保存が安定しアプリのように使えます。
      </p>
      <div class="layout">
        <aside class="panel sidebar">
          <div class="sidebar-header"><h2 class="sidebar-title">患者</h2>
            <button id="new-patient" class="button secondary small" type="button">＋ 登録</button>
          </div>
          <div id="patient-list" class="patient-list"></div>
        </aside>
        <main id="main" class="panel main"></main>
      </div>
      <dialog id="patient-dialog">
        <form id="patient-form" class="dialog-body" method="dialog">
          <h2>患者を登録</h2>
          <div class="field"><label for="patient-code">患者ID（必須）</label>
            <input id="patient-code" name="patientCode" required maxlength="40" autocomplete="off" />
          </div>
          <div class="field"><label for="display-name">表示名（任意）</label>
            <input id="display-name" name="displayName" maxlength="60" autocomplete="off" />
          </div>
          <div class="field"><label for="patient-note">メモ（任意）</label>
            <textarea id="patient-note" name="note" maxlength="500" rows="3"></textarea>
          </div>
          <div class="field"><label for="affected-side">麻痺側（任意）</label>
            <select id="affected-side" name="affectedSide"><option value="none">未設定</option><option value="left">左</option><option value="right">右</option></select>
          </div>
          <p id="patient-form-error" class="notice error" hidden></p>
          <div class="dialog-actions">
            <button id="cancel-patient" class="button ghost" type="button">キャンセル</button>
            <button class="button" type="submit">登録する</button>
          </div>
        </form>
      </dialog>
    `;
  }

  private bindGlobalActions(): void {
    const dialog = this.requireElement<HTMLDialogElement>("patient-dialog");
    this.requireElement("new-patient").addEventListener("click", () => dialog.showModal());
    this.requireElement("cancel-patient").addEventListener("click", () => dialog.close());
    this.requireElement<HTMLFormElement>("patient-form").addEventListener("submit", (event) => {
      event.preventDefault();
      void this.createPatient(dialog);
    });
    const updateNetwork = () => {
      const element = this.requireElement("network-status");
      element.textContent = navigator.onLine ? "オンライン" : "オフライン";
      element.classList.toggle("offline", !navigator.onLine);
    };
    window.addEventListener("online", updateNetwork);
    window.addEventListener("offline", updateNetwork);
    updateNetwork();
    const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    this.requireElement<HTMLElement>("ios-install-hint").hidden = !isAppleMobile
      || window.matchMedia("(display-mode: standalone)").matches;
  }

  private async createPatient(dialog: HTMLDialogElement): Promise<void> {
    const form = this.requireElement<HTMLFormElement>("patient-form");
    const data = new FormData(form);
    const patientCode = String(data.get("patientCode") ?? "").trim();
    const displayName = String(data.get("displayName") ?? "").trim();
    const note = String(data.get("note") ?? "").trim();
    const affectedSide = String(data.get("affectedSide") ?? "none") as Patient["affectedSide"];
    const errorElement = this.requireElement("patient-form-error");
    if (!patientCode) return;
    if (this.patients.some((item) => item.patientCode.toLocaleLowerCase() === patientCode.toLocaleLowerCase())) {
      errorElement.textContent = "同じ患者IDがすでに登録されています。";
      errorElement.hidden = false;
      return;
    }
    const patient: Patient = {
      id: crypto.randomUUID(), patientCode, displayName, note, affectedSide,
      createdAt: new Date().toISOString()
    };
    try {
      await this.database.savePatient(patient);
      this.patients = await this.database.listPatients();
      form.reset();
      errorElement.hidden = true;
      dialog.close();
      await this.selectPatient(patient.id);
    } catch (error) {
      errorElement.textContent = this.errorMessage(error);
      errorElement.hidden = false;
    }
  }

  private async selectPatient(patientId: string): Promise<void> {
    this.selectedPatientId = patientId;
    this.videos = await this.database.listVideos(patientId);
    this.selectedVideoId = this.videos[0]?.id ?? null;
    this.viewerTab = "video";
    this.renderPatientList();
    this.renderContent();
  }

  private renderPatientList(): void {
    const list = this.requireElement("patient-list");
    list.replaceChildren();
    if (!this.patients.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "患者を登録してください";
      list.append(empty);
      return;
    }
    for (const patient of this.patients) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `patient-card${patient.id === this.selectedPatientId ? " active" : ""}`;
      const code = document.createElement("strong");
      code.textContent = patient.patientCode;
      const name = document.createElement("span");
      name.textContent = patient.displayName || "表示名なし";
      button.append(code, name);
      button.addEventListener("click", () => void this.selectPatient(patient.id));
      list.append(button);
    }
  }

  private renderContent(): void {
    this.releaseOverlay();
    this.releaseObjectUrl();
    this.renderPatientList();
    const main = this.requireElement("main");
    const patient = this.patients.find((item) => item.id === this.selectedPatientId);
    if (!patient) {
      main.innerHTML = `<section class="hero-empty"><div class="hero-empty-inner">
        <h2>歩行動画を、端末の中だけで。</h2>
        <p>患者を登録すると、iPhone・iPad・PCから動画を撮影または選択し、33点PoseとSkeletonを確認できます。</p>
        <button id="empty-new-patient" class="button" type="button">最初の患者を登録</button>
      </div></section>`;
      this.requireElement("empty-new-patient").addEventListener("click", () =>
        this.requireElement<HTMLDialogElement>("patient-dialog").showModal()
      );
      return;
    }

    main.innerHTML = `
      <div class="patient-heading"><div><h2 id="patient-heading"></h2><p id="patient-note"></p></div>
        <div class="video-actions">
          <button id="capture-video" class="button" type="button">カメラで撮影</button>
          <input id="video-capture" class="sr-only" type="file" accept="video/*" capture="environment" />
          <button id="select-video" class="button secondary" type="button">動画を選択</button>
          <input id="video-input" class="sr-only" type="file" accept="video/mp4,video/quicktime,video/x-m4v,video/*" />
          <button id="capture-manual" class="button ghost" type="button">撮影方法</button>
        </div>
      </div>
      <div class="workflow">
        <section class="study-column"><h3 class="section-title">保存動画</h3><div id="study-list" class="study-list"></div></section>
        <section id="viewer" class="viewer-column"></section>
      </div>
    `;
    this.requireElement("patient-heading").textContent = patient.displayName
      ? `${patient.patientCode}　${patient.displayName}` : patient.patientCode;
    this.requireElement("patient-note").textContent = patient.note || "患者メモなし";
    const captureInput = this.requireElement<HTMLInputElement>("video-capture");
    let captureConditions = defaultCaptureConditions();
    this.requireElement("capture-video").addEventListener("click", () => {
      this.captureGuide?.openForCapture(patient, (conditions) => {
        captureConditions = conditions;
        captureInput.click();
      });
    });
    captureInput.addEventListener("change", () => {
      const file = captureInput.files?.[0];
      if (file) void this.importVideo(file, captureConditions).finally(() => { captureInput.value = ""; });
    });
    const videoInput = this.requireElement<HTMLInputElement>("video-input");
    let selectionConditions = defaultCaptureConditions();
    this.requireElement("select-video").addEventListener("click", () => {
      this.captureGuide?.openForVideoSelection(patient, (conditions) => {
        selectionConditions = conditions;
        videoInput.click();
      });
    });
    videoInput.addEventListener("change", () => {
      const file = videoInput.files?.[0];
      if (file) void this.importVideo(file, selectionConditions).finally(() => { videoInput.value = ""; });
    });
    this.requireElement("capture-manual").addEventListener("click", () => this.captureGuide?.openManual());
    this.renderStudyList();
    this.renderViewer();
  }

  private renderStudyList(): void {
    const list = this.requireElement("study-list");
    list.replaceChildren();
    if (!this.videos.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "まだ動画がありません";
      list.append(empty);
      return;
    }
    for (const video of this.videos) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `study-item${video.id === this.selectedVideoId ? " active" : ""}`;
      const name = document.createElement("strong");
      name.textContent = video.originalName;
      const meta = document.createElement("span");
      meta.className = "study-meta";
      const date = document.createElement("span");
      date.textContent = new Intl.DateTimeFormat("ja-JP", { dateStyle: "short", timeStyle: "short" }).format(new Date(video.createdAt));
      const status = document.createElement("span");
      status.className = `status ${video.status}`;
      status.textContent = statusLabel(video.status);
      meta.append(date, status);
      button.append(name, meta);
      button.addEventListener("click", () => {
        this.selectedVideoId = video.id;
        this.viewerTab = "video";
        this.renderContent();
      });
      list.append(button);
    }
  }

  private renderViewer(): void {
    const viewer = this.requireElement("viewer");
    const study = this.videos.find((item) => item.id === this.selectedVideoId);
    if (!study) {
      viewer.innerHTML = `<div class="video-stage"><div class="viewer-placeholder">動画を撮影または選択してください<br />推奨：真横・全身・足先まで画面内</div></div>
        <p class="notice">本アプリは診断装置ではありません。動画とSkeletonを確認し、結果を単独で治療判断に使用しないでください。</p>`;
      return;
    }
    const tabs = study.status === "ready" ? `<div class="viewer-tabs" role="tablist" aria-label="動画表示">
      <button id="video-view-tab" class="viewer-tab${this.viewerTab === "video" ? " active" : ""}" type="button" role="tab" aria-selected="${this.viewerTab === "video"}" aria-controls="video-view-panel">動画・Skeleton</button>
      <button id="analysis-view-tab" class="viewer-tab${this.viewerTab === "analysis" ? " active" : ""}" type="button" role="tab" aria-selected="${this.viewerTab === "analysis"}" aria-controls="analysis-view-panel">解析結果</button>
    </div>` : "";
    viewer.innerHTML = `${tabs}
      <div id="video-view-panel" class="viewer-panel" role="tabpanel" ${this.viewerTab === "analysis" && study.status === "ready" ? "hidden" : ""}>
        <div class="video-stage">
          <video id="player" controls playsinline webkit-playsinline preload="metadata"></video>
          <canvas id="skeleton-canvas" aria-hidden="true"></canvas>
        </div>
        <div id="analysis-progress" class="progress-box" hidden>
          <div class="progress-row"><span id="progress-message">準備中</span><span id="progress-percent">0%</span></div>
          <progress id="progress-bar" value="0" max="1"></progress>
          <button id="cancel-analysis" class="button ghost small" type="button">解析を中止</button>
        </div>
        <div id="result-summary"></div>
      </div>
      ${study.status === "ready" ? `<div id="analysis-view-panel" class="viewer-panel" role="tabpanel" ${this.viewerTab === "video" ? "hidden" : ""}></div>` : ""}`;
    const player = this.requireElement<HTMLVideoElement>("player");
    this.objectUrl = URL.createObjectURL(study.video);
    player.src = this.objectUrl;
    if (study.status === "ready") this.attachOverlay(player, study);
    this.renderResultSummary(study);
    if (study.status === "ready") {
      this.requireElement("video-view-tab").addEventListener("click", () => this.selectViewerTab("video", study));
      this.requireElement("analysis-view-tab").addEventListener("click", () => this.selectViewerTab("analysis", study));
      if (this.viewerTab === "analysis") this.renderAnalysisResults(study);
    }
  }

  private selectViewerTab(tab: "video" | "analysis", study: VideoStudy): void {
    this.viewerTab = tab;
    const videoTab = this.requireElement<HTMLButtonElement>("video-view-tab");
    const analysisTab = this.requireElement<HTMLButtonElement>("analysis-view-tab");
    const videoPanel = this.requireElement<HTMLElement>("video-view-panel");
    const analysisPanel = this.requireElement<HTMLElement>("analysis-view-panel");
    videoTab.classList.toggle("active", tab === "video");
    analysisTab.classList.toggle("active", tab === "analysis");
    videoTab.setAttribute("aria-selected", String(tab === "video"));
    analysisTab.setAttribute("aria-selected", String(tab === "analysis"));
    videoPanel.hidden = tab !== "video";
    analysisPanel.hidden = tab !== "analysis";
    if (tab === "analysis") this.renderAnalysisResults(study);
  }

  private renderAnalysisResults(study: VideoStudy): void {
    const panel = this.requireElement("analysis-view-panel");
    const result = this.getGaitAnalysis(study);
    new AnalysisResultsView(panel, result).render();
  }

  private getGaitAnalysis(study: VideoStudy): GaitAnalysisResult {
    let result = this.gaitAnalysisCache.get(study.id);
    if (!result) {
      result = analyzeGait(study.poseFrames, {
        videoMetadata: study.videoMetadata,
        cameraSide: study.captureConditions?.cameraSide
      });
      this.gaitAnalysisCache.set(study.id, result);
    }
    return result;
  }

  private renderResultSummary(study: VideoStudy): void {
    const container = this.requireElement("result-summary");
    if (study.status === "failed") {
      container.innerHTML = `<p class="notice error"></p>`;
      const notice = container.querySelector("p");
      if (notice) notice.textContent = study.error;
      return;
    }
    if (study.status !== "ready") {
      container.innerHTML = `<p class="notice">Pose解析の開始を待っています。</p>`;
      return;
    }
    const detected = study.poseFrames.filter((frame) => frame.landmarks.length === 33).length;
    const detectionRate = study.poseFrames.length ? (100 * detected / study.poseFrames.length).toFixed(1) : "0.0";
    const result = this.getGaitAnalysis(study);
    const quality = result.acquisitionQuality;
    const qualityLabel = { high: "高", caution: "注意", retake: "撮り直し推奨" }[quality.status];
    const metadata = study.videoMetadata;
    const previousStudy = previousReadyStudy(study, this.videos);
    const comparison = previousStudy ? compareCaptureConditions(study, previousStudy) : null;
    container.innerHTML = `<div class="capture-quality ${quality.status}">
      <div><span>撮影品質</span><strong>${qualityLabel}</strong></div>
      ${quality.reasons.length ? `<ul>${quality.reasons.map((reason) => `<li>${reason}</li>`).join("")}</ul>` : `<p>側方性・足部追跡・歩行周期を確認できました。</p>`}
    </div>
    <div class="result-grid">
      <div class="metric"><span>Poseフレーム</span><strong>${study.poseFrames.length}</strong></div>
      <div class="metric"><span>33点検出率</span><strong>${detectionRate}%</strong></div>
      <div class="metric"><span>解析fps</span><strong>${metadata ? metadata.estimatedFps.toFixed(1) : "—"}</strong></div>
    </div>
    ${renderCaptureConditions(study)}
    ${comparison ? renderConditionComparison(comparison.status, comparison.differences) : ""}
    <p class="notice">${quality.status === "retake" ? "正確な解析が難しいため、撮り直しをおすすめします。" : "再生・停止・シークにSkeletonが追従します。関節角度は「解析結果」タブで確認できます。"}</p>
    ${quality.status === "retake" ? `<div class="qc-actions"><button id="retake-video" class="button" type="button">撮り直す</button><button id="qc-view-manual" class="button ghost" type="button">撮影方法を見る</button></div>` : ""}`;
    if (quality.status === "retake") {
      this.requireElement("retake-video").addEventListener("click", () => this.requireElement<HTMLButtonElement>("capture-video").click());
      this.requireElement("qc-view-manual").addEventListener("click", () => this.captureGuide?.openManual());
    }
  }

  private async importVideo(file: File, captureConditions: CaptureConditions): Promise<void> {
    if (!this.selectedPatientId) return;
    if (!file.type.startsWith("video/") && !/\.(mov|mp4|m4v|webm)$/i.test(file.name)) {
      this.showGlobalError(new Error("動画ファイルを選択してください。"));
      return;
    }
    const study: VideoStudy = {
      id: crypto.randomUUID(), patientId: this.selectedPatientId, originalName: file.name,
      createdAt: new Date().toISOString(), durationMs: 0, status: "pending", error: "",
      video: file, poseFrames: [], schema: "motionlab.pose.v1",
      analysisVersion: "motionlab-gait-web/0.3.0", captureConditions
    };
    try {
      await this.database.saveVideo(study);
      this.videos = await this.database.listVideos(this.selectedPatientId);
      this.selectedVideoId = study.id;
      this.renderContent();
      await this.analyzeStudy(study);
    } catch (error) {
      this.showGlobalError(error);
    }
  }

  private async analyzeStudy(study: VideoStudy): Promise<void> {
    this.analyzer = new VideoPoseAnalyzer();
    study.status = "analyzing";
    this.renderStudyList();
    const progressBox = this.requireElement<HTMLElement>("analysis-progress");
    progressBox.hidden = false;
    this.requireElement("cancel-analysis").addEventListener("click", () => this.analyzer?.cancel());
    try {
      const result = await this.analyzer.analyze(study.video, ({ completed, total, message }) => {
        const ratio = total ? completed / total : 0;
        this.requireElement("progress-message").textContent = message;
        this.requireElement("progress-percent").textContent = `${Math.round(ratio * 100)}%`;
        this.requireElement<HTMLProgressElement>("progress-bar").value = ratio;
      });
      study.status = "ready";
      study.durationMs = result.durationMs;
      study.poseFrames = result.frames;
      study.videoMetadata = result.metadata;
      study.analysisVersion = "motionlab-gait-web/0.3.0";
      study.error = "";
      this.gaitAnalysisCache.delete(study.id);
    } catch (error) {
      study.status = "failed";
      study.error = this.errorMessage(error);
    } finally {
      this.analyzer = null;
      await this.database.saveVideo(study);
      if (this.selectedPatientId) this.videos = await this.database.listVideos(this.selectedPatientId);
      this.renderContent();
    }
  }

  private attachOverlay(player: HTMLVideoElement, study: VideoStudy): void {
    const canvas = this.requireElement<HTMLCanvasElement>("skeleton-canvas");
    const renderer = new SkeletonRenderer(canvas);
    const draw = () => renderer.draw(nearestPoseFrame(study.poseFrames, player.currentTime * 1000), player);
    const frameLoop = () => {
      if (!player.isConnected) return;
      draw();
      if (typeof player.requestVideoFrameCallback === "function") {
        this.videoFrameHandle = player.requestVideoFrameCallback(frameLoop);
      }
    };
    player.addEventListener("loadeddata", () => {
      draw();
      if (typeof player.requestVideoFrameCallback === "function") {
        this.videoFrameHandle = player.requestVideoFrameCallback(frameLoop);
      }
    }, { once: true });
    player.addEventListener("seeked", draw);
    player.addEventListener("timeupdate", draw);
    this.overlayResizeObserver = new ResizeObserver(draw);
    this.overlayResizeObserver.observe(player);
  }

  private showGlobalError(error: unknown): void {
    const main = this.requireElement("main");
    const notice = document.createElement("p");
    notice.className = "notice error";
    notice.textContent = this.errorMessage(error);
    main.prepend(notice);
  }

  private errorMessage(error: unknown): string {
    if (error instanceof DOMException && error.name === "QuotaExceededError") {
      return "端末の保存容量が不足しています。ブラウザの空き容量を確認してください。";
    }
    return error instanceof Error ? error.message : "処理中にエラーが発生しました。";
  }

  private releaseObjectUrl(): void {
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
  }

  private releaseOverlay(): void {
    const player = document.getElementById("player") as HTMLVideoElement | null;
    if (player && this.videoFrameHandle !== null && typeof player.cancelVideoFrameCallback === "function") {
      player.cancelVideoFrameCallback(this.videoFrameHandle);
    }
    this.videoFrameHandle = null;
    this.overlayResizeObserver?.disconnect();
    this.overlayResizeObserver = null;
  }

  private requireElement<T extends HTMLElement = HTMLElement>(id: string): T {
    const element = document.getElementById(id);
    if (!element) throw new Error(`画面要素 ${id} が見つかりません。`);
    return element as T;
  }
}

function statusLabel(status: VideoStudy["status"]): string {
  return { pending: "未解析", analyzing: "解析中", ready: "Pose完了", failed: "エラー" }[status];
}

function defaultCaptureConditions(): CaptureConditions {
  return { gaitMode: "unspecified", orthosis: "unspecified", walkingAid: "unspecified", cameraSide: "unspecified" };
}

function renderCaptureConditions(study: VideoStudy): string {
  const conditions = study.captureConditions;
  if (!conditions || [conditions.gaitMode, conditions.orthosis, conditions.walkingAid, conditions.cameraSide].includes("unspecified")) {
    return `<p class="capture-condition-summary muted">撮影条件：記録なし</p>`;
  }
  const gait = conditions.gaitMode === "comfortable" ? "快適歩行" : "最大歩行";
  const orthosis = conditions.orthosis === "none" ? "装具なし" : "装具あり";
  const aid: Record<CaptureConditions["walkingAid"], string> = {
    none: "補助具なし", cane_single: "T字杖", cane_multi: "多点杖", walker: "歩行器",
    other: "その他の補助具", used: "補助具あり", unspecified: "補助具未記録"
  };
  const camera = conditions.cameraSide === "left" ? "左をカメラ側" : "右をカメラ側";
  return `<p class="capture-condition-summary">撮影条件：${gait}・${orthosis}・${aid[conditions.walkingAid]}・${camera}</p>`;
}

function renderConditionComparison(status: "same" | "different" | "insufficient", differences: readonly string[]): string {
  if (status === "different") {
    return `<div class="condition-comparison warning"><strong>前回と撮影条件が異なります</strong><span>${differences.join("・")}</span></div>`;
  }
  if (status === "insufficient") {
    return `<div class="condition-comparison neutral"><strong>前回との撮影条件比較：記録不足</strong><span>同条件か確認できません。</span></div>`;
  }
  return `<div class="condition-comparison"><strong>前回と同じ撮影条件です</strong><span>歩行速度・装具・補助具・カメラ側・fps</span></div>`;
}
