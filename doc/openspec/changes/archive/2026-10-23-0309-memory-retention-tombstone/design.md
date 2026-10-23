# Design — 情景保留期与删除墓碑（0309）

## D1 墓碑原语：`retract`

```text
retract(entry_id, reason="tombstone") -> bool
  entry = _entry_by_id(entry_id)
  if entry is None: return False
  trace = f"retract.{entry.id}"
  if entry.layer != "L4": migrate(entry.id, entry.layer, "L4", trace_id=trace)
  prior = (content, status, list(tags))
  entry.content = ""
  entry.status = "retracted"
  entry.tags += ["retracted"]（去重）
  backend.put(entry); hot_put(entry)
  tracker.record(Effect(op="memory.retract", undo=restore(prior), trace_id=trace))
  audit.record("delete", entry, reason=reason)
  return True
```

**为什么清正文**：SDD §5.6 / §10.4 的墓碑只保留 `id/hash/时间/原因`。保留正文的
「归档」是 `forget()` 的语义（可逆、可召回），不是删除。`content_hash` 保留是刻意的：
它不含内容，是删除/导出/审计之间的关联键（与 `0308` 的同一取舍）。

**为什么迁 L4**：墓碑已退出全部活性面；放 L4 使「层级」继续表达「归档/非注入」，并避免
L2 文件被墓碑长期占用（L2 软上限只数 `active`，但物理上仍应下沉）。

**可逆性**：同一 trace 记录 `migrate` 与 `memory.retract` 两条效应，逆序回滚即先恢复正文/
状态、再迁回原层（`EffectTracker.rollback` 按记录逆序执行）。跨进程的持久可逆性由 CLI
删除前的 `memory-deleted.jsonl` 备份承担（保留期**不**备份：备份会重新持有已到期正文）。

## D2 保留期判据与触发

| 维度 | 取值 |
|---|---|
| 作用层 | `layer == "L2"` |
| 类型 | `kind == "episodic"` |
| 状态 | `status == "active"` |
| 时间 | `ts > 0` 且 `ts < now - N*86400`（`ts<=0` 不惩罚，沿用既有口径） |
| 动作 | `retract(id, reason="retention")` |
| 触发 | `forget()` 的**前置阶段** |

`forget()` 是既有唯一「维护性收口」入口：循环压实收尾与 `memory maintain` 都调用它，
`_enforce_l2_cap` 也复用它。把保留期放在这里意味着：

- 不新增维护步骤 → `compaction` 观测事件的 `steps` payload 逐字不变（`0253` 的账目锚不动）；
- 不需要新的 CLI 子命令；`memory maintain` 打印的归档数自然包含到期墓碑；
- 直接构造 `MemoryStore`（未注入 `episodic_retention_days`）⇒ 前置阶段为 no-op ⇒
  既有单测与嵌入方逐字回归。

`forget()` 返回值为「保留期墓碑 id + 衰减归档 id」；两者都以审计 `reason` 区分
（`retention` / `decay`），调用方无需拆解。

## D3 删除 CLI 改墓碑

`memory delete <id>` 流程不变的前半段（查找 → `_backup_memory_entry` 备份，失败
fail-closed），后半段由 `discard` 改为 `retract(..., reason="tombstone")`：

- 备份仍含原正文（持久可逆性来源）；
- `audit(None)` / `memory export` 仍能看到墓碑（`content=""`、`status="retracted"`、
  `content_hash` 原值）；
- `read()/recall()/failure_lessons()` 与压实材料均不可见；
- 输出「已墓碑化 …；备份文件：…」。

**为什么不改 `discard`**：`discard` 是内部清理原语（压实陈旧产物按序号清退，
`context/compactor.py:154`），那里需要真正移除；把 CLI 删除与内部清理分开，避免一处语义
改动波及两处调用面。

## D4 `retracted` 的可见性矩阵

| 面 | `retracted` 是否可见 | 实现 |
|---|---|---|
| `read()/recall()` | 否 | 既有 `status == "active"` 过滤 |
| `failure_lessons()` | 否 | 既有 `status == "active"` 过滤 |
| `audit()` / `index()` / export | 是（墓碑） | 既有不过滤 |
| `_episodic_groups()` 压实材料 | 否（**本 change 新增**） | 加 `status == "active"` |
| `_material_for_session()` 重抽材料 | 否（**本 change 新增**） | 加 `status == "active"` |
| `forget()` 衰减面 | 否（**本 change 新增**） | 跳过非 active |
| L2 软上限计数 | 否（**本 change 新增**） | 只数 active |

## D5 配置

`memory.episodic_retention_days`，缺省 `90`：

- `0` = 关闭（唯一关闭面；kill-switch 保留变更前行为）；
- 缺失 / `bool` / 小数 / 非数值 / 负数 ⇒ `90`（方向恒为「保留策略仍生效」，笔误不得
  静默变成永久保留）；
- 未加载配置 ⇒ `90`。
- 组合根总是注入该值；直接构造 store 的缺省是 `None`（完全关闭），保持嵌入面逐字兼容。

## D6 审计

沿用 `0308` 的事件字段与 fail-open 语义，不新增字段：

- 删除 CLI：`op="delete"`、`reason="tombstone"`；
- 保留期：`op="delete"`、`reason="retention"`；
- 内部物理清理（`discard` / repair）：`op="delete"`、`reason=""`（既有逐字不变）。

## 被拒备选

| 备选 | 拒绝理由 |
|---|---|
| 保留期到期仅迁 L4 + `forgotten`（不清理正文） | 不是保留期，只是退出注入面；正文仍无限期落盘 |
| 保留期物理删除（不走墓碑） | 无法回答「何时/为何消失」，违反 §5.6；与 `0301` 的可追溯方向相反 |
| 新增独立维护步骤 `retention` | 改 `compaction` 观测 payload 的既有 `steps` 账目（`0253` 锚），收益不抵回归面 |
| 每次写入都扫描保留期 | O(全量) 写入放大；维护节拍已覆盖 |
| 保留期默认 `0`（opt-in） | SDD §5.6 明确缺省 90 天；`0` 已提供 kill-switch |
| 同时做 `why/stats/重建索引` | 属 P2-5 / 不适用面，混入会扩大变更面 |
| 容量 256 MiB 拒绝写入 | 无 namespace，且拒绝写会破坏既有记忆主流程；登记为残余 |

## 测试映射

| 用例组 | 断言 |
|---|---|
| 保留期判据 | 到期墓碑化；新条目/非 episodic/`ts<=0`/非 active 不动 |
| `forget` 合并返回 | 到期墓碑 + 衰减归档同时返回，审计 reason 区分 |
| 配置 | 缺省 90、三面、`0` 关闭、非法归一 90、运行时接线 |
| 墓碑可见性 | read/recall/failure_lessons/压实材料不可见；audit/export 可见 |
| 删除 CLI | 备份保留正文；条目不物理消失；输出「已墓碑化」；备份失败 fail-closed |
| 可逆 | `rollback("retract.<id>")` 恢复正文/状态/原层 |
| 持久 | 重新加载后墓碑仍为 `retracted`、正文为空 |
