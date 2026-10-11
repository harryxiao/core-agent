# Proposal 0209 — 容错件接线（Retry 进生产；Fallback/Pipeline 首测）

## 为什么

`RetryPolicy` / `Fallback` / `Rollback`（`constraints/fault_tolerance.py:79/:105/:123`）与
`Pipeline`（`constraints/middleware.py:32`）**生产零调用**，其中 `Fallback` / `Pipeline` **连测试都
没有**；规格（`constraints/spec.md`「容错中间件」）已点名熔断 / 降级 / 重试 / 回滚四件。这是六能力
走查中「有规格无接线」死代码的一支：重试能力在，接线缺 —— 一次工具超时（`TIMEOUT`）/ 执行异常
（`EXECUTION_FAILED`）就整轮失败，本可对**可逆**工具自动退避重试一次即自愈。

## 做什么（含计划期修正 §0）

- **Retry 进生产**：新 `src/core/loop/fault_adapter.py`（镜像 `constraints_adapter.py`；`loop →
  constraints` 合法，`constraints → loop` 是架构红线）—— `FaultChain(provider, policy,
  sleep=asyncio.sleep).wrap(act)`：终止动作直通；失败且错误码 ∈ **显式白名单**
  `{TIMEOUT, EXECUTION_FAILED}`（未来错误码 **fail-closed 不重试**）**且** `tool_id` 可逆（惰性
  从 `provider.active_tools()` 建 frozenset，只在失败路径算）才重试；判停复用
  `RetryPolicy.should_retry`；退避 `await sleep(policy.backoff(attempt))`；**耗尽原样返回最后失败
  结果**（不降级）。
- **`DefaultLoop` 新可选参 `act_wrapper`**：`None` ⇒ 逐字不变；非空 ⇒ 包裹 `self.act`。
- **组合根注入**：`constraints.retry_attempts > 0` 时构造 `FaultChain` 注入主 / 子 / 神兽三 loop；
  **宠物不接**（沿 `runtime.py:1146` 隔离注记 —— 宠物流量不污染主线熔断态，同理不共享重试）。
- **配置**：单键 `constraints.retry_attempts`（int ≥0，**0 = 关 = 缺省**）；校验镜像
  `_circuit_breaker_errors`（`bool` 拒收）；访问器返回**原始整数**（底座模块不 import 能力层
  `RetryPolicy`，与 `retention_limits()` 同口径）。
- **Fallback / Pipeline 首次单测**（`tests/test_constraints.py` 增补）：走出零测试状态，
  `on_failure` 产响应、Pipeline 洋葱序 / 逆序 `on_failure` 短路。
- **Rollback 不接**：loop 级 `rollback(trace_id)`（`default.py:458-459`）已满足规格 Scenario
  「失败回滚」；ADR 记「单一路径」边界。

## §0 计划期修正（明示）

④b 字面是「Retry/Fallback/Rollback/Pipeline 进工具链」，但对抗验证发现 **Fallback 降级回复若进
生产会（a）静默抑制 `default.py:458-459` 的 trace 回滚**（该回滚以 `result.failed` 为触发）、
**（b）终结 loop 杀死 ReAct 自愈**（注释 `:439` 明写工具失败不判轮失败）；且 `Pipeline`/`Fallback`
是**异常形状**，`act()` 是**结果形状**，硬接需人为翻译。故本 change 终形 = **Retry 进生产**（白名单
＋仅可逆＋耗尽原样返回）＋ **Fallback/Pipeline 首次单测**（走出零测试）＋ **Rollback 维持 loop 级
既有路径**。降级回复上线若需要，另立 change。

## 规格影响

`constraints` **MODIFIED**「容错中间件」—— narrative 补「重试生产接线语义（白名单 / 仅可逆 / 缺省关 /
耗尽原样返回）+ 库能力边界（Fallback/Pipeline 库能力 + 单测覆盖、生产未接的理由）+ 回滚单一路径」
句 + **ADD** Scenario ×5（可逆超时重试成功 / 不可逆不重试 / 策略拒绝不重试 / 耗尽不降级不改结果 /
`retry_attempts=0` 缺省逐字不变）；既有 7 Scenario **逐字保留**。canonical req **不变**（MODIFIED 不增）、
scen **+5**。

## 风险

- **重复副作用**：已核 —— 效应只在成功后记（`provider.py:136-149`，`_call` 成功才 `tracker.record`）
  ⇒ 重试**不会双记账**。可逆门（仅对 `reversible=True` 工具重试）进一步封住不可逆外写被重试放大
  的风险。
- **`TIMEOUT` 部分外写**：既有风险被重试放大（第一次超时可能已部分落盘）；**只对可逆工具重试**即缓解
  （不可逆工具不重试）。ADR 记局限。
- **遥测 `duration_ms` 含退避时长**：`default.py:442` 计时跨整个 `_act`，退避计入其中；语义为
  「端到端耗时」，ADR 记。
- **缺省关**：`retry_attempts` 缺省 `0` ⇒ 不构造 FaultChain ⇒ `act_wrapper=None` ⇒ 既有路径**逐字
  不变**（守全仓不变量）。
