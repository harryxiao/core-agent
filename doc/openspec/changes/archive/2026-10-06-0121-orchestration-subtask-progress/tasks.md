# tasks — 子任务运行态实时回流（change 0121 / phase-29 change A：E51）

## 1. 规格（先行）
- [x] 1.1 `specs/orchestration/spec.md`：MODIFIED「任务入口与进度事件」——词表 +`subtask_progress`
- [x] 1.2 同 delta：**子任务运行态回流**条款（经 `astream` 执行；里程碑 = `action_started` /
      `action_completed` / `step_completed`；走既有通道、不另建旁路）
- [x] 1.3 同 delta：**粒度与载荷白名单**条款（`reply_delta` **不回流**；按内层类型白名单化；
      白名单外类型（含未来新增）不外发；凭据不进事件面）
- [x] 1.4 同 delta：**附加通道、终态不变**条款（终态仍 `SubtaskOutcome`；fan-in / 依赖交接 /
      波次推进判据不变；无里程碑时逐字一致）+ 3 个新 Scenario
- [x] 1.5 `openspec validate 0121-orchestration-subtask-progress` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_orchestration_progress.py`（新）：**里程碑实时回流** —— 真 `DefaultLoop`
      （planner 走工具动作 → 终止动作）经 `TaskScheduler.astream` 执行 ⇒ 事件序含
      `subtask_progress`，内层类型依序 `action_started` / `action_completed` / `step_completed`，
      且携带 `task_id` / `subtask_id` / `ts`
- [x] 2.2 同文件：**`reply_delta` 不外发** —— 流式 planner（逐个 delta）⇒ `subtask_progress` 中
      **无** `event == "reply_delta"`，且任何 `data` 里**无**模型原文
- [x] 2.3 同文件：**载荷白名单化** —— 内层事件多带字段（如 `api_key` / `secret`）⇒ 外发 `data`
      只含该类型白名单键（参数化表：三类里程碑各一）
- [x] 2.4 同文件：**白名单外类型不外发** —— 内层产出未知事件类型 ⇒ **零** `subtask_progress`
- [x] 2.5 同文件：**附加通道不改终态** —— 同一子任务「有里程碑」与「无里程碑」两次运行 ⇒
      `SubtaskOutcome` 的 `ok` / `trace_id` / `reply` 与 fan-in 推进结果**逐字一致**
- [x] 2.6 同文件：**`collect_result` 与 `arun` 同语义** —— `collect_result(loop.astream(x))` 与
      `await loop.arun(x)` 结果相等（成功 / `loop_failed` 归一 / 未达终态不抛）—— 单一真源守门
- [x] 2.7 回归改判：**5 处**测试替身由 `arun` **迁移到 `astream`** ——
      `tests/test_phase14.py:_FakeLoop`、`tests/test_phase15.py:_FakeLoop`、
      `tests/test_session_isolation.py:_SessionRecordingLoop`、
      **`tests/test_orchestration.py:_TrackingLoop` 与 `_FixedReplyLoop`**（编排层经 `astream` 执行
      ⇒ 只覆写 `arun` 的替身不再被调；`test_orchestration.py` 的帧序列断言相应过滤 `subtask_progress`）
- [x] 2.8 红：以上用例在实现前**必失败**（`subtask_progress` 尚不存在）—— 实测 `ImportError:
      cannot import name 'collect_result'` + 6 处编排帧断言失败

## 3. 实现
- [x] 3.1 `src/core/loop/protocol.py`：新增 `async def collect_result(stream, on_event=None) ->
      LoopResult`（逐事件回调 → 归一化终态：`loop_finished` 取载荷 / `loop_failed` 归
      `failed=True` 且回复取 `reason` / 未达终态不抛）；`src/core/loop/__init__.py` 导出
      —— 顺带**订正协议声明**：`LoopPlugin.astream` 由 `async def … -> AsyncIterator[LoopEvent]`
      （= 协程）改为异步生成器 stub 形式 `def astream(…) -> AsyncIterator[LoopEvent]`（与实现形态一致）
- [x] 3.2 `src/core/loop/default.py`：`arun` 改为 `collect_result(self.astream(...))` 薄壳
      （签名与语义逐字不变）
- [x] 3.3 `src/core/orchestration/scheduler.py`：模块级 `_PROGRESS_FIELDS`（内层类型 → 白名单字段）
      + `_run_subtask` 内 `arun` → `astream` + `collect_result(..., relay)`；`relay` 只转译白名单
      类型、载荷按白名单取键、附 `ts`
- [x] 3.4 迁移 **5 处**测试替身到 `astream`（`test_phase14` / `test_phase15` / `test_session_isolation`
      / `test_orchestration` ×2）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1535 passed ⇒ 改判 + 新增后 **1542 passed**）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/orchestration/spec.md`（对齐既有排版：
      `### Requirement:` 正文紧接、`#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0121-orchestration-subtask-progress/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0114**（决策：复用既有通道不另建旁路 / 白名单化载荷 /
      终态归一抽为共享实现 + 判据订正 2 条（键名 `event`·`data`；「层面零改动」订正为含替身迁移与
      协议声明订正）+ 已知局限 + 变更追踪表行）
- [x] 6.2 `doc/03-interfaces/orchestration-interface.md`：`subtask_progress` 事件契约（载荷形状 +
      白名单表）；`doc/02-modules/orchestration.md` §4（事件面）
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行（TC-OSP-01..05，§34）
- [x] 6.4 `coding-plan/phase-29.md`：§6 表 A 行标「已落地（change `0121` / ADR-0114）」+ 状态行
      —— **该文件含他人未提交改动 ⇒ 本次编辑落盘但 `不提交`**（见 7.2）；`coding-plan/README.md`（干净 ⇒ 提交）
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [ ] 7.1 单次提交：`feat(orchestration,loop): 子任务运行态实时回流（subtask_progress）（change 0121）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、
      `src-tauri/Cargo.lock`、`node_modules/`、`frontend/dist/`、
      **`coding-plan/phase-29.md`**（含**他人**未提交的 §0.5 改动 ⇒ 本次的 §6/状态行编辑**随文件一并留待**，
      不拆 hunk 混提）
