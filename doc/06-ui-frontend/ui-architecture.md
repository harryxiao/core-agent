# CORE-Harness UI 界面与启动模式设计（CLI / Web / Desktop）

> 状态：**Web SPA 与 Tauri 壳已落地**（change `0100`）；CLI（Textual）与语音（§5）仍为提案。
> 关联 OpenSpec change `0003-ui-frontend` / `0100-ui-settings-spa` · ADR-0013 ~ 0015、ADR-0093
> 定位：core-agent 的三模启动层——同一内核、同一配置源、三种入口。
>
> 落地位置：前端 `frontend/`（Svelte + Vite，产物 `frontend/dist/` 由 `fastapi_serve.build_app`
> 挂站点根）；桌面壳 `src-tauri/`（Tauri v2，只做开窗口 / 挂 SPA / 启 sidecar）；sidecar 拉起实现于
> `ui/desktop_bridge.py`。**Rust 壳未纳入四门构建验证**（见 ADR-0093 §限制）。

---

## 0. 目标与背景

core-agent 内核（loop / memory / tool-use / mcp / evolution / permission / …）目前只有"代码级"入口。
本设计为它补齐三种用户可感知的启动模式，且三者共享同一内核与同一 LLM 配置：

| 模式 | 入口 | 体验 |
|---|---|---|
| CLI | `core-agent` | 终端交互（Claude Code 式 Ink 友好体验） |
| Web | `core-agent serve` | 浏览器访问，UI 内可配置 LLM API |
| Desktop | `core-agent.app` | 可打包安装的可执行文件，UI 内可配置 LLM API |

**一条硬约束**：三种模式复用同一套内核与配置，不各自维护一份实现。

---

## 1. 需求摘要

1. **CLI 启动模式**：终端里像 Claude Code（Ink）那样友好交互——折叠块、流式输出、多面板、焦点管理、行内 diff 高亮。
2. **Web 启动模式**：本地起 HTTP 服务，浏览器打开 SPA，可视化会话 + 流式输出 + **UI 内配置 LLM API**（provider / endpoint / key / base URL）。
3. **桌面启动模式**：打包成可执行安装文件（Windows / macOS / Linux），同样 UI 内可配置 LLM API，且与 Web 体验 **100% 一致**。

---

## 2. 调研取证（开源方案与框架选型）

> 数据来源：GitHub API + npm registry + 各仓库 raw 抓取，stars 为取证时点值。

### 2.1 TUI 框架选型

| 框架 | Stars | 语言 | 定位 | 对 core-agent 适配 |
|---|---|---|---|---|
| **Ink** | 39.9k | TypeScript/React | React for CLI（Claude Code 同款） | ❌ Node 运行时，需与 Python 后端跨语言桥接 |
| **Textual** | 37.3k | **Python** | 声明式/响应式 TUI（Rich 团队） | ✅ **同进程零桥接，首选** |
| Rich | 57.4k | Python | 富文本/表格/进度条渲染 | ✅ Textual 底层渲染引擎，作辅助 |
| Bubbletea | 45.0k | Go | Elm 架构 TUI | ❌ 跨语言 |
| Ratatui | 22.7k | Rust | 即时模式 TUI | ❌ 跨语言（Tauri 侧或用到） |

**关键事实**：Claude Code 的 npm 包 `dependencies` 为空、只发布平台二进制（`@anthropic-ai/claude-code-linux-x64` 等），
说明其 Ink/React **全部被打包进原生二进制**。因此 core-agent 不应照搬 Ink（需 Node 运行时），
而应取 Ink 的"声明式 + 响应式"交互哲学，用 Python 原生对应物 **Textual** 复刻。

### 2.2 现成 Web UI 开源方案

| 项目 | Stars | 后端 | 前端 | 定位 | 能否直接复用 |
|---|---|---|---|---|---|
| **Open WebUI** | 152.5k | **Python FastAPI 0.136** | SvelteKit | LLM 聊天 Web UI | ⚠️ 后端同栈最贴合，但是**完整产品**非可嵌入库 |
| **Cherry Studio** | ~52k | 本地 Electron | TypeScript | 桌面多模型客户端 | ⚠️ 桌面打包的**最佳参考案例** |
| Lobe Chat | 82.6k | Node | TypeScript | 聊天 UI 框架 | ❌ 前端可参考，后端不同栈 |
| LibreChat | 44.4k | Node | TypeScript | ChatGPT 克隆 | ❌ 同上 |
| Dify | ~156k | Python | TypeScript | 工作流编排平台 | ❌ 偏工作流，非通用 UI 层 |

