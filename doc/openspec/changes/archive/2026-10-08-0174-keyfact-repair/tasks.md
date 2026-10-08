# Tasks: keyfact-repair（失效关键事实的运维修复）

> 顺序：**规格已先行**（§1）⇒ 测试先行（§2 红）⇒ 实现（§3）⇒ 门禁（§4）⇒ 文档/台账/记忆（§5）⇒ 提交（§6）。
> 每项可独立验收；四门禁**直连二进制、禁 `uv run`**。

## 1. 规格（已完成）

- [x] 1.1 `specs/memory/spec.md` delta：ADDED「失效关键事实的运维修复」+7 Scenario
- [x] 1.2 `specs/cli-ops/spec.md` delta：MODIFIED「运维命令集」+1 Scenario（既有 9 条逐字保留）
- [x] 1.3 `proposal.md` / `design.md`
- [x] 1.4 `openspec validate 2026-10-08-0174-keyfact-repair` ⇒ valid

## 2. 测试先行（红态证据）

- [x] 2.1 `tests/test_memory_keyfact_repair.py`：识别失效条目（不误伤 coeffect 引用 / 无 ref 正常条目）
- [x] 2.2 同文件：重抽成功 ⇒ 该会话旧条目**全删**、新条目落库（实体名不重者也删）
- [x] 2.3 同文件：同 slug ⇒ 新值**不**被删（`keyfact.<slug>` 保留新取值）
- [x] 2.4 同文件：抽取器**未注入** ⇒ 不删、无写入、`skipped` 标明
- [x] 2.5 同文件：抽取器**抛错** ⇒ 不删、无写入、`skipped` 标明
- [x] 2.6 同文件：材料含 **L4** 归档条目 ⇒ 仍能重抽（守护「去掉层过滤」）
- [x] 2.7 同文件：备份文件内容 = 被删条目原文（可解析、id 集合相符）
- [x] 2.8 同文件：备份写入失败 ⇒ 不删（新条目保留）
- [x] 2.9 同文件：幂等（无失效条目 ⇒ 无写入、无备份）
- [x] 2.10 同文件：`dry_run=True` ⇒ 不删、不落库、不落备份
- [x] 2.11 同文件：无 `session:` 标签的失效条目 ⇒ 不删、报告标明
- [x] 2.12 跑红：实现落地前跑该文件 ⇒ **12 failed / 0 passed**，全为 `AttributeError: 'MemoryStore' object has no attribute 'repair_stale_key_facts'`（新面确由本 change 引入）

## 3. 实现

- [x] 3.1 `store.py`：`RepairReport` dataclass（`identified` / `sessions` / `deleted` / `written` / `backup_path` / `skipped` / `dry_run`）
- [x] 3.2 `store.py`：`_stale_key_facts()`（判据：`tags` 含 `ref:` 且非 `coeffect:` 形态 + 取值为 `REDACTED`）
- [x] 3.3 `store.py`：`_material_for_session(sid)`（`kind == "episodic"` **全层**，按 `session_id` 或 `session:<sid>` 归属）
- [x] 3.4 `store.py`：`_delete_entry(entry)`（热区 pop + 后端 delete + `EffectTracker` 记录进程内 undo）
- [x] 3.5 `store.py`：`repair_stale_key_facts(*, dry_run=False)`（按会话：材料 → 重抽 → 备份 → 落新 → 删旧**减去新写 id**；三处 fail-closed）
- [x] 3.6 `core/memory/__init__.py`：导出 `RepairReport`
- [x] 3.7 `entry.py`：`mem_sub.add_parser("repair-keyfacts", ...)` + `--dry-run`
- [x] 3.8 `entry.py`：`_memory()` 改**分派表**（maintain / repair-keyfacts）+ 报表打印
- [x] 3.9 跑绿：§2 全部用例通过

## 4. 四门禁（直连二进制）

- [x] 4.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 4.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] 4.4 `.venv/bin/pytest -q` ⇒ 全绿（基线 **2003**，记增量）

## 5. 文档 / 归档 / 台账 / 记忆

- [x] 5.1 `doc/01-architecture/adr.md`：**ADR-0165** + 变更追踪行
- [x] 5.2 `doc/02-modules/memory.md`、`doc/03-interfaces/memory-interface.md` 相关段
- [x] 5.3 `doc/04-testing/test-cases.md` **§87**（TC-KFREPAIR，含红态证据）
- [x] 5.4 `coding-plan/known-risk.md` §1 新行 **E111** + §3 ADR-0165 局限行
- [x] 5.5 手工归档：delta 并入 canonical（`memory` / `cli-ops`）⇒ `mv` 到
      `doc/openspec/changes/archive/2026-10-08-0174-keyfact-repair/` ⇒ `openspec validate --all` ⇒ **31/0**
- [x] 5.6 记忆：`MEMORY.md` 指针行 + `coding-plan-leftover-walkthrough.md` 追加 change `0174` 节

## 6. 提交

- [x] 6.1 单次提交 `feat(memory): 失效关键事实的运维修复（change 0174 / ADR-0165 / 台账 E111）`
      （排除 `config.yaml` / `.claude/settings*.json` / `uv.lock` / `coding-plan/phase-*.md` 等禁提项）

## 7. 端到端（用户）

- [ ] 7.1 `core-agent memory repair-keyfacts --dry-run` ⇒ 报表列出 2 个会话 / 16 条失效条目
- [ ] 7.2 `core-agent memory repair-keyfacts` ⇒ 落备份文件、删 16 条旧条目、写入重抽结果；
      复跑一次 ⇒ 无失效条目、无写入（幂等）
