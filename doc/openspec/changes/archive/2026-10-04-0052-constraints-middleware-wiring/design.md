# Design — constraints-middleware-wiring（change 0052 / 账本 E1）

## 1. 岔口选型：Fork B（最小加法式）

三条独立证据锁定「适配层接进 loop 接缝」而非包装工具边界：
账本 E1 自述的关闭动作是「写 constraints→loop 适配层」；`doc/02-modules/constraints.md:12`
明示本模块插在 **loop 的推理→行动、行动→记忆两个接缝**；loop 规格「横切中间件插入」已存在。

**关键事实（一手核实）**：before 半边**无需改 loop**。`act()` 对终止动作直接
`return ActionResult(failed=False, data=action.args)`；`observe()` 见 `data["reply"]` 即 `ctx.finish()`；
`decline()` 正是此形状。故「熔断打开 → 短路」今天即可由「before 中间件返回终止 Action」表达。

**真正缺失的只有结果侧信号**：没有任何东西能喂 `CircuitBreaker.record_result`，
而 `before` 只在 `state == OPEN` 时抛错、`state` 只由 `record_result` 置 OPEN
→ 熔断证明不可开。故最小增量 = 保留 `Middleware`（before-only）不变 + 新增 `action_observers`（结果侧）。

**已否决**：
- Fork A（把链压进 before-only）：熔断不可开，账本的 `CIRCUIT_OPEN` 短路用例写不出来；
  校验与工具层重复、压缩已接线 → 零行为变化 + 新死代码。
- Fork C（包装 `ToolProvider`）：工具边界**已经就是** constraints 链，重复实现；且 `_apply_middlewares` 仍死。
- 真洋葱（after 逆序）：无消费者，YAGNI；顺序 = 注册序。

## 2. 落点（红线）

`tests/test_architecture.py:268 test_phase2_middleware_no_reverse_dependency` 禁 `constraints → loop`，
故适配层**只能落 loop 侧**：`src/core/loop/constraints_adapter.py`（`loop → constraints` 合法；
`test_phase3_loop_no_reverse_dependency` 只禁 loop→{skills,skillhub}）。
`runtime.py` 保持唯一组合根（`test_runtime_is_sole_composition_root`）。

## 3. 熔断粒度陷阱

`CircuitBreaker` 只有单计数器/单状态、无 key。直接接进 loop 会让一个坏工具**全局开闸**。
故适配层持 `self._breakers: dict[str, CircuitBreaker]` **按 `tool_id` 惰性建**，不改 `CircuitBreaker` 既有契约。
这也与规格措辞「某插件连续 N 次失败」一致。

## 4. 失败分类（哪些计入熔断）

只计**执行类**失败：`TIMEOUT` / `EXECUTION_FAILED`（及未知码，fail-safe）→ `record_result(success=False)`。
**策略性拒绝完全不调 `record_result`**：`INVALID_ARGS` / `COEFFECT_MISSING` / `GATE_DENIED` /
`IRREVERSIBLE_BLOCKED` / `NO_TOOL_PROVIDER` —— 否则模型可用坏参数把工具"锁死"（gate 拒绝/ schema 拒绝
不反映工具健康度）。

## 5. 失败策略非对称

before 侧中间件保持 **fail-loud**（异常向上传播，行为不变；适配层自捕获 `ConstraintError`）；
结果侧观察者 **fail-soft**（单观察者异常降级为 `_trace("action_observer_failed")`，不改本轮结局），
对齐既有 `turn_observer` / `cold_path` 降级先例。

## 6. 短路语义

熔断打开 → 返回终止 Action「已拒绝：工具 X 熔断中（CIRCUIT_OPEN），本轮终止。」——
与 `decline` 同构，满足「中间件拒绝短路」。**接受项**：按工具熔断开闸后本轮终止、无法同轮改投工具 B
（属"快速失败"）。若将来需要"注入合成观察结果继续本轮"，另开接缝（本次非目标）。

## 7. 有意不接

- `Validator`：被 `ToolProvider._validate_args` 吸收（且接线会更差：opaque 拒绝 vs 结构化错误供自纠）。
- `RetryPolicy`：幂等风险 + `ToolDef` 无幂等标记 + 二次 `EffectTracker.record` 污染 undo 栈；
  规格重试场景已由 ReAct 观察回灌满足。
- `Fallback`：无生产 `fallback_fn`。
- `ContextCompressor`：非 `Middleware`，压缩已在 `core.context` 接好。

## 8. 测试策略

单元覆盖已存（`tests/test_constraints.py`），本变更必须证明**生产接线**：
loop 契约单测（观察者序/降级/终止不触发/向后兼容）+ runtime 装配断言（主/子 loop 同一 chain 对象）
+ 适配层单测（按工具隔离 / 策略拒绝不计入 / 半开闭合）+ 端到端熔断（第 N+1 次调用计数停在 N）。
