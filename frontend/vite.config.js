import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// `base: "./"` —— 产物以**相对路径**引用资源：同一份 dist/ 既能被 FastAPI 挂在 `/`，
// 也能被 Tauri 壳以 file:// 加载（规格「Web 与桌面体验一致」的物理前提；
// 写成 `/assets/...` 在 file:// 下必 404）。
export default defineConfig({
  plugins: [svelte()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
});