**结论**：**不存在可直接嵌入 core-agent 作为 Web 界面的框架**——以上全是自带后端/数据模型/认证体系的独立应用，
硬嵌 = 改造 Fork 成本 > 自研。但有两个高价值参照：
- **Open WebUI** 证明「Python 后端 + Svelte 前端」架构成熟可行，且与 core-agent 同栈；
- **Cherry Studio** 证明「Electron + 前端 SPA 打桌面包」路径成熟。

### 2.3 桌面打包框架

| 维度 | Electron | Tauri |
|---|---|---|
| Stars | 123.2k | ~111k |
| 内核 | 自带 Chromium + Node | Rust + 系统 WebView |
| 体积 | ~100MB+ | ~3–10MB |
| 内存 | 高 | 低 |
| 前端复用 | 打包即 SPA | 打包即 SPA（可 sidecar 后端） |

---

## 3. 总体架构（三模一张图）

```
            ┌──────────────────────────────────────────────┐
            │        单一 SPA 前端（一份代码）                 │
            │   会话 / 流式输出 / 用量 / 设置(LLM API) / 会话管理 │
            └───────────────────┬──────────────────────────┘
                                │ HTTP + SSE（流式）
            ┌───────────────────▼──────────────────────────┐
            │    core-agent 后端 API 层（FastAPI）          │
            │    loop / memory / tool-use / mcp / …         │
            │    LLM 配置源 = config.yaml + settings.local  │
            └───────────────────┬──────────────────────────┘
                                │ 同内核 · 同配置
   ┌────────────────────────────┼────────────────────────────┐
   │                            │                            │
┌──▼─────────────┐      ┌───────▼───────┐      ┌─────────────▼─────┐
│ ① CLI          │      │ ② Web         │      │ ③ Desktop         │
│ core-agent     │      │ core-agent    │      │ core-agent.app    │
│ Textual TUI    │      │ serve → 浏览器 │      │ Tauri 壳 + SPA     │
│ 直连内核 API   │      │ 打开 SPA      │      │ sidecar 拉起后端   │
└────────────────┘      └───────────────┘      └───────────────────┘
```

---

## 4. 各模式设计

### 4.1 CLI（Textual）

- **组件化**：`Widget`/`Compose`/`App`，对应 Ink 的 React 组件树。
- **响应式**：`@reactive` 装饰器 + CSS 样式系统，做折叠块、行内 diff 高亮、多面板分栏、滚动缓冲。
- **斜杠命令提示**：输入 `/` 触发命令自动补全（命令面板），候选来自内核 plugin-registry 注册的 command/tool 元数据（经统一 API 的 `list_tools` 拉取），属 UI 层输入组件交互、不进内核接口。
- **纯 Python**：与内核同进程直接 import，无 IPC 成本；调用同一后端 API 层，保证行为/鉴权/日志一致。
- 目录规划：`src/cli/`（`app.py` + `widgets/` + `bridge.py`）。

### 4.2 Web（FastAPI + 单 SPA）

- 后端：FastAPI 暴露 loop/session/memory/tools 接口 + SSE 流式（复用内核）。
- 前端：单一 SPA（推荐 Svelte 或 React），chat / 会话管理 / 用量 / 设置（LLM API 配置）页。
- 参考：Open WebUI 的同栈架构成熟经验。
- **任务区（change `0122`）**：`POST /task` 以 SSE 外发 `task.*` 进度事件（与 CLI `/task` 同编排器同事件面）；
  SPA 右栏在**会话列表之上**新增**任务区**块 —— 二者**并列不混池**（任务 = **在途**运行态、会话 = **持久**记录），
  子任务行呈现标题 + 状态徽标 + 可展开详情；任务收尾（`task_finished` / `task_failed`）即**移出在途列表**
  （回落），**不**进入会话列表。「进入子 agent 会话 / 主-子焦点切换」不在其中（子 agent 消息流无数据源）。

### 4.3 Desktop（Tauri 壳）

