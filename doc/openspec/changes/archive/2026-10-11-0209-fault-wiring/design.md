# Design 0209 — 容错件接线

## 决策

1. **适配层落 `loop` 侧**（`loop → constraints` 合法；`constraints → loop` 是架构红线
   `test_architecture.py:272-283`），镜像 `constraints_adapter.py`。`FaultChain.wrap(act)` 返回一个
   与 `ActFn` 同签名的协程函数（`(action, trace_id, *, approved) -> ActionResult`）。
2. **注入方式 = `act_wrapper` 构造参**（非中间件 / 观察者）：重试是**在同一个动作上重复尝试**，语义上
   包裹 `act` 本体而非绕行 `action_started` / `action_completed` 事件流 —— 事件流仍按**单次
   `_act` 调用**记一条（重试不额外发 `action_completed`），遥测 `duration_ms` 含退避（ADR 局限）。
   `DefaultLoop.__init__` 里 `self._act = act_wrapper(self.act) if act_wrapper else self.act`；
   `None ⇒ self._act is self.act` ⇒ 既有路径**逐字不变**。
3. **显式白名单 `_RETRIABLE = {"TIMEOUT", "EXECUTION_FAILED"}`**：只有这两个执行类错误码重试；
   未来新增错误码**默认不重试**（fail-closed）。策略性拒绝（`INVALID_ARGS` / `COEFFECT_MISSING` /
   `GATE_DENIED` / `IRREVERSIBLE_BLOCKED` / `NO_TOOL_PROVIDER`）天然不在白名单 ⇒ 不重试。
4. **仅可逆工具重试**：`tool_id` 反向查 `provider.active_tools()`（`provider.py:77-79`）得
   `reversible`；**惰性**建 frozenset（只在失败路径算一次并缓存）—— 避免每次 `act` 都扫全工具表。
   不可逆工具不重试：避免「部分外写」被重试放大。
5. **耗尽原样返回最后失败结果**：**不降级、不改写 error** —— 保住 `default.py:458-459` 的 trace
   回滚（以 `result.failed` 为触发）与 `:439` 的「工具失败不判轮失败」（ReAct 自愈）。`RETRY_EXHAUSTED`
   码仍不使用（原样返回语义下无需改写错误码，ADR 登记）。
6. **判停复用 `RetryPolicy.should_retry`**：适配层传一个非 `ConstraintError` 的轻量异常承载失败码
   （`RetriableToolFailure`），`should_retry` 只据 `attempt < max_attempts` 判停 —— 次数上界是
   **单一真源**，适配层不复制该逻辑。
7. **配置访问器返回原始整数**：`configuration` 是**底座模块**（`BASE_MODULES`）⇒ 不得 import 能力层
   `constraints`。故 `retry_attempts() -> int`（缺省 `0`）；`RetryPolicy` 由**组合根**装配（同
   `retention_limits()` 先例）。
8. **宠物不接**：沿 `runtime.py:1146` —— 宠物流量不应污染主线/神兽的容错态，故三 loop（主 / 子 /
   神兽）接、宠物不接。

## 单一路径（Rollback 不接的理由）

规格「失败回滚」Scenario 已由 loop 级 `rollback(trace_id)`（`default.py:458-459`，以 `result.failed`
触发、撤销本轮 trace 下全部可逆副作用）满足。再经 `constraints.Rollback` 接一次是**第二条路径**
（同一语义两处实现 ⇒ 双撤销风险）。故 `Rollback` 留库能力、**不接**，ADR 记边界。
