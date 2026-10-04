# Design: 观察期回归自动溶解（evolution auto-dissolve）

## 决策 1：观察期窗口是**独立注册表**（`ObservationRegistry`），不塞进 engine 的私有 dict

```python
# evolution/observation.py
@dataclass
class ObservationWindow:
    target: str                 # 观察目标（候选的 target_plugin，与 dissolve() 同键）
    baseline: float             # 结晶发布时的评测基线分
    samples: list[float] = ...  # 发布后的实测分（冻结时清零）
    frozen_until: float = 0.0   # 冻结冷却期截止时刻

class ObservationRegistry:
    def open(self, target: str, *, baseline: float) -> ObservationWindow
    def sample(self, target: str, score: float, *, now: float | None = None) -> bool  # 是否触发回归
    def freeze(self, target: str, *, now: float | None = None) -> None   # 冻结并清零样本
    def window(self, target: str) -> ObservationWindow | None
```

- 判定口径（下限 / 容差 / 冷却期）是**窗口的性质**，集中在注册表里；engine 只问「该溶解吗」。
  塞进 engine 私有 dict 会让阈值常量散在编排逻辑中间。
- **不采纳**「用 `Evaluator` 复用留出评测」：留出评测是**发布前门禁**（候选 vs 基线，用
  `score_fn` 跑留出集），观察期是**发布后的实测表现**——同一个「退化」概念、两个不同的数据源，
  合并会把发布前门禁拖进观察期（引擎冷路径每样本跑一次评测）。
- **不采纳**「window 存进 `GenerationCandidate`」：候选是**一次提案**的产物，窗口是**发布后**
  的生命周期；且 `crystallize` 之后候选即离场（`_pending` 出队），窗口需要独立于候选存活。

## 决策 2：回归判据 = 样本下限 + **绝对分差**（与 `Evaluator.margin` 同形状）

```python
_OBSERVE_MIN_SAMPLES = 3
_REGRESSION_TOLERANCE = 0.2   # 绝对分差：mean < baseline - tolerance
_FREEZE_COOLDOWN_S = 300.0
```

- 复用 `Evaluator.evaluate` 的退化形状 `held_out < baseline - margin`——同一套心智模型，读者不需要
  学第二种「退化」定义。
- **绝对分差**而非相对比例：分数量纲由调用方决定（成功率 / 质量分都在 `[0,1]`），绝对 0.2 的
  下降在两种口径下都算显著；相对比例在基线接近 0 时会爆炸（`baseline * (1 - tolerance)` → 0，
  任何微小波动都触发）。
- **下限 3** 挡小样本噪声（与 SOP 提炼 `_SOP_MIN_SAMPLES`、迭代 `_ITERATE_MIN_SAMPLES` 同一数量级）。
- 基线为 0 的窗口（`Evaluator` 默认 `_held_out_score` 为 0.0）在绝对容差下**不会触发**——如实
  记录：这是「宁可漏报不误杀」的取向，溶解是不可逆方向上的重动作（虽然可再结晶）。

## 决策 3：`observe` 是 engine 上的**采样接缝**，不内建调度

```python
def observe(self, target: str, score: float, *, now: float | None = None) -> EvolutionOutcome | None:
    """观察期采样；回归超阈值 → 自动 dissolve + 冻结（返回 dissolved 结局，否则 None）。"""
```

- 谁按什么节奏采样属调用方（worker 冷路径 / 未来 evaluator 循环 / 运维脚本）——本变更**不做
  调度器**（phase-18 的 `EvolutionWorker` 是「累计 N 条 trace 跑一次闭环」，与「按时间窗采样」
  是两条不同的冷路径节奏）。`now` 可注入，判定**离线可断言**。
- `freeze` 一并**清零样本**：否则冷却期结束后旧样本仍在列表里，下一票采样立刻再次越线 → 抖动。
- **不采纳**「`observe` 返回 bool」：返回 `EvolutionOutcome(status="dissolved")` 让调用方拿到
  **审计产物**（与 `run_cycle` 的返回形状一致），不需要再去 engine 里翻状态。

## 决策 4：审计留痕走**教训条目**，不新增 `Tracer` 依赖

自动溶解的回归证据（基线 / 观察均分 / 样本数）拼进 `dissolve` 的 `reason`，随既有 L2 教训条目
（`tags=["evolution","dissolve"]`，`trace_id="evolution"`）留痕。

- evolution 目前**不依赖 observability**（`EvolutionEngine` 无 tracer，`EvolutionWorker` 才持
  tracer）；为一条审计事实给引擎接一个 Tracer 会改动其构造面与装配，收益不足。
- **不采纳**「engine 注入 `Tracer`」：审计事实已由记忆层条目承载；需要可观测面时由持有 tracer 的
  worker 侧记录（与 `dissolve` 现有的留痕方式一致）。

## 已知缺口（如实记录，不扩大范围）

- **窗口进程内**：重启即失（进化引擎与候选队列均无持久化）。
- **无采样调度**：见决策 3；「按什么节奏采样多久」未定义。
- **单目标单窗口**：同一 `target` 重新结晶会**覆盖**窗口（`open` 幂等重开）——这是刻意的
  （重新发布 = 重新起算基线），但历史观察数据不保留。
