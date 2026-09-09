import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  base: "./",
  plugins: [
    VitePWA({
      registerType: "prompt",
      includeAssets: [
        "models/pose_landmarker_full.task",
        "wasm/*",
        "mediapipe/*",
        "workers/*",
        "icons/*"
      ],
      manifest: {
        name: "MotionLab Gait",
        short_name: "MotionLab Gait",
        description: "端末内で歩行動画のPoseを確認する臨床支援PWA",
        theme_color: "#0b655e",
        background_color: "#f4f7f6",
        display: "standalone",
        orientation: "any",
        start_url: "./",
        scope: "./",
        icons: [
          { src: "icons/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }
        ]
      },
      workbox: {
        maximumFileSizeToCacheInBytes: 20 * 1024 * 1024,
        globPatterns: ["**/*.{js,css,html,png,svg,task,wasm}"],
        cleanupOutdatedCaches: true,
        navigateFallback: "index.html"
      }
    })
  ],
  build: { target: "es2022" }
});
