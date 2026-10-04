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

**口径单一真源（change `0059`）**：`validate_input` 是「调用前 schema 校验（必填 / 类型）」
**唯一实现**；工具层 `ToolProvider` 的调用前校验**委托**之（`tools → constraints`，与
`loop → constraints` 同型），不得另实现副本。

**`parse_output` 无生产调用方 —— 有意，非遗漏（change `0063` 判定，账本 E13 关闭）**：
规格「输入输出校验」的「调用后把自由文本解析为结构化指令，解析失败绝不带病执行」在生产由
`LLMPlanner._parse`（`src/core/loop/planner.py`）实现——它是**动作感知**的：区分「工具调用」与
「回复」；解析失败即产出**终止 Action**（`reply = LLM_PLAN_PARSE_FAILED: …`），工具**不执行**，
失败原因随观察回灌给模型 ⇒ 即规格场景的「不执行，请求模型修正」（追踪：`TC-CONS-05`）。
`Validator.parse_output` 是**无动作语义**的通用 JSON 解析（只保证解析出对象，判不了
`tool_id` / `reply` 契约），接进 planner 反而**降级**解析能力。故保留为该中间件契约的输出侧
API（有单测覆盖），不接线——不是「实现未用」，而是「不该用」。

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

构造面：`failure_threshold=5` / `cooldown_s=30.0` / `clock`（缺省 `time.monotonic`，可注入便于测试）。

**生产接线**：由 `src/core/loop/constraints_adapter.py` 的 `ConstraintsChain` **按 `tool_id` 隔离**接进 loop
（每工具一个实例，`dict[str, CircuitBreaker]`——单计数器直连会让一个坏工具全局开闸）；`before` 命中 OPEN
即转「终止 Action」短路本轮，`record_result` 由结果侧观察者（`action_observers`）回灌。
**只计执行类失败**（`TIMEOUT` / `EXECUTION_FAILED` / 未知码）；策略性拒绝（`INVALID_ARGS` /
`COEFFECT_MISSING` / `GATE_DENIED` / `IRREVERSIBLE_BLOCKED` / `NO_TOOL_PROVIDER`）不计入、也不影响其他工具。
决策见 ADR-0055。

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
- 生产接线（loop 侧适配层，按工具熔断）：`src/core/loop/constraints_adapter.py`（`ConstraintsChain`）
- 生产接线（工具层校验口径委托）：`src/core/tools/provider.py`（`_validate_args` → `Validator.validate_input`）
- 测试：`tests/test_constraints_wiring.py`
- 规格：`openspec/specs/constraints/spec.md`
