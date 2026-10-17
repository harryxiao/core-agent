## Why

记忆与 evolution 全量 review 的**批次 C（规模/决策质量）**中，evolution 侧有两项确定缺陷：

1. **待确认队列保留「已死」候选**：`run_cycle` 的门禁拒绝、留出退化、无法评测三个分支只返回
   outcome，**不把候选置终态**；而 `pending()` 只按 `status == "pending"` 过滤 ⇒ 已判失败的候选
   仍出现在 `evolve pending` 队列里。用户 `confirm` 后 `crystallize` 才抛
   `GATE_REJECTED` / `EVAL_REGRESSED` / `EVAL_FROZEN`，操作面语义混乱。附带恢复面 fail-open：
   落盘记录缺失 `kind` / `risk_level` 时按 `skill` / `low` 恢复，损坏/旧格式记录可绕过架构级审批。
2. **观察期累计均分会被早期样本稀释且样本无界**：`ObservationWindow.mean` 对开窗以来**全部**样本
   求均值，样本列表只追加、无上限。发布后早期好样本会永久掩盖后期回归（退化永不触发）；长跑下
   窗口状态无界增长。基线口径（留出评测分 vs 在线成功率）也未在规格中写明是代理可比。

## What Changes

- **evolution**：`run_cycle` 的三类失败结局在落盘前置终态（门禁拒绝 / 留出退化 ⇒ `rejected`；
  无法评测 ⇒ `frozen`），终态候选不再进入待确认快照；台账恢复对未知/缺失 `kind` / `risk_level`
  取 fail-closed（`plugin` / `high`），缺失/未知 `status` 不恢复为 `pending`。
- **evolution**：观察窗口样本有上界（`max_samples`，缺省 64），超界淘汰最旧样本、判定均分只在
  最近样本上计算（滑动窗口）；规格明确基线为发布时留出分、在线样本为成功率，二者仅代理可比且
  基线不随样本重估。

## Impact

- 规格：evolution「观察期回归自动溶解（auto-dissolve）」「人工确认队列的持久化与操作面」MODIFIED。
- 代码：`src/core/evolution/engine.py`、`src/core/evolution/pending.py`、
  `src/core/evolution/observation.py`、`src/core/evolution/models.py`（状态词表注释）。
- 行为：已判失败的候选不再出现在 `evolve pending`；观察期判定只看最近 64 条样本；损坏台账记录
  按高风险处置。均为缺陷修复（无配置开关；正常落盘记录行为不变）。
- 不做：`Evaluator.margin` 口径（M6，属需人工裁决的评测策略，不在本批次）；benchmark 记忆隔离
  与 CJK token 估计（另两个 change）。
