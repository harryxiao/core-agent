# Proposal — 记忆治理审计与导出（P2-2）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §10.4「治理审计 / 导出 / 墓碑」与走查 **P2-2**：

1. **无可审计的治理轨迹**：写入、删除、遗忘都会改变持久知识集，但本仓只留**进程内**
   `EffectTracker` 效应（随进程结束失效）与分散的旁路文件（`memory-deleted.jsonl` 仅覆盖
   CLI 删除）。跨进程回看「谁在何时写了 / 删了 / 遗忘了哪条」没有单一入口。
2. **遗忘无原因 / 墓碑信息**：`forget()` 只打 `forgotten` 标签并迁 L4，审计面只能看到
   「已归档」，看不到**为什么**（自然衰减）与**依据**（内容哈希 / 时间）。
3. **无导出面**：SDD 要求治理导出（JSONL / JSON，缺省脱敏、显式确认、记录审计）。本仓
   `memory list/get` 只能逐条查看，无法一次性导出留档。

本 change 只补**治理观测面**，不改记忆语义：审计是**旁路追加日志**（写失败不阻断记忆操作），
导出是**只读快照**（不改条目、不触发复用强化）。

## What Changes

- 新增 `src/core/memory/audit.py`：`MemoryAuditLog`（append-only JSONL，0600，单次 `os.write`
  整行；事件为固定字段的 dict）。事件只含**元数据**（op / id / layer / kind / source /
  session_id / trace_id / content_hash / reason / count / target / format / ts），
  **绝不写正文**；全部字符串字段先 `redact_secrets` 再按上界截断。
  写失败 **fail-open**：吞异常、每实例只告警一次，不影响记忆操作。
- `MemoryStore(audit_log: MemoryAuditLog | None = None)`：缺省 `None` ⇒ 零文件、零行为变化
  （既有直接构造方与全部单测逐字不变）。接线后：
  - `_persist`（成功落库）⇒ `write` 事件（覆盖写入、压实摘要、事实/关系/情景派生）；
  - `_delete_entry` ⇒ `delete` 事件；
  - `forget()` ⇒ `forget` 事件，`reason="decay"`；
  - 幂等重放 / 闸门拒收 / 复用强化（`reuse_count` 自增）**不**产生事件（无持久知识集变化）。
- 配置键 `memory.audit_log`（布尔，**缺省 `true`**，kill-switch 语义）：三面
  `--memory-audit-log` / `CORE_MEMORY_AUDIT_LOG` / `memory.audit_log`。取值归一与
  `memory.key_fact_extract` 同口径：集合外取值归一为**开启**（不得因笔误静默关审计）。
  组合根开启时注入 `MemoryAuditLog($CORE_STATE_DIR/memory.audit.jsonl)`，关闭时注入 `None`。
- CLI：
  - `memory audit [--limit N]`：只读查看审计日志（缺省 50，`0` = 全部；空/缺失 ⇒
    「（无审计记录）」）；坏行容错跳过。
  - `memory export [--format jsonl|json] [--out PATH] --yes`：导出全部条目快照
    （含 L0–L4 / 各治理状态），正文与字符串字段先脱敏；**缺 `--yes` 拒绝导出**（退出 1）；
    `--out` 文件以 0600 落盘；导出成功后写一条 `export` 审计事件（count / target / format）。

## Non-goals

- **不改条目信封**：不加 `namespace` / `tenant` / `trust` / `confidence` / `retracted`
  （P2-2 只做观测面；envelope 变更属独立设计）。
- **不做防篡改 / 签名链**：审计文件是 0600 追加日志；同用户进程仍可改写，tamper-evidence
  与外部 WORM 存储不在本 change。
- **不做自动轮转 / 保留期**：行长大致有界（≤ ~1KB），文件随治理动作线性增长；轮转交给
  外部 logrotate（ADR 局限登记）。不引入 `memory.audit_max_bytes` 等新配置。
- **不审计读路径**：检索、`reuse_count` 强化、迁移（`migrate`）不产生审计行（迁移已有
  `memory.migrate` 效应与 L4 可见性；逐读审计会造成写放大）。
- 不新增第三方依赖；不改 `memory.jsonl` 格式。

## Impact

- 代码：`src/core/memory/audit.py`（新）、`src/core/memory/__init__.py`（导出）、
  `src/core/memory/store.py`（构造参 + 三处钩子 + `record_export`）、
  `src/core/configuration/manager.py`（ConfigSpec + 访问器）、`src/core/runtime.py`（接线）、
  `src/core/entry.py`（两个子命令 + 分派 + 用法串）。
- 行为：直接构造 `MemoryStore` 的既有调用方零变化；组合根缺省多写一个旁路文件
  （`memory.audit.jsonl`，0600），可用 `memory.audit_log=false` 关闭。
- 规格：`memory` **ADDED** ×2（审计日志 / 导出）、`configuration` **ADDED** ×1。
- 测试：新增 `tests/test_memory_audit.py`（审计写入/删除/遗忘/失败隔离/配置三面/接线）、
  `tests/test_memory_export_cli.py`（导出确认、脱敏、格式、审计事件、`memory audit` 读取）。
