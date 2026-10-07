# TUI 续聊转录：agent 回复按 Markdown 渲染（与实时流式路径同格式）

## Why

- **用户实测反馈（2026-10-07）**：在 TUI（`core-agent` 直接跑）里让 agent 输出带 ```` ``` ```` 的 demo，
  「回显依然是正常明文逐行输出的」。
- **根因（已定位，`src/core/ui/repl.py:395-400`）**：TUI 有**两条**渲染 agent 回复的路径，
  只有**实时流式**那条走 Markdown：
  1. **实时流式**（`_show_delta` → `_flush_tail` → `_touch_tail`/`_freeze_tail`，`repl.py:474-574`）——
     尾段**始终**是 `Markdown` widget ⇒ 代码围栏成代码块、表格成表格（E88/E89 已修）。
  2. **续聊载入既有转录**（`on_mount`，`repl.py:391-400`）—— agent 回复被喂给
     `Static(content, classes="hint", markup=False)` ⇒ **纯文本逐行**，代码围栏退化成字面 ```` ``` ````。
- **同一缺陷在规格里的位置**：`ui` spec「Requirement: CLI 友好交互」已要求「围栏渲染为代码块」，
  但**只覆盖流式路径**；续聊铺入时间线未被该 Requirement 覆盖 —— 一条回复**换个入口进来就变样**，
  是**同一条 Requirement 的漏面**，不是新特性。

## What Changes

- `src/core/ui/repl.py`：`build_app` 内 `on_mount` 的续聊铺入分支 —— **agent 回复**改挂
  `Markdown(...)`（与实时路径同 widget，不降级为 `Static` 明文）；**用户消息**回显保持既有
  `❯` 行（逐字转义，单行前缀，不属 Markdown 面）。既有转录**内容**不被改写，只对齐**呈现格式**。
- `doc/openspec/specs/ui/spec.md`：「Requirement: CLI 友好交互」**MODIFIED** —— 把「渲染格式」
  由「仅流式」扩为「流式 ∨ 续聊载入」两条入口**同格式**（+ 1 Scenario）。
- `doc/01-architecture/adr.md`：**ADR-0149**（续聊转录与实时流式**同格式**渲染；两条入口单一口径）
  ＋ 变更追踪行。
- `doc/03-interfaces/ui-interface.md` §2：「会话续聊」段补「agent 回复按 Markdown 渲染」。
- `doc/04-testing/test-cases.md`：新增 `## 72.`（TC-RESUMEMD）。
- `coding-plan/known-risk.md` §1：立 **E98**（已修）＋ §3 ADR-0149 已知局限行。

## Non-goals（明确不做）

- **不**给 Web/Desktop SPA 加 Markdown 渲染（`Chat.svelte` 纯文本属**另一端**，账本 E88 局限② 已记；
  若要做须另开 change，牵动前端依赖面）。
- **不**改实时流式路径（`_show_delta` / `_flush_tail` / `_in_open_*`）—— 它**已正确**，本 change 零触碰。
- **不**改续聊的加载语义、会话校验、`❯` 回显格式、既有转录**内容**。
- **不**引入三方库（`Markdown` 是既有 lazy import）。

## 风险

- **风险①：既有用例 `test_build_app_resumes_existing_session` 断言「回复文本出现在时间线」** ——
  修复后回复落在 `Markdown.source` 而非 `Static.render()`。⇒ 按新契约**改写该用例的取文本助手**
  （`_timeline_texts` 同时收集 `Static` 与 `Markdown`），**断言本体不变**（内容仍在时间线）。
- **风险②：历史回放体量** —— 长会话续聊一次性挂 N 个 `Markdown` widget。与实时路径同量级
  （实时也是每固化段一个 `Markdown`），**不新增**渲染机制；如未来有体量问题，属续聊**加载面**
  另议（不在本 change）。
