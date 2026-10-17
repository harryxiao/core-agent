# Design 0253 — 压实/抽取成本可观测

## D1 事件与 payload

| 事件 kind | 产出点 | payload |
|---|---|---|
| `maintenance` | `_maintain` 末尾（每实际节拍一次） | `elapsed_ms: float`、`steps: dict[str, float]` |
| `compaction` | `_compact` 末尾（每压实一次） | `trigger: str`、`elapsed_ms: float`、`steps: dict[str, float]` |
| `maintenance_failed`（既有） | 各步骤 except 分支 | `step: str`、`error: str`（**新增 `step`**） |

- `steps` 只含**实际执行**的步骤：`memory` 未注入 ⇒ 无记忆三步；`cold_path` 未注入 ⇒ 无
  `cold_path`。轮内压实 `memory` 未注入时只有 `persist`。
- `trigger` 由调用点决定：轮内阈值路径缺省 `threshold`；`_budget_retry` 显式传
  `budget_retry`。这是**成本归因到触发路径**的唯一手段，不改变触发条件本身。

## D2 计时口径

`time.perf_counter()` 包住每一步（含失败步骤：`finally` 记账），`elapsed_ms` 为各步之和。
不用 `time.time()`：系统时钟回拨会产生负耗时；`perf_counter` 单调且分辨率足够。
耗时四舍五入到 3 位小数，payload 有界。

## D3 失败语义不变

步骤失败仍**降级不中断**：异常被捕获、记 `maintenance_failed`、其余步骤继续、`maintenance` /
`compaction` 事件照常产出。`_compact` 的 `persist` 步骤保留原有 `ContextError` 静默分支
（无可沉淀关键信息不是错误），不额外留痕、不计失败。

## D4 零依赖、零配置、零默认行为变化

- 不新增配置键（观测成本不需要运维开关；tracer 本身就是开关）。
- 不接入 `MetricsCollector`：给 `DefaultLoop` 增注入面会扩大装配复杂度，而 trace 事件已经
  可被导出面消费与聚合，P2-lite 到此为止。
- 未注入 tracer ⇒ `_trace` 立即返回，额外开销只有 `perf_counter` 调用（每步一次），
  对本就含模型调用的步骤可忽略。

## 反证设计

| 探针 | 摘除 | 预期红测试 |
|---|---|---|
| P1 | `_maintain` 的 `maintenance` 事件 | 成本事件 / 闸门 / 失败归因 3 例红 |
| P2 | `_compact` 的 `compaction` 事件 | 压实成本 / persist 失败 / budget 触发 3 例红 |
| P3 | `trigger` 传递（硬编码 `threshold`） | 直接调用 + budget 触发 2 例红 |
| P4 | `maintenance_failed` 的 `step` 字段 | 失败步骤归因 1 例红 |

## 已知局限（登记 ADR-0243）

1. **只有时间，没有数量**：不记被压实条目数 / 摘要 token 数（`MemoryStore.compact` 不返回
   计数）；抽取成本只能按 `memory_compact` 总时长近似。
2. **事件在末尾发出**：若进程在节拍中途崩溃，该次 `maintenance` 事件不存在（已执行的失败
   留痕仍在）。
3. **无聚合 / 分位数**：每节拍 / 每压实一条原始事件，聚合依赖导出面；高频维护时事件量随
   节拍线性增长。
4. **steps 键是契约**：消费方按字典读取；新增步骤对旧消费方向后兼容，但改名属破坏性变更。
5. **线程内计时**：`_compact` 在 `asyncio.to_thread` 工作线程执行，`elapsed_ms` 含该步自身
   执行时间，不含线程排队等待。
