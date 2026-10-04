# Proposal — evolution-confirm-surface

## Why

账本 `coding-plan/phase-19.md` §2 **A4**：`EvolutionEngine.confirm` 的三重门（present + `is_approved` +
target 匹配）在 `0046` 已实现并被测试覆盖，但**生产侧无调用者** —— grep 仅命中 `PermissionGuard.confirm`
同名方法。三处症状，同一个根因（零件「进程内、无状态、无驱动」）：

1. **确认路径在生产不可达**：`confirm` 无调用方，`crystallize`（发布 + 开窗）**同样无调用方**
   —— change `0051` 已把 `evolve run` 接成一次性入口，但那一轮只走到 `pending` 为止，
   L4 的「过门候选 → 人工确认 → 结晶发布」在生产**整条断掉**。
2. **待确认队列是死状态**：`EvolutionEngine._pending` 只在进程内累积，且**只增不减**；
   CLI 每条命令各起一份 `HarnessHost`（`0051` 决策已记），故一次 `evolve run` 产出的候选
   在下一条命令里已不可见 —— 「谁来看这一队候选」无答案。
3. **候选身份绑在对象标识上**：验证门/留出评测报告以 `id(candidate)` 为键存于引擎私有字典
   （`engine.py:_gate` / `_eval`），**跨进程必然失配** —— 即便把队列落盘，重启后
   `crystallize` 也会以 `GATE_REJECTED` / `EVAL_REGRESSED` 拒绝一个本该发布的候选。

## What Changes

- `GenerationCandidate` 增**稳定身份** `candidate_id`（UUID，构造即固化）。
- 新增 `PendingQueue`（`evolution/pending.py`）：把「候选 + 验证门报告 + 留出评测报告」作为
  **一条**待确认记录整体落盘（复用 `core/persistence.py` 的 JSON 快照，零第三方依赖），
  启动时恢复；未注入路径则纯内存（与 `ObservationRegistry` 同形，ADR-0054 已确立此模式）。
- `EvolutionEngine` 以 `PendingQueue` 取代 `_pending` / `_gate` / `_eval` 三份进程内私有态；
  检索键由 `id(candidate)` 改为 `candidate.candidate_id`；新增 `reject(candidate, reason=...)`
  与 `find(candidate_id)`；`pending()` 只列 `status == "pending"`。
- 组合根注入 `PendingQueue(path=$CORE_STATE_DIR/evolution-pending.json)`。
- **操作面**：CLI 增 `evolve pending` / `evolve confirm <id>` / `evolve reject <id>`；
  对 `risk_level="high"` 候选，操作面作为审批流的**签发端**构造 `ApprovalRequest` →
  `ApprovalWorkflow.approve()` → 以获批审批单调 `confirm`（`im/gateway.py:14` 已有同形先例）。

## Non-Goals

- **不做** UI 审批面板（WebUI 侧留待需要时；本变更只落 CLI 操作面）。
- **不做** 审批单本身的持久化 —— `ApprovalWorkflow` 的归档仍是进程内的（本变更只**签发**，
  归档持久化属 permission 域的另一议题）。
- **不做** 候选的去重/上限/过期回收（队列只增不减的另一面；当前无消费者需要）。
- **不改** `confirm` 的三重门语义（`CONFIRM_REQUIRED` fail-closed 与目标匹配一律照旧）。
- **不做** 低风险自动结晶（spec 明令禁止）。
- **不动** `EvolutionWorker` / `EvolutionTrigger` 的驱动语义（`0051` 已定：驱动面只给机会）。

## Impact

- `src/core/evolution/models.py`（`candidate_id`）、`engine.py`（队列注入 / 检索键 / `reject` / `find`）、
  `pending.py`（新）、`__init__.py`（导出）。
- `src/core/runtime.py`（组合根注入路径）。
- `src/core/entry.py`（`evolve` 三个子命令 + 审批单签发）。
- `doc/openspec/specs/evolution/spec.md`（ADDED 一条 Requirement）、`doc/03-interfaces/evolution-interface.md`、
  `doc/02-modules/evolution.md`、`doc/01-architecture/adr.md`（ADR-0058）。
- 账本 `coding-plan/phase-19.md` §2 A4 关闭。
