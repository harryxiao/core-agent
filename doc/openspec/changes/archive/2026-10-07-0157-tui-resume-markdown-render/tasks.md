# 0157 · 任务清单（TUI 续聊转录按 Markdown 渲染）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` **MODIFIED**「CLI 友好交互」（渲染格式由「仅流式」扩为「流式 ∨ 续聊载入」同格式 + 1 Scenario）。
> 状态：**已归档**（2026-10-07；四门禁全绿，`openspec validate --all` 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`（delta，MODIFIED）：「CLI 友好交互」补续聊铺入条款 + Scenario「续聊转录按同格式渲染」
- [x] 1.2 ADR-0149（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_repl.py`：新增「续聊铺入的 agent 回复渲染为 Markdown（含 `MarkdownFence`）」用例（实现前红）
- [x] 2.2 `tests/test_repl.py`：`_timeline_texts` 助手下沉为同时收集 `Static` 与 `Markdown`（既有断言本体不变）
- [x] 2.3 红态确认：2.1 实现前必红（回复落 `Static`，无 `Markdown`/`MarkdownFence`）

## 3. 实现

- [x] 3.1 `src/core/ui/repl.py`：`on_mount` 续聊铺入分支 —— agent 回复改挂 `Markdown(...)`；用户 `❯` 回显不动

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2「会话续聊」：补「agent 回复按 Markdown 渲染（与实时同格式）」
- [x] 4.2 `doc/04-testing/test-cases.md`：新增 `## 72.`（TC-RESUMEMD）
- [x] 4.3 `coding-plan/known-risk.md`：§1 立 E98（已修）＋ §3 加 ADR-0149 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（ui）⇒ `shutil.move` 至 `archive/2026-10-07-0157-tui-resume-markdown-render/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E98）；ADR-0149 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(ui): TUI 续聊转录按 Markdown 渲染，回复不再退化为明文（change 0157）`
