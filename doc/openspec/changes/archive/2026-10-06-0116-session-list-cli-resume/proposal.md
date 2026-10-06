# 提案 — 会话列表面板与 CLI 会话可见面（change 0116 / phase-28 E49，Change B 前端+CLI 切片）

## 背景

用户原话的后半：「**webUI 右边是会话列表管理**——记录了当前已创建会话，可以选不同的会话**查看记录**
或者**继续聊天**，相互独立。也可以继续创建新会话。」CLI 侧「类似」。

change `0115`（B1）已把**机制**补齐：转录落盘（`memory/transcript.py`）、按会话读取
（`GET /session/{id}/messages`）、枚举附派生 `title`/`updated_at`（`GET /sessions`）、本会话最近 N 轮
回灌进 prompt。**但没有任何消费方**：

| # | 一手事实 | 后果 |
|---|---|---|
| 1 | `frontend/src/lib/api.js` 只有 `getLLMConfig`/`saveLLMConfig`/`createSession`/`runStream`；**无 `listSessions`、无取历史** | SPA 从不调用 `GET /sessions`；会话列表在界面上不存在 |
| 2 | `frontend/src/views/Chat.svelte:6` `lines` 是纯内存 `$state`；`:10-15` 首条消息**惰性 `ensureSession()`** | 刷新即空白（历史不可见）；无法切换会话；「新建会话」无显式入口 |
| 3 | `frontend/src/App.svelte:28-32` 单列（`max-width: 860px`）、`{#if tab==="chat"}<Chat />` | 无右侧栏位 |
| 4 | `src/core/entry.py:232-234` `session` 只有 `create`/`list`；`src/core/ui/repl.py:193` `build_app` **硬编码** `api.create_session("cli")`，`run_repl(api)` 无会话参数 | CLI 既看不到记录，也不能「继续聊」既有会话（每次进 TUI 都是全新会话） |

⇒ 本切片把**已有机制**接到两个消费面：Web 右栏会话列表、CLI `session show` + REPL 续聊。**零后端改动**。

## 变更目标

1. **CLI 会话可见面**（`cli-ops/spec.md` ADDED「会话命令族与交互入口续聊」）：`session show <id>`
   打印该会话转录（共用同一 `TranscriptStore`）；无子命令的交互入口 SHALL 接受 `--session <id>`
   续接既有会话（复用该标识，**不新建**），未登记标识仍 fail-closed 拒绝。
2. **Web 会话列表面板**（`ui/spec.md` ADDED「Web 会话列表与切换」）：SPA SHALL 呈现会话列表
   （`GET /sessions` 的派生 `title` 与最近活跃），SHALL 支持点选会话查看其转录（`GET
   /session/{id}/messages`）并继续对话，SHALL 支持**显式**新建会话（取代首条消息惰性建会话）。

## Non-goals

- **任何后端 / 规格已有端点改动**：`GET /sessions`、`GET /session/{id}/messages` 由 `0115` 提供，形状不动。
- 会话**删除 / 重命名**；新建会话对话框（标题仍为**派生**首条用户消息，不新增可写标题）。
- SSE 断线重连语义、Tauri 壳改动（`frontend/dist/` 仍不提交，本地 `npm run build` 重建）。
- CLI 侧**转录渲染进 TUI 时间线之外**的展示形态（如分页 / 导出）。
- 前端测试基建（本仓无 JS 测试；靠 `npm run build` + 离线冒烟，见 tasks §4）。

## 判据与取舍

- **不给 TUI 造第二套会话参数**：`run --session <id>` 已是既有先例（`entry.py:296`）⇒ 交互入口用**同名**
  `--session <id>`（顶层 flag），语义一致（复用既有会话，不新建）。`argparse` 子解析器只在属性缺席时套默认值
  ⇒ 与 `run --session` 同 `dest` 不冲突。
- **`CLIBridge.connect_impl` 签名加 `session_id`**（`Callable[[UIAPILayer, str], None]`）：会话标识必须
  到达 `build_app`（今天硬编码在 `repl.py:193`）；**不绕过** `CLIBridge`（否则 `cli_bridge` 沦为死代码）。
  代价是两处测试替身随之对齐（`tests/test_ui.py:68`、`tests/test_entry.py:318`）。
- **显式新建取代惰性新建**：惰性建会话会在每次打开页面时留下 32 位 hex 的**空会话**，污染列表（用户要的
  是「列表记录了当前已创建会话」）⇒ 无选中会话时发送被拒绝并提示，由「新建会话」按钮显式创建。
- **列表按 `updated_at` 降序在**前端**排序**：后端 `registry.list()` 序即注册表序（创建序），而「最近活跃」
  是派生值 ⇒ 排序属呈现层，不回头改后端响应形状（`0115` 的兼容承诺不破）。
- **续聊时把既有转录渲染进时间线**：否则用户按 `--session` 进来看到空时间线、以为没接上（模型有上下文、
  界面没显示 ⇒ 误导）。渲染用既有 `.echo`/`.hint` 样式与 `escape`，不新增渲染通道。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 切换会话时异步取历史发生**竞态**（慢响应覆盖新会话） | 取回后校验「目标 `sessionId` 未变」才写入 `lines` |
| 前端口径与后端**形状**漂移（`{sessions: []}` / `{session_id, messages}`） | 复用既有 `toJson` 错误映射；冒烟以真实 `serve` 断言 |
| 未登记标识经 `--session` 进 TUI 后中途才炸 | 在 `build_app` 构建期即调 `api.session_messages(id)`（未登记抛 `UiError`，fail-closed 且**先于**进入 TUI） |
| 破坏既有 REPL 行为（默认路径） | `session_id` 缺省 `""` ⇒ `api.create_session("cli")` 逐字不变；既有 repl 测试全绿即证 |
