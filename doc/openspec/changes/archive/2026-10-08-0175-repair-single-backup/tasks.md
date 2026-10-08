# Tasks: repair-single-backup（修复备份「一次操作一份」）

> 顺序：**规格已先行**（§1）⇒ 测试先行（§2 红）⇒ 实现（§3）⇒ 门禁（§4）⇒ 文档/台账/记忆（§5）⇒ 提交（§6）。
> 每项可独立验收；四门禁**直连二进制、禁 `uv run`**。

## 1. 规格（已完成）

- [x] 1.1 `specs/memory/spec.md` delta：MODIFIED「失效关键事实的运维修复」——备份句追加「每次操作恰好一份」、
      失败句改为「不删**任何**条目（跨会话一并阻断）」、改 1 Scenario + 加 1 Scenario（7 → 8）
- [x] 1.2 `proposal.md` / `design.md`
- [x] 1.3 `openspec validate 2026-10-08-0175-repair-single-backup` ⇒ valid

## 2. 测试先行（红态证据）

- [x] 2.1 `tests/test_memory_keyfact_repair.py` **新增**：两会话 ⇒ 备份文件**恰好 1 份**、内容为两会话待删 id 的**并集**、`backup_path` 指向它
- [x] 2.2 同文件 **新增**：两会话 + 备份写入失败 ⇒ `deleted == []` 且两会话旧条目**都在**、`skipped["backup_failed"]` 含两会话、新条目已落
- [x] 2.3 核对既有单会话用例是否隐含「每会话一份」（如 `test_backup_file_keeps_original_entries`）⇒ 必要时收紧断言
- [x] 2.4 跑红：**1 failed / 13 passed** —— `test_two_sessions_share_one_backup` 失败，且形态比预期更锋利：两次调用落在**同一秒** ⇒ **同一路径** ⇒ 第二会话的备份**静默覆盖**第一会话的（文件恰好 1 个但内容只有会话 2 的待删条目）；另一新增用例 `test_backup_failure_blocks_every_session` 为**等价守护**（实现前后皆绿，诚实记之）

## 3. 实现

- [x] 3.1 `store.py`：`_repair_session` → `_collect_session(...) -> list[MemoryEntry]`（重抽 + 落新 + **返回** doomed；备份/删除代码移出）
- [x] 3.2 `store.py`：`repair_stale_key_facts` 三段式 —— ① 收集循环 ② **一次**备份（`doomed_all` 并集、一个时间戳）③ 统一删除
- [x] 3.3 `store.py`：备份失败 ⇒ `skipped["backup_failed"] = sorted(report.sessions)` + **不删任何条目**（操作级 fail-closed）
- [x] 3.4 跑绿：§2 全部用例 + 既有 12 用例全绿

## 4. 四门禁（直连二进制）

- [x] 4.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 4.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] 4.4 `.venv/bin/pytest -q` ⇒ **2017 passed**（基线 **2015**，**+2**）

## 5. 文档 / 归档 / 台账 / 记忆

- [x] 5.1 `doc/01-architecture/adr.md`：**ADR-0166** + 变更追踪行
- [x] 5.2 `doc/02-modules/memory.md` §3.4、`doc/03-interfaces/memory-interface.md` 相关段
- [x] 5.3 `doc/03-interfaces/cli-ops-interface.md` §6（备份「一次操作一份」口径）
- [x] 5.4 `doc/04-testing/test-cases.md` **§88**（TC-KFBACKUP，含红态证据）
- [x] 5.5 `coding-plan/known-risk.md` §1 新行 **E112** + §3 ADR-0166 局限行
- [x] 5.6 手工归档：delta 并入 canonical（`memory`）⇒ `mv` 到
      `doc/openspec/changes/archive/2026-10-08-0175-repair-single-backup/` ⇒ `openspec validate --all` ⇒ **31/0**
- [x] 5.7 记忆：`MEMORY.md` 指针行 + `coding-plan-leftover-walkthrough.md` 追加 change `0175` 节

## 6. 提交

- [x] 6.1 单次提交 `feat(memory): 修复备份一次操作一份（change 0175 / ADR-0166 / 台账 E112）`
      （排除 `config.yaml` / `.claude/settings*.json` / `uv.lock` / `coding-plan/phase-*.md` 等禁提项）

## 7. 端到端（用户）

- [ ] 7.1 `core-agent memory repair-keyfacts --dry-run` ⇒ 报表（零写入）
- [ ] 7.2 若将来再出现失效条目：单次操作 ⇒ **恰好一份**备份文件、失败即整次不删
