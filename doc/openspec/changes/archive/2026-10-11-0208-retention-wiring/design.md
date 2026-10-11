# Design 0208 — 保留策略接线

## 决策

1. **配置访问器返回原始值对，不返回 `RetentionPolicy`**：`configuration` 是**底座模块**
   （`test_architecture.py:58` `BASE_MODULES`）⇒ **不得** import 能力层 `durability`。故访问器
   `retention_limits() -> tuple[int | None, float | None]`（`(max_count, time_window_s)`；`None`
   表未配置）；`RetentionPolicy` 由**组合根**（`runtime.py`）装配。与 `max_concurrency()` /
   `loop_limits()` 返回原始类型的先例一致。
2. **接线点 = `_write_checkpoint` 落盘之后**：保证清理看到「新检查点已在库中」，且最新 ts 最大 ⇒
   数量上限**永不误删刚写者**。`apply` 在**每次**检查点写入后调用（波次级 + 任务完成级）。
3. **只接 `max_count` / `time_window_s`**：`storage_quota` 通道 `apply` 超配额时抛
   `RETENTION_QUOTA_EXCEEDED` ⇒ 接进落盘热路径会让「写检查点」可能炸；本 change 不引入该风险，
   留库能力（ADR 局限）。`strategy` 字段无消费者（不接）。
4. **缺省关**：两键皆缺省 ⇒ `retention_limits()` 返回 `(None, None)` ⇒ 组合根不构造 policy ⇒
   `_write_checkpoint` 内 `if policy is not None` 短路 ⇒ **零清理、逐字不变**（守全仓不变量）。
5. **校验阻断启动**：`_retention_errors(raw)` 镜像 `_circuit_breaker_errors` —— `max_count` 须为
   **≥1 的整数**（`bool` 拒收）、`time_window_s` 须为 **≥0 的数值**（`bool` 拒收）；缺省（键不存在）
   合法。非法值进 `validate_schema` 的 errors ⇒ `ConfigurationError`。
