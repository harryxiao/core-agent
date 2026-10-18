# Proposal 0262 — 记忆检视与纠错 CLI

## Why

记忆是 core-agent 的核心资产，但运维面目前只能 `maintain` / `repair-keyfacts`：用户无法查看
系统到底存了什么、无法按 id 取出单条全文，也无法删除一条错误记忆。对比审查（2026-10-18）
把「缺用户纠错面」列为 P1 短板 —— 记忆只进不出，错误事实只能等自然遗忘，用户没有最直接的
纠正手段。

## What Changes

- `memory` 子命令新增三个一次性运维动作（均不启动常驻进程、不改变运行态）：
  - `memory list [--limit N]`：列出条目（id / layer / kind / source / session / importance /
    ts / 摘要）；`--limit` 只限制**展示**条数（缺省 50，`0` = 全部），底层 `audit()` 仍全量读取。
  - `memory get <id>`：打印单条全文与元数据；内容经 `redact_secrets` 脱敏后回显。
  - `memory delete <id>`：删除前把该条 JSON **追加**到 `$CORE_STATE_DIR/memory-deleted.jsonl`
    （0600），再调用 `MemoryStore.discard`；备份写入失败 ⇒ **fail-closed**（不删除）。
- 只复用公开 API：`MemoryStore.audit(None)` 与 `MemoryStore.discard`；不新增 `tools.memory`
  工具面、不读私有 `_all_entries`。

## Impact

- `src/core/entry.py`（三个子命令 + 分派）。
- 规格：`cli-ops` **MODIFIED**「运维命令集」（+3 scenarios）。
- 文档：`doc/03-interfaces/cli-ops-interface.md`、`doc/04-testing/test-cases.md` §174、
  ADR-0252 / 台账 E198。
- 测试：`tests/test_entry.py` 新增 list/get/delete/未知 id/备份失败/脱敏用例。

## 不做（明确边界）

- 不新增 `memory restore` 子命令（回滚靠备份文件人工恢复，沿用 `repair-keyfacts` 先例）。
- 不做 Web / TUI 记忆编辑；不新增模型侧 `tools.memory`。
- 不做批量删除 / 按条件清理（避免一次误删大面积记忆）。
- `audit()` 全量加载：大库的内存与耗时作为已知局限记录，不在本 change 优化。
