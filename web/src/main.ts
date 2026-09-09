import { registerSW } from "virtual:pwa-register";
import "./styles.css";
import { installSameOriginFetchGuard } from "./privacy/egressGuard";
import { App } from "./ui/App";

const root = document.getElementById("app");
if (!root) throw new Error("アプリの開始位置が見つかりません。");

installSameOriginFetchGuard();

const updateServiceWorker = registerSW({
  onNeedRefresh() {
    if (window.confirm("MotionLab Gaitの更新があります。画面を再読み込みしますか？")) {
      void updateServiceWorker(true);
    }
  }
});

void new App(root).start();
