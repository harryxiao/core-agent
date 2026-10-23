# Proposal — 情景保留期与删除墓碑（P2-3 + P2-2 残留）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §5.6 / §10.4 与走查 **P2-3**，并收口 **P2-2** 的残留：

1. **无情景保留期**：SDD 要求 episodic 缺省保留 90 天（可配），本仓只有「衰减评分」与
   「L2 软上限」两条收口路径——一条近期高频复用、但内容已过保留期的情景会**无限期**留在
   可注入面；`ts<=0` 的旧行也无从清理。
2. **删除不是墓碑**：`memory delete <id>` 备份后**物理删除**（`discard`），条目从
   `audit()` / 导出快照中一并消失；SDD §5.6 / §10.4 要求墓碑（id / hash / 时间 / 原因，
   不含正文）且「删除后重建索引不得复活」。`0308` 只补了删除审计，未改删除语义。

本 change 只做**收口语义**：保留期到期与显式删除都走**墓碑化**（清空正文、`status="retracted"`、
迁 L4），审计/导出仍可见墓碑，注入面与压实材料均不可见。不引入命名空间、不改 `forget()`
的自然衰减判据、不做索引重建工具。

## What Changes

- **墓碑原语**：`MemoryStore.retract(entry_id, *, reason="tombstone") -> bool`：
  - 条目存在 ⇒ 迁 L4（可逆效应的 trace `retract.<id>`）、清空 `content`、置
    `status="retracted"`、追加 `retracted` 标签、保留 `id / content_hash / ts / source /
    session_id / trace_id / version`；记一条 `memory.retract` 可逆效应；审计
    `op="delete"`、`reason` 取调用方（`tombstone` / `retention`）。
  - 条目不存在 ⇒ 返回 `False`，零落盘 / 零效应 / 零审计。
- **情景保留期**：`MemoryStore(episodic_retention_days: int | None = None)`；非正 / `None`
  ⇒ 不启用（直接构造与既有单测逐字不变）。启用时 `forget()` **先**墓碑化到期条目、再走
  既有衰减归档：
  - 判据：`layer=="L2"`、`kind=="episodic"`、`status=="active"`、`ts>0` 且
    `ts < now - N×86400`；
  - 动作：复用 `retract(..., reason="retention")`（清正文 + `retracted` + L4）；
  - 返回：到期墓碑 id 并入 `forget()` 的返回列表（调用方无需新入口）；
  - **触发沿用既有维护节拍**：循环压实收尾的 `forget()` 与 `memory maintain` 的
    `forget()` 都会执行；不新增观测步骤、不改 `compaction` 事件 payload。
- **配置**：`memory.episodic_retention_days`（整数，缺省 `90`，`0` = 关闭），三面
  `--memory-episodic-retention-days` / `CORE_MEMORY_EPISODIC_RETENTION_DAYS` /
  `memory.episodic_retention_days`。非法 / 负数 / 布尔 ⇒ 归一为 `90`（笔误不得静默关闭
  保留期）；`0` 是唯一关闭面。组合根注入 `config.episodic_retention_days()`。
- **CLI 删除改墓碑**：`memory delete <id>` 仍**先备份**（`memory-deleted.jsonl`，fail-closed），
  备份成功后调用 `retract(..., reason="tombstone")`；输出改为「已墓碑化」。
- **注入面收口**：`status != "active"` 的条目除既有 `read()/recall()/failure_lessons()`
  外，也从 `_episodic_groups()`（压实材料唯一源）、`_material_for_session()`、
  `forget()` 衰减面与 L2 软上限计数中剔除——墓碑不得被摘要器回喂、不得占 L2 名额。

## Non-goals

- **不做命名空间容量上限 / 告警**（SDD §5.6 的 256 MiB per namespace）：`namespace` 在
  `0303` 已明确「无消费方不引入」，容量面随命名空间立项；本 change 只登记为 P2-3 残余。
- **不做 `memory why` / `stats` / 重建索引**：单一 `memory.jsonl` 是唯一权威、无派生索引，
  「重建索引」当前不适用；`why/stats` 属可观测性增强（P2-5），另行立项。
- **不改 `forget()` 的衰减判据与归档去向**（仍 `forgotten` 标签 + L4、保留正文）；
  保留期墓碑是**附加判据**，到期条目走 `retracted` + 清正文。
- 不新增第三方依赖、不改 `memory.jsonl` 行格式（`status` 增一个枚举值，旧行默认兼容）。

## Impact

- 代码：`src/core/memory/protocol.py`（`MemoryStatus` + `retracted`）、
  `src/core/memory/store.py`（构造参、`retract`、`forget` 前置保留期、活性过滤四处）、
  `src/core/configuration/manager.py`（ConfigSpec + 访问器）、`src/core/runtime.py`（接线）、
  `src/core/entry.py`（delete 改墓碑 + 输出文案）。
- 行为：直接构造 `MemoryStore` 的既有调用方保留期关闭 ⇒ 零变化；组合根缺省 90 天 ⇒
  `forget()` 会墓碑化到期 episodic（可用 `memory.episodic_retention_days: 0` 关闭）。
- 规格：`memory` **ADDED** ×1 + **MODIFIED** ×1（治理信封 status 枚举）；`configuration`
  **ADDED** ×1。
- 测试：新增 `tests/test_memory_retention.py`、`tests/test_memory_tombstone.py`；
  改写 `tests/test_entry.py` 删除用例。
