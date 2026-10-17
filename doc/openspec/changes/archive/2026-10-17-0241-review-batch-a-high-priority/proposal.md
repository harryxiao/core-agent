# Proposal 0241: 记忆与进化高危面收口（评测异常 / 派生豁免 / 密钥脱敏）

## 为什么

对记忆模块与 evolution 决策路径的全量 review 发现三处高危缺口：

1. **评测器异常击穿进化闭环**：`BenchmarkScorer` 的执行器异常按规格**冒泡**，但
   `Evaluator.evaluate` 未捕获 ⇒ 异常直穿 `EvolutionEngine.run_cycle` / `EvolutionWorker.maybe_run`
   ⇒ 本轮候选**不进台账、不产出 `frozen`**，`_sample_observations` 与 `_completed.clear()`
   均不执行，下一轮重放同一批 trace。规格（evolution「留出评测」）明确要求评测器据此判
   `freeze`，实现未对齐。
2. **情景归纳产物被重要度闸门误伤**：`_GATE_EXEMPT_SOURCES` 已含 `compaction` / `context` /
   `extraction` / `relation`，唯独漏了 `episodic`。压实产出的情景归纳结论是**派生结论**，
   却会因低分被拒收或降层 —— 与「派生结论不得因评分而丢失或降层」的规格语义相反。
3. **密钥脱敏闭环有缺口**：摘要器返回的摘要、循环轨迹条目、进化侧的溶解原因 / 人工拒绝理由 /
   技能内容字段均**原样落库**。这些文本来自模型或人工输入，**不构成信任边界**；一旦夹带
   明文密钥即违反「密钥只引用不读取、绝不进日志/记忆」。

## 做什么

- **A1 评测器 fail-closed**：`Evaluator.evaluate` 捕获留出打分抛出的 `Exception` ⇒ 返回
  `verdict="freeze"`（与「无留出分」同一结论口径）。`run_cycle` 因而把候选记入台账并以
  `status="frozen"` 返回，而非抛出。
- **A2 派生来源豁免**：`episodic` 加入 `_GATE_EXEMPT_SOURCES`；同步修正 `store.py` 中
  「豁免评分 ≠ 豁免遗忘」注释（episodic 是第三类来源，不参与 `forget`，属刻意设计）。
- **A3 脱敏闭环**：
  - `_commit_summary` 落库前对摘要无条件 `redact_secrets`（store 侧执行，注入摘要器不构成信任边界）。
  - 循环轨迹条目写入前对**整条内容**执行与行动序列同源的 `redact_secrets`。
  - `dissolve` 的 `reason`、`reject` 的 `reason`、`_crystallize_skill` 的
    `description` / `preconditions` / `task_types`、`_crystallize_plugin` 的 `issue` 落库前脱敏。

## 不做什么

- 不改评测决策口径（`margin=0.0`、基线是绝对阈值）—— 属批次 C。
- 不改 `episodic` 的遗忘策略（`forget` 对它是另一面，既有语义不变），只修注释与评分豁免。
- 不对 `param_schema`（结构化字段名/类型）做文本改写。
- 不引入新配置键；缺省行为除上述缺陷路径外逐字不变（未命中密钥形态时脱敏为恒等变换）。

## 影响

- `src/core/evolution/evaluator.py`、`src/core/evolution/engine.py`
- `src/core/memory/store.py`
- `src/core/loop/default.py`
- 规格：memory「写入侧重要度闸门」「记忆压实」、loop「执行循环」、evolution 新增「进化写回与
  技能内容的密钥形态脱敏」
