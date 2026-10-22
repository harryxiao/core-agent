# 提案：记忆落盘跨进程合并与遗忘检索隔离（P0）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 的走查（2026-10-22）确认两项 P0：

1. **跨进程全量重写 ⇒ 记忆静默丢失**：`FileBackend` 构造时只加载一次
   （`src/core/memory/backend.py:26-33`），每次写入都用进程内快照**全量重写** `memory.jsonl`
   （`backend.py:107-116`）；而 `read()` 命中即强化并落盘（`store.py:395-420`），循环每轮都跑。
   TUI 长驻进程、`task`/cron 短进程、`memory maintain` 共用 `$CORE_STATE_DIR/memory.jsonl`
   （`runtime.py:298-303`）⇒ 后写者整体覆盖先写者，无锁、无告警。对照：转录用
   `O_APPEND` 单次写（`doc/02-modules/memory.md:145`），后台任务登记已加 flock（change `0283`）。
2. **遗忘不生效**：`forget()` 只把低分条目迁 L4（`store.py:786-804`），`read()` 不过滤层
   （`store.py:330-393`，L4 仅经权重降 0.08），`failure_lessons()` 亦层无关
   （`store.py:622-645`）⇒ 被“遗忘”的内容仍从**两个注入面**进入提示词。SDD §5.6 / A7 要求
   forget 后召回与索引均不可见（墓碑保留供审计）。

## What Changes

- **跨进程合并落盘**：`FileBackend` 的 `put` / `put_many` / `delete` 在**独占建议锁**内
  **先读盘、再合并本次变更集**（新增/覆盖的 id 与删除的 id），然后原子替换；合并后进程内
  集合采纳盘上最新集合。锁取不到按 **fail-open** 退化为无锁写（记忆写入不得成为新失败面）。
- **中性锁模块**：新增 `src/core/filelock.py` 承载 `exclusive_file_lock` /
  `try_exclusive_file_lock`（原实现位于 `core/orchestration/state_files.py`），后者改为
  re-export；`core.memory` 只依赖中性模块，不反向依赖编排层。
- **遗忘隔离**：`forget()` 在迁移 L4 的同时打 `forgotten` 标签（与迁移同一 trace，可回滚）；
  `read()` 与 `failure_lessons()` 缺省排除带该标签的条目；`read(include_forgotten=True)`
  供审计/显式查看。
- 规格 `memory` **MODIFIED ×3**：「记忆后端落盘耐久」（+ 跨进程合并承诺与 4 Scenario）、
  「记忆遗忘（forgetting）」（+ 标签 / 退出注入面 / 可回滚，新增 3 Scenario）、
  「情景链」（(h) 失败教训读面排除遗忘条目，+ 1 Scenario）。

## Non-goals

- 不改 `memory.jsonl` 格式（不引入 append-only journal / 墓碑文件 / 新字段）。
- 不改变「归档 ≠ 遗忘」：压实、重要度闸门、L2 软上限造成的 L4 归档**仍可被召回**
  （只有 `forgotten` 标签生效）。
- 不做导出、重建索引、保留期、审计日志（走查的 P2 面）。
- 不解决同一 id 的并发写顺序（同 id 竞争保持 last-writer-wins）。

## Impact

- 代码：`src/core/memory/backend.py`（合并落盘）、`src/core/memory/store.py`
  （`forget` / `read` / `failure_lessons`）、`src/core/filelock.py`（新）、
  `src/core/orchestration/state_files.py`（re-export）。
- 文档：`doc/02-modules/memory.md` §§3.10/3.11、`doc/03-interfaces/memory-interface.md`
  §1/§5；ADR-0291；known-risk E237；test-cases §214。
- 测试：`tests/test_memory_backend_durability.py` +4；新增 `tests/test_memory_forget_recall.py`（7）。
