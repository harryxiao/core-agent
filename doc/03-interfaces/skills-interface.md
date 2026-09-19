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
class SkillRouter:
    def match(self, task: str, *, top_k: int = 3) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K。"""

@dataclass
class SkillMatch:
    skill: Skill
    score: float                # 匹配度（语义 + 历史成功率 + 适用声明）
```

无匹配时返回空列表，由 loop 回退通用流程并记录未命中（供新技能沉淀）。

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

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `PRECONDITION_FAILED` | 前置条件不满足 |
| `INVALID_SKILL_SCHEMA` | 技能 schema 非法 |
| `NO_SKILL_MATCH` | 路由无匹配 |

---

## 7. 关联

- 模块：`02-modules/skills.md`
- 规格：`openspec/specs/skills/spec.md`
