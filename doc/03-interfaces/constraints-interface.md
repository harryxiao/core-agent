# 接口设计：约束与中间件（Constraint & Middleware Interface）

> 模块：`02-modules/constraints.md` ｜ 规格：`openspec/specs/constraints/spec.md`

---

## 1. 中间件统一契约

```python
class Middleware(Protocol):
    name: str
    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        """输入侧处理：校验/熔断/重试。"""
    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        """输出侧处理：校验/回滚。"""
```

洋葱模型执行：`before` 顺序执行 → 核心 → `after` 逆序执行。

---

## 2. Validator 接口

```python
class Validator(Middleware):
    def validate_input(self, tool: str, args: dict, schema: dict) -> list[str]:
        """输入校验：schema/类型/coeffect；返回错误列表（空=通过）。"""

    def parse_output(self, raw: str, schema: dict) -> ParsedOutput:
        """把自由文本解析为结构化指令；失败抛 OutputParseError。"""
```

---

## 3. CircuitBreaker 接口

```python
class CircuitBreaker(Middleware):
    def before(self, ctx, req) -> ExecRequest:
        """OPEN 状态快速失败；HALF_OPEN 半开试探。"""

    def record_result(self, success: bool) -> None:
        """成功/失败计数；连续 N 次失败 → OPEN。"""

    @property
    def state(self) -> str:   # "CLOSED" | "OPEN" | "HALF_OPEN"
```

---

## 4. RetryPolicy 接口

```python
class RetryPolicy(Middleware):
    def should_retry(self, attempt: int, error: Exception) -> bool:
        """幂等操作才允许重试；指数退避 + 抖动。"""

    def backoff(self, attempt: int) -> float:
        """返回退避秒数（指数 + 抖动）。"""
```

---

## 5. Fallback / Rollback 接口

```python
class Fallback(Middleware):
    def on_failure(self, ctx, req, error) -> ExecResponse:
        """降级：备用工具/简化路径/转人工。"""

class Rollback(Middleware):
    def on_failure(self, ctx, req, error) -> ExecResponse:
        """复用 EffectTracker.rollback(trace_id) 撤销本轮副作用。"""
```

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `OUTPUT_PARSE_FAILED` | 输出解析失败 |
| `CIRCUIT_OPEN` | 熔断器打开 |
| `RETRY_EXHAUSTED` | 重试耗尽（转 Fallback） |
| `ROLLBACK_FAILED` | 回滚失败（转 QUARANTINE） |

---

## 7. 关联

- 模块：`02-modules/constraints.md`
- 规格：`openspec/specs/constraints/spec.md`
