# 0296 — 前台轮不被后台收尾与压实拖死

## Why

2026-10-19 生产事故：交互端输入「执行」后长时间无响应，记忆压缩同样长时间无终态。遥测证据：

- `fda1ce3c`（09:12:21–09:12:49）正常跑完 3 个 `code_run` 并外发 `loop_finished`；
- `40f9bd91`（09:13:16 起）只有 `loop_started`、**零业务 span**，09:15:42 以
  `loop_aborted CancelledError` 结束（146s）；
- `c7fff019`（09:16:30 起）6 个 `code_run` 后静默 86s（第 6 步触发轮内压实），09:18:15 被中止；
- 历史：`10-19 07:29:51 maintenance_failed step=compaction_timeout timeout_s=120`，
  `07:30:16 compaction elapsed_ms=144839`（144.8s）；`08:02:53` 再次超时；
- `10-11 23:36 turn_observer_failed: LLM_TIMEOUT 调用超时（>60.0s）：glm-5.3`。

根因不是单一死锁，而是**前台被后台同步模型工作串行拖住**：

1. `DefaultLoop._astream_events` 在发 `loop_started` 之后、任何业务逻辑之前
   `await self._await_post_turn()`。上一轮的后台收尾（`turn_observer` → Sedimenter/SOP，再
   `_maintain` → 记忆压实）任意一段慢，下一轮就**连感知都进不去**。
2. 后台收尾与维护中的单次模型调用沿用主调用的 `timeout=60s` × `max_retries=3`，一次失败
   端点可吃掉约 4 分钟；压实又是「逐条目打分 + 每会话摘要 + 三类抽取」的多调用串行作业
   （`_MAX_SCORED_PER_COMPACT = 20`），实测 144.8s。
3. `MemoryStore.compact` 没有任何**协作式截止时间**：轮内 `_compact_bounded` 的 `wait_for`
   只是放弃等待，工作线程仍会继续发起后续模型调用；`_maintain` 与 CLI `memory maintain`
   则完全没有上限。
4. 0295 把每个写效应成功轮都接到 Sedimenter 候选蒸馏，收尾链路进一步变重。

## What Changes

- **前台解耦**：`_astream_events` SHALL NOT 等待上一轮后台收尾。后台收尾改为**单链路串行**
  （后一轮的收尾排在前一轮之后），前台只留痕 `post_turn_overlap` 并立即进入本轮。
- **有界等待**：`arun` / `run` 的「包含完整收尾」语义保留，但等待 SHALL 有上限
  （缺省 `120s`，可经构造注入覆盖）；超时留痕 `post_turn_timeout` 并返回本轮结果。
- **协作式截止时间**：`MemoryStore.compact(..., deadline=...)` 在**每次模型调用前**检查
  （打分逐条、逐会话摘要、三类派生抽取）；截止后 SHALL NOT 发起新的模型调用，也不提交
  半成品摘要。轮内压实把 `deadline` 传入工作线程；维护节拍与 CLI 同样传入。
- **压实 single-flight**：同一 store 上并发触发的压实 SHALL 非阻塞跳过（告警留痕），
  避免超时工作线程与新触发叠加放大模型调用。
- **后台模型调用独立上限**：组合根为 `_llm_text` 派生接缝构造**独立 provider**，
  由新配置键 `llm.background_timeout`（缺省 `60.0` 秒）与 `llm.background_max_retries`
  （缺省 `0`）约束；主循环/校验仍用主 provider（`llm.timeout` / `llm.max_retries` 逐字不变）。
- **轮内压实上限可配**：新配置键 `loop.compact_timeout`（缺省 `60.0` 秒，须 `> 0`），
  组合根注入四个 `DefaultLoop`；超时语义保持「放行本轮 + `compaction_timeout` 留痕」。
- **维护节拍有界**：`_maintain` 取得总截止时间（缺省 `120s`，构造注入）；截止后剩余步骤
  SHALL 跳过并逐项留痕 `maintenance_failed`（`error="deadline_exceeded"`）。
- **CLI 有界**：`memory maintain` 新增 `--timeout S`（缺省 `120`，须 `> 0` 整数），
  以截止时间调用 `compact`；截止后跳过后续步骤并明示「已达到时间上限」。
- **共享技能库加锁**：后台收尾与下一轮可并发后，`SkillLibrary` 的注册/查询/持久化
  SHALL 经 `threading.RLock` 串行化（与 `FileBackend` / `SopExtractor` 同口径）。

## Non-goals

- 不引入进程隔离、任务队列或常驻调度器；不改动 cron 形态。
- 不强杀工作线程或取消已发出的 HTTP 请求（Python 线程不可强杀）；截止时间是**协作式**：
  当前调用返回到检查点后不再发起下一次。
- 不改变压实的产物与可逆语义（摘要、迁移、派生抽取、效应 trace 均不变）。
- 不改 `llm.timeout` / `llm.max_retries` 的既有语义与缺省（主调用行为逐字不变）。
- 不改 TUI/Web 事件契约；不新增压缩进度事件。
- 不提高 `loop.compact_steps` 缺省值（缓解手段，不是修复）。

## Impact

- 代码：`src/core/loop/default.py`（前台解耦、收尾链、维护截止、压实截止）、
  `src/core/memory/store.py`（deadline + single-flight + 时钟注入）、
  `src/core/memory/protocol.py`、`src/core/runtime.py`（后台 provider / 压实上限接线）、
  `src/core/configuration/{manager,models}.py`（三键）、`src/core/entry.py`（CLI `--timeout`）、
  `src/core/skills/library.py`（RLock）。
- 规格：`loop` MODIFIED「收尾与维护工作的执行线程」「轮内压实进度与上限」；
  `memory` MODIFIED「记忆压实」；`configuration` MODIFIED「LLM 提供商配置（必选）」
  「循环预算配置」；`cli-ops` MODIFIED「运维命令集」。
- 测试：新增前后台解耦 / 收尾链 / 有界等待 / 压实 deadline / single-flight /
  维护 deadline / CLI timeout / 配置三键 / 后台 provider 接线；更新现有 `compact` 替身签名。
- 文档：ADR-0286、`coding-plan/known-risk.md` E232、`doc/04-testing/test-cases.md` §209、
  `doc/03-interfaces/{loop,memory,configuration,cli-ops}-interface.md`（如存在对应节）。
