# tasks — 编排任务的 HTTP 面与 Web 任务区（change 0122 / phase-29 change B：E53）

## 1. 规格（先行）
- [x] 1.1 `specs/ui/spec.md`：**ADDED**「任务编排的 HTTP 面与 Web 任务区」（新能力 ⇒ ADDED，先例 `0028`）
- [x] 1.2 同 delta：**HTTP 暴露**条款（`POST /task` SSE；同编排器同事件面；未登记仍 `UI_SESSION_NOT_FOUND`；
      编排器未注入 ⇒ `UI_ORCHESTRATOR_UNSET` 错误帧）
- [x] 1.3 同 delta：**并列不混池**条款（任务区与会话列表同处右栏、各自独立；在途 vs 持久）
- [x] 1.4 同 delta：**标题 + 状态 + 详情**条款（逐子任务渲染；详情取自既有事件载荷，不建第二数据源）
- [x] 1.5 同 delta：**收尾回落**条款（终态 ⇒ 移出在途列表；不进入会话列表）+ 明写**不在本需求内**
      （进入子 agent 会话 / 主-子焦点切换：无数据源）+ 6 个新 Scenario
- [x] 1.6 `openspec validate 0122-task-http-surface` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_serve.py`：**`POST /task` 流式任务事件** —— 真 `TaskScheduler`（+ 假 loop）经
      `UIAPILayer(orchestrator=…)` ⇒ 断言 SSE 帧序列含 `task.task_started` / `task.subtask_started` /
      `task.subtask_completed` / `task.task_finished`（**依序**）
- [x] 2.2 同文件：**未登记会话 ⇒ 错误帧** —— `UI_SESSION_NOT_FOUND` 出现在 body（HTTP 200 + SSE 错误帧，
      与 `/run` 同型）
- [x] 2.3 同文件：**编排器未注入 ⇒ 错误帧** —— `UI_ORCHESTRATOR_UNSET`
- [x] 2.4 同文件：**静态挂载不遮蔽 `/task`** —— 既有 `test_with_dist_…` 扩一条 `POST /task` 断言
- [x] 2.5 红：以上用例在实现前**必失败** —— 实测 4 failed：`405 Method Not Allowed`（`/task` 未注册、落到静态兜底）+ 三处拿不到 `UI_SESSION_NOT_FOUND` / `UI_ORCHESTRATOR_UNSET`

## 3. 实现
- [x] 3.1 `src/core/ui/fastapi_serve.py`：新增 `run_task(body)` 处理器（镜像 `run` 的 SSE + `UiError`
      错误帧），注册 `POST /task`（在 `StaticFiles` 挂载**之前**）；文档字符串与 `# noqa: C901` 注释的
      端点数 **11 → 12**
- [x] 3.2 `frontend/src/lib/api.js`：抽私有 `_postSSE(path, body)`（`runStream` 改为其薄壳，**语义逐字
      不变**）+ 新增导出 `runTask(sessionId, goal)`
- [x] 3.3 `frontend/src/views/TaskPanel.svelte`（新）：目标输入 + 在途任务卡片（子任务行 = 标题 + 状态
      徽标 + 可展开详情：里程碑 / 验收 / 失败理由）；终态 ⇒ 移出在途列表（回落）
- [x] 3.4 `frontend/src/App.svelte`：右栏新增 `<TaskPanel {sessionId} />` **区块**（在 `SessionList`
      **之上**，两区块并列不混池）；`SessionList` 零改动

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1542 passed ⇒ 新增 3 例后 **1545 passed**）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）
- [x] 4.6 前端 `npm run build` 通过（119 modules；产物 gitignore ⇒ **只提交 `frontend/src/**`**）+ 真 `uvicorn` 冒烟（SPA 已挂载下 `POST /task` 200 且 SSE 帧序正确、未登记会话回错误帧）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/ui/spec.md`（对齐既有排版：`### Requirement:`
      正文紧接、`#### Scenario:` 后留空行 —— 取该文件**最近的**（change `0115`/`0116`）块式样）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0122-task-http-surface/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0115**（决策：复用既有映射层只补 HTTP 暴露 / 任务区与
      会话列表**并列不混池** / **不建**子 agent 会话切换（无数据源）+ 判据订正 + 已知局限 +
      变更追踪表行）
- [x] 6.2 `doc/03-interfaces/ui-interface.md`：§1.1 事件面注明任务流、§1.2 端点表 **11 → 12**（新增
      `POST /task` 行）+ 右栏两区块说明
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行（TC-TASKHTTP-01..04，**§35**）
- [x] 6.4 `coding-plan/phase-29.md`：§3.3 标「B 已落地」+ §6 表 B 行 + 状态行 —— **该文件含他人未提交
      改动 ⇒ 本次编辑落盘但 `不提交`**（见 7.2）；`coding-plan/README.md`（干净 ⇒ 提交）
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [ ] 7.1 单次提交：`feat(ui): 编排任务的 HTTP 面与 Web 任务区（POST /task）（change 0122）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、
      `src-tauri/Cargo.lock`、`node_modules/`、`frontend/dist/`、
      **`coding-plan/phase-29.md`**（含**他人**未提交的 §0.5 改动 ⇒ 本次编辑随文件一并留待）
