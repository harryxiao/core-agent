# constraints-middleware-wiring — 约束中间件链真正接入 loop（E1）

## Why

账本 E1（`coding-plan/phase-19.md`）：**constraints 中间件链从未注入 loop** ——
`src/core/loop/default.py` 的 `_apply_middlewares` 是生产死代码，`runtime.py` 从不传 `middlewares=`。

一手核实后的两处订正（本次会话）：

1. **空转的不是校验**。校验生产已由工具层承担：`tools/provider.py _validate_args` 与
   `constraints/validator.py validate_input` 语义逐行等价（`_matches_type` 两份拷贝）；
   `ToolProvider.ainvoke` 已含 未知工具→参数校验→coeffect 解析→`SafetyGate`→超时→执行→
   `EffectTracker`→结构化 `ToolResult`。
2. **上下文压缩已接线**：`runtime.py` 中 `compactor=context_compactor`（`core.context.Compactor`；
   与 `constraints.ContextCompressor` 是两码事 —— 后者**不是** `Middleware`，无 `before`/`after`）。

因此 E1 的真实残留 = **constraints 规格「容错中间件」需求的熔断在生产无任何等价物**，
外加 `middlewares` 接缝本身是死的。

## What Changes

- **loop 增一处加法式结果侧接缝**：新增 `action_observers`（`Callable[[LoopContext, Action, ActionResult], None]` 列表），
  在每个**非终止**动作完成后按注册序回调，仅通知；观察者异常降级为遥测、**不改变本轮结局**。
  `Middleware`（before-only）契约**保持不变**（既有 `tests/test_loop.py` 的 callable 中间件用法不动）。
- **新增 `core/loop/constraints_adapter.py`**：`ConstraintsChain`
  —— before 半边把 `CircuitBreaker.before` 的 `CIRCUIT_OPEN` 转成终止 Action（短路本轮，
  与既有 `decline` 同构）；结果半边喂 `CircuitBreaker.record_result`。熔断**按 `tool_id` 隔离**
  （`dict[str, CircuitBreaker]` 惰性建），**只对执行类失败计数**，策略性拒绝不计入。
- **组合根注入**：`runtime.py` 构造一份 `build_constraints_chain()`，注入主 loop 与所有子 agent loop
  （共享同一实例 → 熔断态 per-runtime）。
- **`CircuitBreaker` 增可选 `clock` 注入**（默认 `time.monotonic`，对齐 `DefaultLoop` 既有 `clock`），
  让「冷却后半开试探」测试确定性。
- spec delta：loop（MODIFIED 横切中间件插入[双接缝]）、constraints（MODIFIED 容错中间件[按工具隔离/计数规则]）。

## Non-Goals

- **不接线 `Validator`**：其校验逻辑已被 `ToolProvider._validate_args` 覆盖且**接线会更差**
  （工具层返回结构化 `INVALID_ARGS` 供模型自纠；loop 层拒绝会终止本轮）。
- **不接线 `RetryPolicy`**：工具副作用非幂等、`ToolDef` 无幂等标记，二次 `EffectTracker.record` 污染 undo 栈；
  规格的重试场景已由 ReAct 观察回灌满足。
- **不接线 `Fallback`**：无生产 `fallback_fn`。
- **不把 `ContextCompressor` 并入链**：它非 `Middleware`，且压缩已在 `core.context` 接好。
- **不做真洋葱（after 逆序）**：无消费者；顺序 = 注册序，将来需要另开变更。
- **不做**熔断阈值/冷却配置化（`configuration/` 无 constraints 段，属 E10 配置门控）。

## Impact

- `src/core/loop/{default.py, __init__.py, constraints_adapter.py(新)}`
- `src/core/constraints/fault_tolerance.py`（`CircuitBreaker` 加法式 `clock`）
- `src/core/runtime.py`（两行注入）
- spec：`doc/openspec/specs/{loop,constraints}/spec.md`
- 文档：`doc/03-interfaces/{loop,constraints}-interface.md`、`doc/02-modules/{constraints,loop}.md`、ADR-0055
- 账本：E1 关闭（含「校验非空转」订正）+ 三条后续行（Validator.parse_output 无调用方 / 校验码重复 / 熔断不可配）
