# 接口设计：技能封装（Skills Interface）

> 模块：`02-modules/skills.md` ｜ 规格：`openspec/specs/skills/spec.md`

---

## 1. 技能定义

```python
@dataclass
class Skill:
    skill_id: str               # 全局唯一，如 "skills.data_analysis.summarize"
    description: str
    task_types: list[str]       # 适用任务类型
    preconditions: list[str]    # 前置条件
    param_schema: dict
    instructions: str           # 执行说明
    version: str                # 世代版本 v1/v2...
    status: str                 # "draft" | "active" | "gray" | "deprecated"
```

---

## 2. SkillLibrary 接口

```python
class SkillLibrary:
    def register(self, skill: Skill) -> None:
        """入库；schema 非法抛 INVALID_SKILL_SCHEMA。"""

    def lookup(self, skill_id: str) -> Skill: ...

    def list_by_domain(self, domain: str) -> list[Skill]: ...

    def check_preconditions(self, skill: Skill, ctx: dict) -> bool:
        """前置条件不满足返回 False（PRECONDITION_FAILED）。"""
```

---

## 3. VersionManager 接口

```python
class VersionManager:
    def promote(self, skill_id: str, version: str, ratio: float) -> None:
        """灰度发布：新版本仅对 ratio 比例任务生效。"""

    def ab_test(self, skill_id: str, v_a: str, v_b: str) -> ABResult:
        """A/B 并行，用 observability 指标量化对比。"""

    def select(self, skill_id: str, ctx: dict) -> str:
        """按灰度/A/B 结果返回应使用的版本。"""

@dataclass
class ABResult:
    winner: str | None
    metric_delta: dict          # 各指标对比
    decision: str               # "promote" | "revert" | "keep"
```

---

## 4. SkillRouter 接口

```python
# 语义打分器接缝：(任务文本, 候选技能快照) → {skill_id: 分值}；缺省不启用（纯词法）
# 快照为 dict（不含 skills 类型）——实现侧（judgment.SkillMatcher）不依赖本模块
SkillScorer = Callable[[str, list[dict]], dict[str, float]]

class SkillRouter:
    def __init__(
        self,
        library: SkillLibrary,
        *,
        memory: MemoryStore | None = None,
        scorer: SkillScorer | None = None,
        threshold: float = 0.5,
    ) -> None: ...

    def match(self, task: str, *, top_k: int = 3) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K。"""

@dataclass
class SkillMatch:
    skill: Skill
    score: float                # 匹配度（词法命中率 / 语义分；历史成功率见 #8 缺口）
```

无匹配时返回空列表，由 loop 回退通用流程并记录未命中（供新技能沉淀）。

| 维度 | 口径 |
|---|---|
| **词法 fast path** | 词元包含匹配（命中率 = 命中词元 / 任务词元）；**命中即返回，零模型调用** |
| **语义兜底触发** | 仅当词法**全无命中**时才调打分器（避免把辅助决策成本抬到每个推理轮） |
| **候选集** | 仅 `active` / `gray` 技能（`draft` / `deprecated` 不打分） |
| **阈值** | 语义分 ≥ `threshold`（缺省 0.5）才采纳，按分降序取 Top-K |
| **降级** | 未注入打分器 / 打分器抛错 / 分值低于阈值 → 行为与纯词法一致（空结果 + 记 miss）；`match` 不向调用方抛异常 |
| **miss 口径** | 有命中（词法或语义）则不记 miss；两者皆无才记（miss 是「无技能可用」信号，供新技能沉淀） |
| **接线** | `build_runtime`：`scorer=SkillMatcher(router) if jev is not None else None`（未配置 JEV → 纯词法） |

---

## 5. 结晶/溶解接口

```python
class SkillCrystallizer:
    def crystallize(self, skill: Skill) -> bool:
        """复用次数达阈值 + 过验证门 → 结晶为 L1 插件（联动 evolution）。"""

    def dissolve(self, skill_id: str, reason: str) -> None:
        """失效/退化 → 溶解回 L3 技能，教训写回记忆。"""
```

---

## 6. SOP 提炼接口

把**同一类任务的多次成功轨迹**聚合、提炼为一条 `Skill`（技能库的产出入口；此前只有
注册 / 路由 / 版本三段，没有任何产生技能的路径）。

```python
# 提炼接缝：prompt → SOP 文本（skills 不 import LLM 抽象，组合根注入模型调用）
SopWriter = Callable[[str], str]

def build_sop_prompt(task: str, steps: Sequence[str]) -> str:
    """把一组成功轨迹渲染为提炼 prompt（逐条节选，token 有界）。"""

def sop_writer_with(llm: Callable[[str], str]) -> SopWriter:
    """把「prompt → 文本」的模型调用适配为提炼契约（同 memory.Summarizer 方向）。"""

class SopExtractor:
    def observe(self, task: str, steps: Sequence[str], *, ok: bool = True) -> Skill | None:
        """提交一条轨迹；达阈值则提炼入库并返回技能，否则返回 None。"""
```

| 维度 | 口径 |
|---|---|
| **调用方** | `DefaultLoop` 收尾钩子（`SopObserver`）——成功收尾提交（任务文本, 行动/结果序列）；失败轨迹不提交 |
| **归组键** | 优先词法命中已有技能的 `task_types` 并复用其作组键，否则「任务词元签名」（`terms_of` 与 SkillRouter 同口径）——确定性、离线可断言 |
| **阈值** | 同组累计达 3 条（`_SOP_MIN_SAMPLES`）提炼一次，提炼后**清空该组**（下批重新累积） |
| **产物** | `skill_id="skills.sop.<组键 blake2b-8hex>"`（确定性、同组重复提炼覆盖同一条）、`description="SOP：<组键>"`、`task_types=[组键]`、`instructions=<提炼文本>`、`status="active"` |
| **发布口径** | `active`（维度1 技能库层属低风险自动发布）；`draft` 对路由不可见 → 不置 draft |
| **降级** | 未注入 writer：不累积、不提炼（零额外模型调用）；提炼文本为空：不入库、样本保留待下轮 |
| **可逆** | 入库登记 `Effect(op="skills.register", undo=移除)`（`trace_id="skills.extract"`）；回滚即移除，重复回滚幂等 |

已知缺口（如实记录）：技能库无持久化（进程内注册表，重启即失）、无 judgment 质量门、
样本仅进程内累积（不落盘）。质量门与版本迭代归 Phase 18 #8。

---

## 7. 错误码

| 错误码 | 含义 |
|---|---|
| `PRECONDITION_FAILED` | 前置条件不满足 |
| `INVALID_SKILL_SCHEMA` | 技能 schema 非法 |
| `NO_SKILL_MATCH` | 路由无匹配 |

---

## 8. 关联

- 模块：`02-modules/skills.md`
- 规格：`openspec/specs/skills/spec.md`