- 壳职责最小化：开窗口 + 挂载 SPA + sidecar 拉起 Python 后端。
- **与 Web 复用同一 SPA 构建产物**，实现桌面/Web 体验 100% 一致。
- sidecar 由 Tauri 官方机制管理，随应用打包（Windows / macOS / Linux）。

---

## 5. 实时语音输出交互设计（全双工 · barge-in · 流式 TTS）

> 关联 OpenSpec change `0014-voice-output`。语音输出是**全双工、三模共享的跨模式交互能力**，不归入 §4 任一单模小节，独立成节。

1. **全双工（Full-Duplex）**：麦克风采集（ASR 输入通道）与 TTS 播报（输出通道）同时进行、互不阻塞，支持"边说边听"；音频链路 ASR → 内核 loop → 流式 TTS，与 §3 的 HTTP + SSE 文本流并存，同走统一后端 API。

2. **barge-in 打断**：用户开口即由 VAD 触发，立即中止当前 TTS 播报与正在生成的 token（软取消），实现"随时插话"；打断仅终止语音/文本生成，已执行工具结果保留归档、避免重复执行，打断状态机在**内核/后端统一**、三模共用。

3. **流式播报**：TTS 按句子/短片段分片合成、随 token 边生成边播，降低首字延迟；与 SSE 流式输出对齐，TTS 即流式输出的音频投影。

4. **三模 CLI / Web / Desktop 差异（差异仅在音频前端，状态机/协议后端统一）**：
   - **CLI（Textual）**：终端无原生音频，经系统音频后端（afplay / aplay / pw-play 等）播放，或降级为文本提示；按键触发打断。
   - **Web**：浏览器 Web Audio / SpeechSynthesis 播报，`getUserMedia` + VAD 做 barge-in；首次需麦克风授权。
   - **Desktop（Tauri）**：复用同一 SPA 构建产物，音频能力与 Web **零差异**，桌面壳仅保证系统音频权限与扬声器设备。
   - **统一面**：打断状态机、流式 TTS 分片协议、会话级 TTS 开关均在后端 API 层统一定义，三模仅音频前端实现不同。

---

## 6. 四条设计原则（保证 100% 一致）

1. **前端单一代码库**：Web 与桌面跑完全相同的 SPA 构建产物，桌面只是换个壳。
2. **桌面壳职责最小化**：Tauri 只做开窗口 / 挂 SPA / 启 sidecar 三件事。
3. **统一 API 解耦**：三种模式都走同一套后端 API（HTTP + SSE）；CLI 的 Textual 层也调同一 API，不绕过。
4. **单一配置源**：LLM API Key 等只在后端 `config.yaml` + `settings.local.json` 配置一次，三模不重复配置。

---

## 7. 分阶段落地路径

| 阶段 | 交付 | 说明 |
|---|---|---|
| P1 | 后端 API 层 | ✅ 已落地：FastAPI 暴露 loop/session/memory/tools + SSE 流式；CLI 直连内核先跑通 |
| P2 | Web SPA | 🟡 已落地（`0100`，`0116`）：会话（chat + SSE + **右栏会话列表 / 切换 / 历史**）/ **设置（LLM API 配置）** 两页；会话**重命名 / 删除**、用量页未做 |
| P3 | Tauri 桌面壳 | 🟡 壳与 sidecar 已落地（`0100`）；**打包安装包未验证**（未入四门） |
| P4 | Textual CLI | ⬜ 未做：复刻 Ink 式交互（折叠块 / diff 高亮 / 多面板 / 焦点管理） |

---

## 8. 技术决策记录（ADR 索引）

| ADR | 决策 |
|---|---|
| ADR-0013 | CLI 采用 Textual（Python 原生）复刻 Ink 式交互 |
| ADR-0014 | Web 采用自研单 SPA + 统一 API（不嵌入现成开源产品） |
| ADR-0015 | 桌面端采用 Tauri 壳复用 SPA + sidecar 后端 |

---

## 9. 三模方案一句话总结

| 模式 | 技术 | 复用度 |
|---|---|---|
| CLI | Textual（Python 原生 Ink 对应物） | 内核 100% 复用，UI 层自研 |
| Web | FastAPI 后端 + SPA（参考 Open WebUI） | 后端 + 前端 100% 复用 |
| Desktop | Tauri 壳 + 同一 SPA + sidecar 后端（参考 Cherry Studio） | SPA 100% 复用 |
