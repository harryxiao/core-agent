# Design 0260 — 长任务默认值

## D1 `loop.max_rounds` 缺省 20

- 依据：编码闭环的最小步数（读 → 改 → 测 → 看 → 修）与一次回环即可用尽 10 步；20 步给一次
  完整修复循环留余量。
- 改动点：`configuration/manager.py::_DEFAULT_MAX_ROUNDS` 与 `loop/default.py::
  DefaultLoop.__init__(max_rounds=...)` **同值**。后者是直接构造（beast / pet / UI 的
  `DefaultLoop()`）的缺省；不同步会让「有配置源」与「无配置源」两条路径缺省分叉。
- 不变量：token 预算派生与 token 阀逐字不变；`loop.compact_steps` 缺省 6 仍 **< 20** ⇒ 压实
  步数维度仍可真正提前触发；校验仍要求 ≥1 的整数。

## D2 `orchestration.subtask_timeout` 配置缺省 600 秒

- 依据：交接 deadline 缺失时，卡死的子任务永久占用调度槽；600s 覆盖大多数编译 / 测试子任务，
  又不至于让单点故障长期悬挂。
- 改动点：`_DEFAULT_ORCHESTRATION_SUBTASK_TIMEOUT = 600`。校验范围不变（≥0 的整数，
  `bool` 非法）；显式 `0` 仍合法，语义仍为「不设限」（`TaskScheduler` 侧把 `> 0` 转为
  `deadline`，`0` 保留 `None`）。

## D3 构造缺省与配置缺省的两处口径（有意保留）

`TaskScheduler(subtask_timeout: float = 0)` **保持 0**：

- 构造函数是能力层 API，缺省 0 = 不设限，是「不注入就不改变既有行为」的保守语义；直接构造
  调度器的既有测试与调用方（含 `TaskScheduler()`）行为逐字不变。
- 生产路径由组合根 `build_runtime` 显式注入 `config.orchestration_subtask_timeout()`；缺省
  配置下注入 600。缺省值变更只作用于**配置面**，不靠构造缺省扩散。
- 因此「未配置」与「显式 0」在生产面均得到 600（未配置）与 0（显式关闭）两种可区分结果；
  `TaskScheduler()` 直连仍是不设限。该差异写入接口文档与 ADR。

## D4 规格与校验

- `loop`「错误与预算控制」：默认轮数 `10` → `20`，其余条款逐字保留。
- `configuration`「循环预算配置」：缺省句与 Scenario 改 `20`。
- `configuration`「编排调度配置」：缺省句改 `600`（`0` = 显式关闭），Scenario 改 `600`；
  另加 Scenario 固定「显式 0 仍不设限」。
- 校验上下界、ConfigSpec 三面、优先级链均不变。

## 反证

1. 摘除 `_DEFAULT_MAX_ROUNDS = 20`（还原 10）⇒ 配置缺省用例红；复原后 md5 一致。
2. 摘除 `_DEFAULT_ORCHESTRATION_SUBTASK_TIMEOUT = 600`（还原 0）⇒ 编排缺省用例红；复原后
   md5 一致。
3. 摘除 `DefaultLoop.max_rounds` 构造缺省 20（还原 10）⇒ 构造缺省同值用例红；复原后 md5 一致。

## 已知局限

- 20 / 600 是启发式缺省，未做真实任务成功率调优；用户可按任务类型覆盖。
- 轮数提高会放大单任务的最坏 token 消耗；token 预算仍独立生效，但「最坏耗时」没有同等硬上限。
- `TaskScheduler` 构造缺省与配置缺省不同值，直连调度器的调用方不会获得 600s 保护（仅生产
  组合根注入）。
