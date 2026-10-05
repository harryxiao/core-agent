# tasks — WebUI 设置页（Svelte SPA + Tauri 壳 + sidecar 拉起）（change 0100）

## 1. 规格（先行）
- [x] 1.1 `specs/ui/spec.md`：MODIFIED「Web 界面访问」（静态挂载 + 缺产物降级 + 不遮蔽端点）
      + MODIFIED「桌面打包」（复用 SPA 产物 + sidecar 由 `DesktopBridge` 拉起）
- [x] 1.2 `openspec validate 2026-10-05-0100-ui-settings-spa` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_serve.py` 追加：缺 `dist` ⇒ 纯 API（既有端点全可达）；有 `dist` ⇒ `/` 返回 SPA
      且**既有端点不被遮蔽**
- [x] 2.2 `tests/test_ui.py`（或 `tests/test_desktop_sidecar.py`）：sidecar spawn 参数逐项、不经 shell、
      可执行体缺失 ⇒ `UI_SIDECAR_FAILED`（假可执行体，不真起服务）
- [x] 2.3 运行确认**红**（5 failed / 12 passed）

## 3. 实现
- [x] 3.1 `ui/errors.py`：`UI_SIDECAR_FAILED`（+ `_STATUS` 映射）
- [x] 3.2 `ui/desktop_bridge.py`：`_default_start` 改真实 spawn（`sys.executable -m core.entry serve`，
      列表形式、不经 shell、注入缝保留）
- [x] 3.3 `entry.py`：`_app` 分支接 `DesktopBridge`（端口/sidecar 参数从 args 取）+ `__main__` 守卫
- [x] 3.4 `ui/fastapi_serve.py`：`frontend/dist` 存在 ⇒ `StaticFiles(html=True)` 挂 `/`（**最后**注册）
- [x] 3.5 `frontend/`（新建）：Svelte + Vite（`package.json` / `vite.config.js` / `index.html` /
      `src/{main.js,App.svelte,lib/api.js,views/{Chat,Settings}.svelte}`）
- [x] 3.6 `src-tauri/`（新建）：壳配置（窗口 / SPA 产物 / sidecar 命令），最小职责
- [x] 3.7 `.gitignore`：`node_modules/` / `frontend/dist/` / `src-tauri/target/`
- [x] 3.8 构建验证：`npm ci && npm run build` ⇒ `frontend/dist/index.html` 生成；四门仍绿

## 4. 文档
- [x] 4.1 `doc/06-ui-frontend/ui-architecture.md`：状态由「提案」转「已落地」+ 落地路径标注
- [x] 4.2 `doc/05-development/development-guide.md`：前端构建命令（`npm ci && npm run build`）
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-UI-13/14（静态挂载与降级 / sidecar 拉起）
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0093（可选产物挂载 + sidecar spawn 口径）

## 5. 收口
- [x] 5.1 四门全绿（直连二进制不用 `uv run`）
- [x] 5.2 手工归档 + `openspec validate --all`
- [x] 5.3 账本 `coding-plan/phase-20.md` C8 关闭 + `phase-19.md` 补行
- [x] 5.4 记忆更新 + 提交（`feat(ui): WebUI 设置页与 Tauri 壳 sidecar（change 0100）`）
