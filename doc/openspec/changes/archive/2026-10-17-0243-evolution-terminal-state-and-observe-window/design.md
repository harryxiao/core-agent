# Design — evolution：pending 终态化 ＋ 观察期滑动窗口

## 背景

review 的 M3/M5 同属 evolution 的**状态面**：候选台账把「已判失败」与「待人工确认」混在同一
快照，观察窗口把「开窗以来全部样本」当作判定材料。两者都不是规模问题，而是**判定语义**问题，
故同 change 收口。

## D1 三类失败结局显式置终态

`EvolutionEngine.run_cycle` 在 `self._pending.record(...)` **之前**设置 `candidate.status`：

| 分支 | 终态 | 理由 |
|---|---|---|
| 门禁未过 | `rejected` | 规格（运行时测试未过场景）已要求「记候选为 rejected」，实现此前漏置 |
| 留出评测 `rollback` | `rejected` | 已判退化 ⇒ 不可发布；`EvolutionOutcome.status` 仍保留 `rollback` 以区分「退化」与「门禁拒绝」 |
| 留出评测 `freeze` | `frozen` | 「无法评测」不是退化、也不是人工可确认的候选；独立终态避免被误当作 rejected（与 `EvalReport.verdict` 三态对齐） |

`PendingQueue.pending()` 不变（仍只收 `pending`）—— 修的是**状态未被设置**，不是过滤面。
`GenerationCandidate.status` 词表扩为 `pending | confirmed | rejected | frozen | implemented`。

## D2 恢复 fail-closed

`_candidate_from_dict` 的缺省方向反转为「按最危险解释」：

- 未知/缺失 `kind` ⇒ `plugin`（架构级，`confirm` 需审批单）；
- 未知/缺失 `risk_level` ⇒ `high`；
- 缺失/未知 `status` ⇒ `rejected`（不进入待确认快照）；
- `caliber` 缺失保持 `0`（既有行为：不可结晶，`GATE_CALIBER_STALE`）。

**取舍**：旧格式/损坏记录可能被过度保守地当作架构级候选；这是有意的——恢复路径无法证明记录
完整，fail-closed 优先（与门禁/评测的 fail-closed 同哲学）。正常记录四字段齐全，行为不变。

## D3 观察窗口滑动窗口

- 新常量 `_OBSERVE_MAX_SAMPLES = 64`，`ObservationRegistry(max_samples=64)`。
- `sample()` 追加后若超界，删除最旧样本（`del samples[:-max]`），再判回归；`_load()` 同样裁剪。
- `mean` 属性不变（对当前 `samples` 求均值）—— 语义由「全部历史」变为「最近窗口」。
- `max_samples < min_samples` 的配置视为无效？**不额外校验**：保持构造面简单，由调用方负责
  （缺省 64 ≥ 3；测试可显式设置小窗口）。若误配，回归永不触发（样本数永远不足），是保守侧。

**为什么不是 EWMA**：EWMA 引入平滑系数这一新决策参数，且不可解释（教训条目要报「样本数」）；
滑动窗口的语义（最近 N 条）可直接写进规格与教训，运维可复现。

## D4 基线口径写明而非改码

基线仍是 `crystallize` 时的 `eval_report.held_out_score`。review 指出在线样本是 trace 成功率、
与留出质量分不同量纲；本 change **不改**基线来源（发布时没有在线样本，无法标定在线基线），
而是在规格中明确「代理可比、容差吸收量纲差、基线不随样本重估」，并登记为 ADR 局限。

## 测试面

- 终态化：门禁拒绝 / rollback / freeze 三支各一条；断言 `status` 与 `pending()` 为空。
- 恢复：构造缺失 kind/risk/status 的落盘 JSON，断言 `plugin` / `high` / 非 pending。
- 滑窗：上界保持（含 reload）；「早期好样本不得稀释近期回归」的反例（累计均分会永不触发）。
- 基线：多次采样后 `window.baseline` 不变。

## 局限

- 观察窗口仍是**进程内 + 单文件**状态；多进程并发采样无锁（既有局限，未扩大）。
- `frozen` 只影响待确认快照；操作面若按 `find()` 直接取候选仍可看到它（留痕需要），
  `crystallize` 的既有门禁/评测校验仍会拒绝。
