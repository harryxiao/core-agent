# 提案 — WebUI 设置页（Svelte SPA + Tauri 壳 + sidecar 拉起）（change 0100）

## Why

规格「LLM API 可配置」的场景以**「用户打开 Web 或桌面设置页」**起头，而本仓**至今没有任何前端产物**：

- `ui/spec.md:91` 已把栈定死（**实现：Svelte SPA**），`ui/spec.md:105` 定「实现：Tauri 壳 + sidecar」，
  ADR-0014 / ADR-0015 亦已决；但 `frontend/` 与 `src-tauri/` **均不存在**（change `0003` 只交付了后端 API 层）。
- `fastapi_serve.build_app`（`fastapi_serve.py:40`）**未 mount 任何静态文件** ⇒ `core-agent serve` 打开
  `http://host:port/` 是 404，设置页无处可点。
- `DesktopBridge._default_start`（`desktop_bridge.py:34`）**直接 raise**「sidecar 拉起未接」，
  `entry._app`（`entry.py:400`）走它 ⇒ `core-agent app` 必然失败（账本 C8 的代码半）。

于是 0098（可配）与 0099（可热更 + 可落盘）**没有可用入口**：改配置只能手写 yaml 或 `curl`。
本项补齐「点得着的界面」+ 桌面壳的 sidecar 拉起。

## What Changes

- **`frontend/`（新建）** —— Svelte + Vite 单 SPA，产物 `frontend/dist/`：
  - **会话页**：`POST /session` 建会话 → `POST /run` 消费 SSE 流（`reply_delta` 增量渲染、
    `loop.error` 显式报错），复刻 CLI 的流式体验。
  - **设置页**：LLM provider / model / endpoint / api_key_ref（**只收 `${VAR}` 引用，明文拒收**）/
    reasoning_effort / embedding_model / **context_window / output_reserve / max_rounds** → `PUT /llm-config`；
    以 `GET /llm-config` 的**生效值** `token_budget` 回显「窗口配了有没有生效」。
- **`fastapi_serve.build_app` 挂载 SPA 产物**：`frontend/dist` 存在 ⇒ `StaticFiles(html=True)` 挂到 `/`；
  **不存在 ⇒ 保持纯 API 模式**（后端可独立验收，不硬依赖前端产物 —— 同「可选依赖」口径）。
- **`src-tauri/`（新建）** —— Tauri 壳只做三件事（ADR-0015）：开窗口 / 挂同一 SPA 产物 / 启 sidecar。
- **`DesktopBridge` sidecar 拉起（账本 C8 代码半）**：`_default_start` 由 raise 改为 **spawn 本地后端进程**
  （`python -m core.entry serve` 同款 sidecar），`entry._app` 注入 `start_impl`；可离线验证
  （假可执行体断言 spawn 参数）。
- **`.gitignore`** 增 `node_modules/`、`frontend/dist/`、`src-tauri/target/`（构建产物不入库）。
- **文档**：`doc/06-ui-frontend/ui-architecture.md` 由「提案」转「已落地」口径；
  `doc/05-development/development-guide.md` 加前端构建命令。

## Non-goals

- **不做 TTS**（账本 C7，与「LLM 配置可生效」无因果；真实 TTS 后端仍缺）。
- **不做多模态上传 / 语音输入前端**（`ui/spec.md` 有需求，但依赖模型能力探测，另案）。
- **不引入 UI 组件库 / 状态管理库**（Svelte + 原生 fetch 足够；少一层三方依赖）。
- **不打安装包**（Windows/macOS/Linux 安装文件需各平台工具链，属发布动作非本仓开发动作）。

## 风险

- **前端不在四门内**（本仓无 JS 测试基建）⇒ 前端正确性靠 `npm run build` 通过 + 后端对**静态挂载契约**
  的 pytest 覆盖；设置页与 API 的字段一致性靠 `GET`/`PUT` 契约测试兜底。
- **Tauri 构建需系统 WebView 依赖**（Linux 侧 `webkit2gtk`）⇒ 若本机缺依赖，`cargo check` 失败属**环境**问题；
  壳配置（窗口 / SPA 挂载 / sidecar 命令）仍以文件形式交付并可被复审。
- **`/` 挂载与既有 REST 路由共存**：`StaticFiles(html=True)` 挂在最后且**不吞** `/session` 等前缀路由
  （FastAPI/Starlette 按注册顺序优先匹配显式路由），测试须锁死「挂载后既有端点仍可达」。
