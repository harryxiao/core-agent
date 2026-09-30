# Phase 15 — 验证门 + 结晶（评测基建 + 进化结晶 + 沙箱颗粒度 + HITL + 崩溃恢复/时间旅行）

> 里程碑：**M10 进化闭环**（与 Phase 14 连排，不可拆分；本 Phase 收口「验证门 → 评测 → 结晶」全链路 + design-completeness-eval 三缺口 P1/P2/P3 + loop 级可靠性）
> 位置：L4 进化验证门/结晶闭环 + 横切（permission 沙箱/审批 + durability 接入 loop）
> 上游：Phase 14（EvolutionWorker 已产出候选）
> 对应 change：无新增 openspec change（P1/P2/P3 三条补齐路线均已落 spec：permission「沙箱执行颗粒度」、evolution「评测基建」、permission「审批动作分级协议」）

---

## 1. 范围与定位

Phase 14 只把进化做到「采集 + 提案 dry-run」，候选「只能看不能落」。本 Phase 补齐验证门与结晶，使**一个真实缺陷走完「诊断 → 提案 → 验证 → 结晶」全链路闭环**，并顺手补齐 design-completeness-eval 的三条 P1/P2/P3 缺口（均已有 spec，缺工程落地）+ loop 级可靠性（崩溃恢复 / 时间旅行）。

| 缺口 | 优先级 | 落点 | 现状 |
|---|---|---|---|
| 评测/eval 平台 | P2 | evolution「评测基建」「任务质量评测」 | `Evaluator`/`BenchmarkRegistry`/`QualityEvaluator` 已有，缺可落地评测 harness 与基线对比退化判定 |
| 沙箱执行颗粒度 | P1 | permission「沙箱执行颗粒度」 | `SandboxManager`/`SandboxPolicy` 已有（subprocess + outbound/fs 检查），缺三域隔离 + 资源配额 |
| HITL 审批颗粒度 | P3 | permission「审批动作分级协议」 | `ApprovalWorkflow` 已有 create/ask/archive，缺 approve/reject/edit-plan 三动作 |

## 2. 里程碑验收（M10 后半段）

- [ ] 一个真实缺陷（如工具写错路径）走完 诊断 → 提案 → 验证门 → 留出评测 → 结晶 全链路，`EvolutionOutcome.status == published`
- [ ] 验证门：`Validator` review + 运行时测试均过 → `GateReport.passed=True`；未过门候选丢弃 + 教训写回 L2/L3
- [ ] 留出评测：`Evaluator` 在基准集批量评测 + 与基线对比 → `EvalReport.verdict ∈ publish/rollback/freeze`
- [ ] 结晶：`EvolutionEngine.crystallize` → `SkillLibrary.register`（skill）/ `MemoryStore.crystallize`（plugin）
- [ ] 沙箱颗粒度（P1）：三域隔离 + 网络出站白名单 + 资源配额超限返回 `QUOTA_EXCEEDED`
- [ ] HITL（P3）：`approve`/`reject`/`edit-plan` 三动作 + 分级路由，`edit-plan` 旧单标 superseded
- [ ] 崩溃恢复/时间旅行接 loop：崩溃后 `restore/resume` 续跑；`rollback` 回滚副作用

## 3. 依赖与前置

- Phase 14（EvolutionWorker 产出候选；TaskScheduler checkpoint）
- Phase 5（evolution `Validator`/`Evaluator`/`EvolutionEngine.crystallize`）
- Phase 2（permission `SandboxManager`/`ApprovalWorkflow`；durability `CrashRecovery`/`TimeTravel`）
- Phase 13（runtime 组合根）

## 4. 首步任务

1. **核对 evolution 评测三件现状**：对照 evolution/spec.md「评测基建」「任务质量评测」两条 Requirement 的 Scenario（基准集注册 / 候选批量评测 / 基线对比退化判定 / 完成度·正确性·轨迹质量三维），逐项核对 `BenchmarkRegistry`/`Evaluator`/`QualityEvaluator`，**只补缺口不重写**。

## 5. 实现顺序

### 5.1 评测基建（P2，evolution 模块，补齐）

- `BenchmarkRegistry`：核对 `register(Benchmark)` / `list()` / 批量评测；缺则补（Benchmark = benchmark_id + task_type + samples[input/expected] + metrics）
- `Evaluator.evaluate(candidate)`：核对留出集批量执行 + 与基线对比 → `EvalReport.verdict ∈ publish/rollback/freeze`
- 评测 harness：一段真实 defect 的基准集（含 input + expected），供全链路测试复用

### 5.2 验证门 + 结晶接线（runtime，补齐 Phase 14 未注部分）

- runtime 装配完整 `EvolutionEngine`：`Diagnoser`+`Proposer`+`Validator`+`Evaluator`+`Collector` + `SkillLibrary` + `MemoryStore` + `Crystallizer`
- 一个真实缺陷全链路测试（diagnose → propose → validate → evaluate → crystallize → SkillLibrary/MemoryStore 落库）

### 5.3 沙箱颗粒度（P1，permission，补齐）

- `SandboxPolicy`/`SandboxManager`：核对三域隔离（终端/浏览器/文件系统）+ 网络出站白名单 + 资源配额（超限 `QUOTA_EXCEEDED`）vs spec Scenario；补缺口

### 5.4 HITL 协议（P3，permission，补齐）

- `ApprovalWorkflow`：补 `approve`/`reject`/`edit-plan` 三动作 + 分级路由（`edit-plan` 生成新审批单、旧单 `superseded`）；`ApprovalResult` 状态承载

### 5.5 CrashRecovery/TimeTravel 接 loop（durability → runtime/loop）

- `CrashRecovery.restore/resume`、`TimeTravel.rollback` 已有 → 接线：runtime 启动时检测未完成任务 → `restore/resume`；loop `act` 副作用经 `EffectTracker` 可 `rollback`（Phase 2 已有实现，接 loop 触发点）

## 6. 契约对齐

| capability | 接口 § / spec Requirement | 关键签名 |
|---|---|---|
| evolution | evolution-interface.md；spec「验证门」「留出评测」「评测基建」「任务质量评测」 | `Validator.validate(candidate) -> GateReport`；`Evaluator.evaluate(candidate) -> EvalReport`；`EvolutionEngine.crystallize(candidate)` |
| permission | permission-interface.md §2；spec「沙箱执行颗粒度」「审批动作分级协议」 | `SandboxManager.run/create/destroy`；`ApprovalWorkflow.create/ask/archive`（补 approve/reject/edit-plan） |
| durability | durability-interface.md §1 | `CrashRecovery.restore/resume`；`TimeTravel.rollback` |

## 7. 门禁验收

```bash
ruff check src tests && ruff format --check src tests && pyright && pytest -q
```

- 新增 `tests/test_phase15.py`：
  - 真实缺陷全链路：diagnose → propose → validate → evaluate → crystallize → `published`
  - 未过验证门候选丢弃 + 教训写回 L2/L3
  - 留出评测退化 → `rollback`
  - 沙箱三域/白名单/配额超限 `QUOTA_EXCEEDED`
  - HITL `approve`/`reject`/`edit-plan`（edit-plan 旧单 superseded）
  - CrashRecovery restore/resume + TimeTravel rollback 接 loop

## 8. 提交规范

`feat(phase15): 验证门+结晶 评测基建 + 沙箱颗粒度 + HITL + 崩溃恢复/时间旅行（M10 后半段）`

提交后更新 `README.md` §2 Phase 15 行状态列「⬜ 待开始」→「✅ 完成」；M10 进化闭环（P14+P15）整体勾选。
