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
