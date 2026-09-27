# Phase 5 — 自进化引擎（evolution）

> 里程碑：**M4 自进化**
> 位置：分层图 L5 进化层（结晶闭环）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 3（loop/skills）+ Phase 4（orchestration 可选数据源）

---

## 1. 范围与定位

本 Phase 交付 **1 个能力，让 core-agent 具备自进化**：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| evolution | 结晶闭环（经验采集→结晶→溶解→诊断→提案→验证门→留出评测） | L5 进化层 |

**关键事实**：evolution 在 contracts_summary.md §10 中**无错误码定义**（有接口与方法，但错误码空缺），且核心「结晶」环节须与 Phase 3 的 `SkillCrystallizer` 衔接——这是本 Phase 首步任务的核心核对点（见 §4）。

---

## 2. 里程碑验收（M4 自进化）

**M4 标志**：四阶段结晶闭环跑通。以下全部勾选才算 Phase 5 完成：

- [ ] 采集行动结果对、无结果证据不采集
- [ ] 生成技能候选待人工确认（propose 产物进人工确认队列）
- [ ] 退化检测溶解回收（dissolve）
- [ ] 对比诊断归因到插件、无插件级归因则人工介入（diagnose）
- [ ] 模块级提案过验证门才发布（validate 门禁）
- [ ] 留出集通过则发布、退化回滚、并发评测资源上限（evaluate）
- [ ] 基准集注册 + 批量评测 + 基线对比判定退化
- [ ] 任务完成度/正确性/轨迹质量三维评测
- [ ] 端到端：一次真实任务 → diagnose 归因 → propose 候选 → validate 过门 → evaluate 留出集 → 发布/回滚全链路跑通

---

## 3. 依赖与前置

- **上游**：Phase 0（plugin-registry：诊断归因到插件）+ Phase 1（memory：经验采集来源，**经 `MemoryBackend(Protocol)` 钩子解耦**——evolution 只依赖 Protocol 抽象取「行动结果对」，不 import `MemoryStore` 具体实现）+ Phase 3（loop：产生行动结果对；skills：`SkillCrystallizer` 结晶 + `SkillLibrary` 注册发布）+ Phase 4（orchestration：可选的多任务轨迹数据源）。
- **evolution↔memory Protocol 钩子解耦**（本 Phase 硬性要求）：evolution 的采集/诊断数据入口统一走 memory 的 `MemoryBackend(Protocol)`（`get`/`search`/`list_index`），禁止直接依赖 `MemoryStore` 或具体存储实现；结晶产物写入经 memory 的 `Crystallizer.crystallize()` 落库，evolution 自身的 `Crystallizer` 与 memory 侧通过 Protocol 边界清晰分工（evolution 管「进化候选」，memory 管「分层记忆」）。
- 关键前置：
  - `EvolutionEngine(Plugin)` 需注册进 plugin-registry 生命周期。
  - 结晶产物是技能候选，最终经 skills 的 `register()` 进库——evolution 与 skills 的衔接是硬前置。
  - 评测（evaluate）需要 Phase 4 编排能力跑基准集（并发评测资源上限）。
  - `maybe_run()` 触发条件须可配置，避免每次运行都触发进化。

---

## 4. 首步任务

**核对并打通两个硬前置：evolution ↔ skills 结晶衔接 + evolution ↔ memory Protocol 钩子解耦**：

1. 确认 Phase 3 的 `SkillCrystallizer.crystallize()` 签名与 evolution 的 `propose()` 产物（`GenerationCandidate`）能对接：
   - `propose()` 生成 `GenerationCandidate` → 人工确认 → `crystallize()` 落库为 `Skill`
   - 无「行动结果证据」时不得采集（契约红线）
2. 确认 `Diagnoser` 归因到插件的链路依赖 plugin-registry 的插件元数据，无插件级归因时走人工介入分支。
3. evolution 无错误码定义——首步补齐错误码（建议：`NO_EVIDENCE`、`GATE_REJECTED`、`EVAL_REGRESSED`、`CANDIDATE_PENDING`），走 openspec_sop 补契约再编码。
4. 核对 evolution ↔ memory Protocol 钩子解耦：经验采集/诊断数据入口统一走 memory 的 `MemoryBackend(Protocol)`（`get`/`search`/`list_index`），**不得**直接 import `MemoryStore` 或具体存储实现；结晶产物经 memory 的 `Crystallizer.crystallize()` 落库，evolution 自身 `Crystallizer` 与 memory 侧经 Protocol 边界分工（evolution 管进化候选，memory 管分层记忆）。

**启动前核对**（按顺序执行）：
1. 读 contracts_summary §10（evolution）+ §16（memory）+ §23（skills）原文，确认衔接点与 Protocol 钩子。
2. 补 evolution 错误码契约 + 结晶衔接 + memory 钩子解耦设计，validate 通过后再编码。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 结晶闭环数据流（先）

- `Diagnoser`（diagnose）→ `Proposer`（propose）→ `Validator`（validate）→ `Evaluator`（evaluate），`EvolutionEngine` 编排四者 + `EvolutionTrigger` 触发 `maybe_run()`。
- 数据类型：`DiagnosisReport` / `GenerationCandidate` / `GateReport` / `EvalReport`

### 5.2 触发与资源控制（后）

- `EvolutionTrigger.maybe_run()` 触发条件可配置；并发评测资源上限熔断。
- 留出集评测 + 基线对比判定退化 + 退化回滚。

---

## 6. 契约对齐

以 `contracts_summary.md` §10 为唯一契约基线：

| 契约项 | 实现必须覆盖 |
|---|---|
| 采集 | 只采集有结果证据的行动结果对 |
| 结晶 | 生成候选待人工确认，不得自动发布 |
| 溶解 | 退化检测后回收 |
| 诊断 | 归因到插件，无插件级归因则人工介入 |
| 提案 | 模块级提案过验证门才发布 |
| 评测 | 留出集通过发布、退化回滚、资源上限；三维评测（完成度/正确性/轨迹质量） |

**契约红线**（违反即返工）：
1. 无结果证据不得采集，候选不得自动进库。
2. 退化必须回滚，不得带退化发布。
3. 评测必须受并发资源上限约束，不得无限并发。
4. 三维评测缺一不可：任务完成度、正确性、轨迹质量。

---

## 7. 门禁验收

全局四命令（见 `doc/05-development/development-standards.md`）全部通过：

```bash
ruff check src tests
ruff format --check
pyright
pytest -q
```

本 Phase 专属校验（附加于全局门禁）：

- [ ] 采集测试：无证据不采集
- [ ] 提案测试：候选进人工确认队列，不自动发布
- [ ] 验证门测试：`GATE_REJECTED` 阻断发布
- [ ] 退化回滚测试：`EVAL_REGRESSED` 触发回滚
- [ ] 归因测试：插件级归因正确，无归因走人工介入
- [ ] 资源上限测试：并发评测超限熔断
- [ ] 端到端冒烟：一次真实任务走完整结晶闭环

---

## 8. 提交规范

- **一个 Phase 一个 commit**：evolution 模块 + 错误码补齐 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase5): evolution 自进化结晶闭环（M4）`
- 提交后更新 `README.md` §2 总览表 Phase 5 行状态列为「完成」。
