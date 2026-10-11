# Proposal 0208 — 保留策略接线（缺省关）

## 为什么

`RetentionManager.apply(policy)`（`durability/retention.py:25-49`）三通道（数量上限 / 时间窗口 /
存储配额）＋ `pin/unpin`（`:51-55`）API 齐备、规格已写（`durability/spec.md`「生命周期与保留策略」，
含 pinned 保护），但**生产零调用** ⇒ `checkpoints.jsonl` **无限增长** —— 每次波次 / 任务完成都
`create_checkpoint` 追加快照（`durability/manager.py:32-54`，`put` 追加非覆盖）而无人清理。这是
六能力走查中「长任务 / 重启恢复」的一项：能力在，接线缺；且 `0214`（主 loop 轮级检查点）会把写入
频率显著抬高 ⇒ 本 change **先行**铺好清理面。

## 做什么

- **只接两通道**：`max_count` / `time_window_s` —— **存储配额不接**（`apply` 超配额时抛
  `RETENTION_QUOTA_EXCEEDED`，接进生产会让「检查点落盘」这条热路径可能**炸启动**；留库能力，
  ADR 记）。`RetentionPolicy.strategy` 字段无消费者，亦不接（登记）。
- **接线点** = `_write_checkpoint`（`runtime.py:1039-1065`）落盘后按已配置通道 `apply` —— 清理
  永远在**新检查点已落盘之后**，不会误删刚写的那个（最新 ts 最大）。
- **配置**：`durability.retention.max_count`（int ≥1）＋ `durability.retention.time_window_s`
  （float ≥0）；`map_to` 前缀自动进段白名单（`manager.py:434-437`）；**两键皆缺省 ⇒ 零清理、逐字
  不变**；校验镜像 `_circuit_breaker_errors`（`:887-905`）—— 非法取值**阻断启动**。

## 规格影响

`durability` **MODIFIED**「生命周期与保留策略」—— narrative 补「接线面两配置键 + 缺省关 + 接线点 +
存储配额未接」句 + **ADD** Scenario ×3（数量上限清理最旧 / 时间窗口清理过期 / 缺省未配置零清理）；
既有「保留策略自动清理」「关键检查点保护」两 Scenario **逐字保留**。canonical req **4 → 4**
（MODIFIED 不增）、scen **14 → 17（+3）**。

## 风险

- **误删活跃检查点**：`max_count` 过小会清理未完成任务的旧检查点 ⇒ 续跑回退到更早点（非丢失整体，
  且用户显式配置）。缺省关 ⇒ 不配置即零风险。
- **热路径开销**：每次落盘后 `apply` 需 `list_checkpoints` + 排序（O(n log n)）；检查点写入本就在
  波次/轮次边界（非主循环热路径），可接受。
- **`storage_quota` 不接**：避免 `RETENTION_QUOTA_EXCEEDED` 在落盘路径炸启动 —— 有意保留库能力。
