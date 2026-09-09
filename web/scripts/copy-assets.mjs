import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const publicRoot = join(root, "public");
await mkdir(join(publicRoot, "models"), { recursive: true });
await mkdir(join(publicRoot, "wasm"), { recursive: true });
await mkdir(join(publicRoot, "mediapipe"), { recursive: true });
await copyFile(
  join(root, "..", "models", "pose_landmarker_full.task"),
  join(publicRoot, "models", "pose_landmarker_full.task")
);
const wasmRoot = join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
for (const name of await readdir(wasmRoot)) {
  await copyFile(join(wasmRoot, name), join(publicRoot, "wasm", name));
}
const classicLoader = await readFile(join(wasmRoot, "vision_wasm_internal.js"), "utf8");
await writeFile(
  join(publicRoot, "wasm", "vision_wasm_classic_internal.js"),
  `${classicLoader}\n;globalThis.ModuleFactory = ModuleFactory;\n`,
  "utf8"
);
await copyFile(
  join(root, "node_modules", "@mediapipe", "tasks-vision", "vision_bundle.js"),
  join(publicRoot, "mediapipe", "vision_bundle.js")
);
