# Design 0262 — 记忆检视与纠错 CLI

## D1 命令面与渲染

- `memory list [--limit N]`：`audit(None)` 取全量，**只截断展示**。一行一条，字段顺序固定：
  `id  layer  kind  source  session  importance  ts  summary`。`session` 空串显示 `-`；
  `ts<=0` 显示 `-`。`--limit` 缺省 50，`0` = 全部，负数由 argparse 拒绝（退出码 2）。
  末尾在发生截断时提示 `（共 N 条，显示前 M 条）`。
- `memory get <id>`：元数据逐行 + 空行 + 全文。全文经 `redact_secrets` 脱敏（密钥只引用不
  读取、绝不回显）。未知 id ⇒ stderr + 退出码 1。
- `memory delete <id>`：先备份后删除；未知 id ⇒ stderr + 退出码 1，**不落备份**。
- 三者共用 `_memory_find(audit_entries, entry_id)`：按 id 精确匹配，取首条（口径同
  `MemoryStore._entry_by_id` 的「同 id 即覆盖」）。

## D2 删除的持久可逆性

`discard` 的可逆效应随 CLI 进程退出即失效，故删除前把条目序列化（`asdict(entry)`，JSON 一行）
**追加**到 `$CORE_STATE_DIR/memory-deleted.jsonl`：

- `os.open(..., O_APPEND | O_CREAT | O_WRONLY, 0o600)` 单次 `os.write` 整行（对齐转录落盘的
  并发追加口径）；随后尽力 `chmod 0600`（已有文件可能带更宽权限）。
- **fail-closed**：备份写入抛 `OSError` ⇒ stderr 报错、退出码 1、**一条不删**（与
  `repair_stale_key_facts` 的备份相口径一致）。
- 用**追加**而非一份时间戳文件：单条删除无「整次操作」边界，追加日志天然可累积、可人工重放。

## D3 只读复用公开 API

- 列表/查找走 `MemoryStore.audit(None)`（冷热并集，公开）；删除走 `MemoryStore.discard`
  （既有「热区 + 后端 + 删除效应」唯一路径）。不新增内存索引、不读私有字段。
- `audit()` 全量加载是有意取舍：CLI 运维面一次性使用，优先正确性与零耦合；大库的内存/耗时
  作为已知局限记录。

## D4 与运行实例的关系

命令经 `build_runtime` 装配同一 `$CORE_STATE_DIR` 的 store；`discard` 只作用于**当前进程读取
到的**条目与后端文件，运行中的实例不会收到失效通知（与 `maintain` / `repair-keyfacts` 同构，
一次性运维动作、不改变运行态）。删除后条目从磁盘消失，运行实例下一次落盘/检索以其自身内存
快照为准 —— 该限制写入接口文档。

## 反证

1. 去掉 `delete` 的备份调用 ⇒ 备份落盘用例红。
2. 备份后不调用 `discard` ⇒ 条目消失用例红。
3. `get` 输出跳过 `redact_secrets` ⇒ 密钥形态不回显用例红。
4. 未知 id 也写备份 ⇒ 「未知 id 不落备份」用例红。

## 已知局限

- 无 `restore` 子命令：恢复靠备份 JSONL 人工重放（沿用 repair 先例）。
- `audit()` 全量加载，大库（数万条）的耗时/内存未做分页。
- 运行中的实例不感知 CLI 删除，可能以内存快照短暂「复活」条目；重启后一致。
- `--limit 0` = 全部，与常见「0 条」直觉相反，写入帮助文本。
