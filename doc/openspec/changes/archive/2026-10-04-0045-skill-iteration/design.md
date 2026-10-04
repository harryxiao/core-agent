# Design: 技能迭代闭环（skill iteration）

## 决策 1：命中注入的载荷是「纯 dict 快照」，由组合根组装（loop 不 import skills）

```python
# loop/planner.py —— 渲染纯数据（loop 不知道 skills 类型）
SkillHint = dict[str, str]                      # {"skill_id", "version", "instructions"}
skill_router: Callable[[str], list[SkillHint]] | None
#   blocks.append("可用技能：\n" + "\n".join(_format_skill_hint(h) for h in hints))

# runtime.py —— 闭包组装：路由 → 版本解析 → 记命中 → 快照
def _skill_hints(task: str) -> list[SkillHint]:
    hints: list[SkillHint] = []
    for m in skill_router.match(task):
        version, text = skill_iterator.resolve(m.skill)
        skill_feedback.record_hit(m.skill.skill_id, version=version)
        _surfaced.append((m.skill, version))
        hints.append(skill_hint(m.skill.skill_id, version, text))
    return hints
```

- 与 #6 的 `SopObserver`、#7 的 `SkillScorer`、`facts: list[dict[str, str]]` 同一口径：跨域接缝只
  传**纯数据**，类型知识留在各自域内（`test_architecture` 红线：loop 不得 import skills）。
- **不采纳**「让 `SkillRouter.match` 直接返回含 instructions 的对象再序列化」：路由返回
  `SkillMatch`（skills 类型）是 skills 域内的自然形态，注入是**组合根**的职责（谁持版本与反馈，
  谁组装提示）。
- 节选上界 `_MAX_HINT_CHARS = 400`（与 `_MAX_STEP_CHARS` / `_MAX_ACTION_EXCERPT` 同一口径）。

## 决策 2：loop 收尾钩子扩为 `TurnObserver(task, steps, ok)`（用户 2026-10-04 定夺）

```python
# loop/default.py
TurnObserver = Callable[[str, list[str], bool], object]
# astream 收尾：self._notify_turn(ctx, trace_id, ok=not limit_reason)  # 成功/失败都提交
```

- 「结果不达标」的**唯一来源**是本轮收尾的成功/失败状态（`limit_reason` 即失败）；只有成功信号
  则无法感知执行失败，迭代判据失真。故把 #6 的 `SopObserver`（成功专语义）扩为携带 `ok` 的通用
  收尾钩子，`SopExtractor.observe(..., ok=False)` 仍**只吸收成功**（#6 语义不变）。
- **不采纳**「新增第二个 outcome 钩子」：一个收尾点两个钩子冗余；**不采纳**「成功-only 弱信号」
  （以「同组任务反复出现」代替失败率，判据不可信）。
- 钩子抛错仍降级留痕（`turn_observer_failed`，原 `sop_extract_failed` 随语义泛化更名），
  **不改变本轮结果与终止语义**。

## 决策 3：反馈按 `(skill_id, version)` 累计，进程内、不上报

```python
skills/feedback.py
@dataclass
class SkillStats:  hits: int; ok: int; fail: int   # failure_rate / total 为派生属性
class SkillFeedback:
    def record_hit(self, skill_id, *, version) -> None
    def record_outcome(self, skill_id, *, version, ok) -> None
    def stats(self, skill_id, *, version=None) -> SkillStats   # version=None → 合计
    def success_rate(self, skill_id, version) -> float         # 无样本 → 0.0
```

- 版本维是 A/B 的前提（同一技能的两版本各自统计）；`version` 显式关键字参数，避免 (id, ok)
  这类易错的位置歧义。
- 不落盘、不写记忆：反馈是**运行时统计**，不是需要跨会话追溯的事实（技能库本身也无持久化）。

## 决策 4：迭代 = 复用 `VersionManager`（灰度 + A/B），不新增 A/B 引擎

```python
skills/iteration.py
class SkillIterator:
    def __init__(self, library, feedback, *, writer=None, versions=None,
                 threshold=_ITERATE_FAILURE_RATE, min_samples=_ITERATE_MIN_SAMPLES,
                 ratio=_GRAY_RATIO, tracker=None)
    def resolve(self, skill) -> tuple[str, str]      # (版本, instructions) —— 版本来 VersionManager.select
    def consider(self, skill) -> str | None          # 不达标 → 生成草稿 + 灰度，返回草稿版本号
    def decide(self, skill) -> ABResult | None       # 双版本样本齐 → A/B 定夺并落地/丢弃
```

- **灰度**用 `VersionManager.promote(skill_id, draft, ratio)`；**选版**用 `VersionManager.select`
  （A/B 胜者 > 灰度 > 稳定版 > 当前版），两者都是既有能力——本次只是**接上了调用者**（ADR-0048
  决策 ⑥ 记的缺口）。
- **A/B 指标** = 各版本成功率：`VersionManager(library, metrics=lambda sid, ver: feedback.success_rate(sid, ver))`，
  `ab_test` 的 `b < a → revert / b > a → promote` 语义与「成功率越高越好」一致。
- **退化只丢草稿**：`ab_test` 的 revert 分支会尝试 `_deprecate(skill_id, v_b)`，而草稿版本**不是**
  库中 `Skill.version`（仍为原版本）→ 该调用自然 no-op，**技能不会被误标 deprecated**（这是刻意
  依赖的既有行为，测试显式覆盖）。
- 草稿 `instructions` 存 `SkillIterator._versions[skill_id][版本]`（库中 `Skill` 仍是当前版本）；
  `resolve` 按选中的版本取值，取不到即回退 `skill.instructions`。
- **落地**（promote）：写回 `skill.version` / `skill.instructions`，并登记
  `Effect(op="skills.iterate", undo=恢复原版本与原 instructions)`（P2 可逆；未注入 tracker 时不记）。

## 决策 5：触发点全在组合根闭包（loop 只持一个纯数据回调）

```python
def _on_turn(task: str, steps: list[str], ok: bool) -> None:
    for skill, version in _surfaced:
        skill_feedback.record_outcome(skill.skill_id, version=version, ok=ok)
        skill_iterator.decide(skill)          # 样本齐 → A/B 定夺（每轮都可发生）
        if not ok:
            skill_iterator.consider(skill)    # 失败轮触发迭代（阈值门在 iterator 内）
    _surfaced.clear()
    sop_extractor.observe(task, steps, ok=ok)
```

- `_surfaced` 是**每轮命中**的 (skill, version) 快照，在 `_skill_hints` 里填充、在收尾时消费——
  两处都在组合根，loop 不感知（架构红线）。
- 子 Agent 的 loop 用同一组闭包接线（同 #6/#7）。

## 已知缺口（如实记录，不扩大范围）

- **改写 prompt 无失败轨迹**：只有「现行 instructions + 命中/失败计数」，改写依据弱于「看了失败
  轨迹再改」；轨迹级诊断属维度2（diagnose）。
- **样本进程内、跨进程不共享**：重启即归零（技能库本身亦无持久化）。
- **单轮迭代路径**：草稿被丢弃后需重新累计样本才会再次触发；无 cooldown、无轮数上限（技能库
  规模小时迭代成本可控）。
- **成功率口径粗**：只区分成功/失败，不区分「成功但偏离」；`instructions` 是否被模型实际采纳
  无法观测（无引用检测）。
