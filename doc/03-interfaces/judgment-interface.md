# 接口设计：决策（Judgment Interface）

> 模块：`02-modules/judgment.md` ｜ 规格：`openspec/specs/judgment/spec.md`

---

## 1. 实体模型

```python
from enum import Enum

class DecisionPrimitive(str, Enum):
    """决策原语：choice 选项路由 / score 评分筛选 / noul 布尔判断。"""
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"

@dataclass
class DecisionRequest:
    """决策请求：state + 类型化问题，提交给 JEV System One 决策。"""
    primitive: DecisionPrimitive      # 决策原语
    state: str | dict | list          # 决策上下文状态（纯文本 / 结构化数据）
    questions: dict                   # 类型化问题（map<question_id, Question>）
    options: list[str] | None         # choice 原语的候选选项
    threshold: float | None           # 置信度回退阈值（None 用默认）

@dataclass
class DecisionResult:
    """决策结果：answers 按原语分形（noul→noul / choice→choice+probabilities+confidence / score→score+legend+probabilities+confidence）。"""
    primitive: DecisionPrimitive
    answers: dict                     # 类型化答案（map<question_id, Answer>，按原语分形）
    fallback: bool                    # 是否回退主 LLM

@dataclass
class DecisionTrace:
    """决策轨迹：落 observability 供进化/审批消费。"""
    trace_id: str
    request: DecisionRequest
    result: DecisionResult
    ts: float                         # 决策时间戳
```

---

## 2. DecisionRouter 接口

```python
class DecisionRouter:
    def choose(self, state: dict, options: list[str], threshold: float | None = None) -> DecisionResult:
        """以 choice 原语从候选中路由出唯一分支，选中项及置信度见 result.answers。"""

    def decide(self, request: DecisionRequest) -> DecisionResult:
        """统一决策入口：按原语分发到 JEV，低置信度自动回退主 LLM。"""
```

---

## 3. JEVProvider 接口

```python
class JEVProvider:
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float = 30.0):
        """经 TypeSafe 专有 REST 端点挂接 JEV（base_url 指向 /v1/systemone 宿主，Bearer 认证）。"""

    def query(self, state: str | dict | list, questions: dict) -> dict:
        """提交 state + typed questions（map<id, Question>），返回 typed answers（map<id, Answer>，按原语分形）。"""
```

---

## 4. Compactor 接口

```python
class Compactor:
    def score(self, state: dict, items: list[dict], threshold: float | None = None) -> DecisionResult:
        """以 score 原语对候选内容评分，供记忆压实保留/丢弃决策。"""
```

---

## 4.1 SkillMatcher 接口

技能语义匹配（decision adapter，同 `Compactor` 的落域口径：**只吃 dict，不 import skills**）。

```python
class SkillMatcher:
    def score(self, task: str, skills: list[dict]) -> dict[str, float]:
        """(任务文本, 候选技能快照) → {skill_id: 分值}；每候选一次 score 调用。"""
```

- **逐候选一次调用**：`score` 原语只给「条目集单一分数」（无 per-item 分数）→ K 个候选即 K 次
  `decide()`，每次只送一条候选。
- **容错**：单候选坏答案 / 调用失败 / 回退（回退答案给 SCORE 的分恒为 0.0）→ 该候选略过
  （不产生 `score=0.0` 的伪命中，也不向调用方抛错）。
- **用途**：`SkillRouter` 词法无命中时的语义兜底（见 skills-interface §4）；未配置 JEV 时不构造。

---

## 4.2 SopGate 接口

SOP 发布前的**自动**质量门（decision adapter，同 `SkillMatcher` 的落域口径：**只吃文本、不 import
skills**）。「该提炼产物是否可复用 / 可执行 / 非空泛」由 **noul** 原语作答 ⇒ 守红线「维度1
技能库/SOP **全自动**」（**不**引入人工确认）。

```python
class SopGate:
    def __call__(self, task: str, sop: str) -> bool:
        """(任务文本, 提炼正文) → 是否放行；判定**故障 / 缺答案 ⇒ True**（fail-open）。"""

def sop_gate_with(router: DecisionRouter) -> SopGate:
    """把 noul 原语适配为 SOP 提炼器的质量门契约（skills 侧 `SopGate = Callable[[str,str],bool]`）。"""
```

- **载荷**：`state={"task": …}`、`questions["noul"]["action"]={"kind": "publish_sop", "sop": 正文}`
  —— 门**必须**看到正文才判得动质量；该载荷进既有 `DecisionTrace` 观测面（与 `Guardrail` 把
  `action` 交给 trace 同口径，未新增暴露面）。
- **fail-open**：路由抛异常 / 答案缺 `noul` 键 ⇒ **放行**（门是**新增**的刹车，判定故障不得把
  「一直正常发布」变成**静默不发布**）。**边界**：`DecisionRouter` 自身的降级链**不冒泡** ——
  provider 不可达即回退主 LLM，其答案（含主 LLM 亦不可用时给出的 `False`）都算**有结论** ⇒
  该情形门**拒**（每次拒有调用方告警留痕，故不静默）。
- **用途**：`SopExtractor(gate=…)`（见 skills-interface §6）；未配置 JEV 时不构造（`gate=None`）。

---

## 5. Guardrail 接口

```python
class Guardrail:
    def check(self, state: dict, action: dict, threshold: float | None = None) -> DecisionResult:
        """以 noul 原语做守卫判断，返回放行/拦截结论（是/否，见 result.answers[id].noul）。"""
```

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `JUDGMENT_PROVIDER_UNREACHABLE` | JEV 端点不可达 |
| `JUDGMENT_SCHEMA_MISMATCH` | 类型化答案与问题 schema 不匹配 |
| `JUDGMENT_LOW_CONFIDENCE` | 置信度低于阈值（触发主 LLM 回退；仅 choice/score 有置信度，noul 以概率接近 0.5 判定） |
| `JUDGMENT_TIMEOUT` | JEV 决策超时（回退主 LLM） |
| `JUDGMENT_INVALID_PRIMITIVE` | 未识别的决策原语 |

---

## 7. 关联

- 模块：`02-modules/judgment.md`
- 规格：`openspec/specs/judgment/spec.md`
- 挂载：`02-modules/loop.md`（决策点 choice 路由）、`02-modules/memory.md`（记忆压实 score）、`02-modules/permission.md`（守卫 noul 判断）
