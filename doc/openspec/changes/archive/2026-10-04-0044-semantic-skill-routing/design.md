# Design: 语义路由（semantic skill routing）

## 决策 1：语义兜底只在「词法全无命中」时触发（词法是 fast path）

```python
candidates = [s for s in self._library.all_skills() if s.status in ("active", "gray")]
scored = [SkillMatch(skill=s, score=self._score(s, terms)) for s in candidates]
scored = [m for m in scored if m.score > 0] or self._semantic(task, candidates)
scored.sort(key=lambda m: m.score, reverse=True)
if not scored:
    self._record_miss(task)
```

- 词法命中路径**零模型调用、零行为变化**；语义只在今天会「记 miss 后丢弃」的那条死路上补一次
  机会——正是 M3 遗留（miss 只沉淀不复用）的收口点。
- **不采纳**「每次都用语义打分并与词法融合」：`match` 在每个推理轮都调一次（`planner._skill_hints`），
  每轮 K 次 judgment 调用会把辅助决策成本抬到主路径上；且词法已是确定性、可离线断言的口径。

## 决策 2：打分走 judgment `score` 原语，逐候选一次调用（domain adapter 落在 judgment 域）

`score` 原语的返回值是**条目集的单一分数**（`answers["score"]["score"]`），**无 per-item 分数**
（与 0042 `importance` 打分同一约束，见 ADR-0047 决策 ③）。故 K 个候选 = K 次 `decide()`。

```python
# src/core/judgment/skills.py
class SkillMatcher:
    def __init__(self, router: DecisionRouter) -> None: ...
    def score(self, task: str, skills: list[dict[str, Any]]) -> dict[str, float]:
        return {skill["skill_id"]: value for skill in skills if (value := self._score_one(...)) > 0}
```

- 落在 **judgment 域**（照 `judgment/compactor.py` 的 `Compactor` 先例）：skills 域的 seam 只声明
  「(task, 候选) → {skill_id: 分}」，**不 import judgment**；judgment 侧只吃 dict、**不 import skills**
  → 两边都不知道对方的类型，依赖方向与 0043 的 `SopWriter` 一致。
- **不**把打分循环放进 `SkillRouter`（那会让 skills 需要 judgment 的请求形状）；**不**改
  `score` 原语为逐条返回（judgment 规格变更，blast radius 覆盖 JEV prompt 与 router 解析）。

## 决策 3：阈值 `_SEMANTIC_MIN_SCORE = 0.5`；回退分 0.0 自然等价词法

- 低于阈值**不采纳**：否则任何任务都能匹配上某条技能，技能块被灌水进 prompt（白烧 token）。
- JEV 不可达 / 低置信度回退主 LLM 时，`_fallback_answer` 给 SCORE 的答案是 `score=0.0`
  → 恒低于阈值 → **语义路径自然退化**，不需要额外开关。
- 阈值经 `SkillRouter(threshold=...)` 可调（构造参数，缺省常量）。

## 决策 4：逐候选失败跳过（打分是咨询性查询，其失败不得中断路由）

```python
# SkillMatcher._score_one：坏答案 / 调用失败 / 回退（0.0）一律返回 0.0
try:
    return float(self._router.decide(request).answers["score"]["score"])
except Exception:      # noqa: BLE001 — 逐候选跳过，坏答案不污染候选集
    return 0.0

# SkillRouter._semantic：打分器整体故障 → 空（match 不向调用方抛异常）
try:
    scores = self._scorer(task, [_snapshot(s) for s in candidates])
except Exception:      # noqa: BLE001 — 降级为纯词法
    return []
```

- `match` 由 `planner._system_prompt` 直接调用（**无异常包裹**），抛出会打断本轮推理；打分是
  无副作用的咨询性查询，降级为「该候选无分」是正确的失败面（与 0042 逐条目打分同一取向）。
- 打分为 0/缺失的候选不进入候选集（不产生 `score=0.0` 的伪命中）。

## 决策 5：语义命中即命中，不再记 miss

miss 的**用途**是「无技能可用 → 记录供新技能沉淀」。语义已把任务与已有技能接上时记 miss 是
假信号（会同时污染 `misses`（M3 的沉淀入口）且与「路由未命中沉淀」场景的字面语义冲突）。
故：有命中（词法或语义）则不记 miss；两者都无 → 记 miss（行为不变）。

## 决策 6：B4 收口 = 删除 `ContextPack.skills`（用户 2026-10-04 定夺）

- 该字段**无生产者**（`DynamicAssembler.build` 从不填）**无消费者**（planner 从 `skill_router`
  回调取技能）；唯一引用是 `BudgetManager` 的裁剪/计量与 `context-interface.md` 的声明。
- **不采纳**「装配器填充、planner 读 pack」：技能将与事实争同一预算（`enforce` 先裁 facts、
  skills 只吃**剩余**），记忆丰富时技能会被挤出 prompt——今天是**恒注入**，属功能退化。
- 连带删除：`BudgetManager.enforce` 的 skills 裁剪行、`_measure` 的 skills 计量行、
  `context-interface.md` 的字段行与保留策略中 skills 一句、`test_context` 的 skills 用例。
- 规格侧无对应 Requirement（context spec 从未提及 skills）→ **删除是规格中性**的；`ContextPack`
  构造方均未传该字段，删除对生产零影响。B5 的 `_trim` 修复仍适用于 facts（`continue` 语义未动）。

## 已知缺口（如实记录，不扩大范围）

- **语义分只用于排序，无历史成功率加权**：`SkillMatch.score` 的接口注释写着「语义 + 历史成功率
  + 适用声明」，历史上成功率维度仍缺（需命中/结果反馈闭环，属 #8 Skill 迭代）。
- **候选未预筛**：词法 miss 时对全部 active/gray 技能逐条打分（K 次调用）；技能库规模上来后需
  加粗筛（如摘要向量），暂以「只在 miss 时触发」控成本。
