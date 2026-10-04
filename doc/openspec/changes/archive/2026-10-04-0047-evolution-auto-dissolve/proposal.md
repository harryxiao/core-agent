# Proposal: 观察期回归自动溶解（evolution auto-dissolve）

## Why

Phase 18 #10（维度2 进化的最后一环，也是验收锚点「一条已结晶技能在观察期触发回归指标超阈值，
自动 `dissolve` 并保留教训」）。

1. **溶解无触发者**：`EvolutionEngine.dissolve(plugin_id, reason)` 已存在（技能标 deprecated +
   教训写回 L2），但**没有任何调用方**——`grep dissolve` 只在测试与 `SkillCrystallizer`（另一条
   通道）出现。evolution spec「溶解与回收」的 Scenario「退化检测」（连续指标退化 → 标记
   deprecated）在生产**不可能发生**：没有任何机制在结晶之后继续看指标。
2. **结晶即失联**：`crystallize` 发布后就再也不被观察——`_eval[id(candidate)]` 只用来做发布前
   的门禁比对，发布后的实际表现（回归指标）**无采样点、无窗口、无阈值**。
3. **抖动静默风险**：即便加了自动溶解，没有冷却期就会出现「溶解 → 重新结晶 → 再溶解」的抖动；
   phase-18 §5 的错误处理表明确要求「留出集退化 → 自动回滚，**冻结该方向（冷却期）**」。

## What Changes

- **ADDED Requirement: 观察期回归自动溶解（auto-dissolve）**——结晶发布后 SHALL 登记观察期窗口
  （记录评测基线分）；调用方持续采样回归指标，样本数达下限**且**观察均分低于「基线 − 容差」
  SHALL 自动 `dissolve`（技能标 `deprecated`、教训写回 L2 并携带回归证据）；溶解后该目标 SHALL
  进入**冻结冷却期**（期内不再触发、样本清零）；未开窗目标的采样 SHALL 被忽略（不抛异常）。
- 新增 `src/core/evolution/observation.py`：`ObservationWindow`（基线 / 样本 / 冻结截止）+
  `ObservationRegistry`（`open` / `sample` / `freeze` / `window`，阈值口径
  `_OBSERVE_MIN_SAMPLES=3`、`_REGRESSION_TOLERANCE=0.2`、`_FREEZE_COOLDOWN_S=300`）。
- `EvolutionEngine`：`crystallize` 发布成功后开窗（基线 = 该候选的 `eval.held_out_score`）；
  新增 `observe(target, score, *, now=None) -> EvolutionOutcome | None`——回归触发即
  `dissolve` + 冻结，返回 `EvolutionOutcome(status="dissolved")`。
- `EvolutionOutcome.status` 的取值集合增 `dissolved`。

## Non-goals

- **采样调度器**：engine 只提供 `observe(...)` 采样接缝，**不内建后台轮询**（谁按什么节奏采样
  ——worker 冷路径 / 未来 evaluator 循环——属调用方；本变更不做调度）。
- **回归指标的来源**：`observe` 收的是**已算好的分数**（与 `Evaluator.score_fn` 同口径的数字），
  不在 engine 内重跑评测（评测是发布前门禁，观察期是发布后的实测表现）。
- **冻结期的解冻策略**：冷却期到点即自动恢复采样（不再额外要求人工解冻/黑名单）。
- **观察窗口持久化**：进程内（进化引擎本身无持久化，如实记录）。

## Impact

- 规格：`evolution/spec.md`（+1 Requirement，5 Scenario）。
- 代码：新增 `src/core/evolution/observation.py`；`engine.py`（开窗 + `observe`）、
  `models.py`（`status` 取值注释）、`__init__.py`（导出）。
- 契约：`doc/03-interfaces/evolution-interface.md`（观察期接口 + 口径表）、ADR-0052、
  `02-modules/evolution.md`（§3.5 结晶与溶解）。
- 兼容性：`crystallize` 签名与返回不变（仅多一个副作用：开窗）；`dissolve` 签名与语义不变
  （新增的是调用者）；未调用 `observe` 时行为与今天逐字节一致。

## Risks

- **误溶解**（样本少波动大）：样本下限（3）+ 容差（0.2 绝对分差，与 `Evaluator.margin` 同形状）
  双重门控；溶解是**可逆方向**（保留教训、技能回 L3、可再结晶）。
- **抖动**：溶解即冻结该目标 `_FREEZE_COOLDOWN_S` 并清零样本，冷却期内不可能二次触发。
- **静默失效**（基线为 0 的窗口永不触发）：如实记录——绝对容差下 0 基线不会误报，也不会因
  微小波动误溶解；需要相对口径时由调用方传入合适基线。
