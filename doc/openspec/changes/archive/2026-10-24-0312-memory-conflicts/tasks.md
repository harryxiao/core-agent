# Tasks — 冲突裁决的可见性与计数（0312）

## 1. 规格与测试先行

- [x] 1.1 `proposal.md` / `design.md` / `specs/memory/spec.md`（MODIFIED ×4 + ADDED ×1）
- [x] 1.2 新增 `tests/test_memory_conflicts.py`（红）：取代计数 / 同值不计数 / 审计行形状
      （op/id/target/reason、无取值明文）/ 审计关闭仍计数 / 审计失败仍计数 / stats `conflicts`
      含墓碑化旧版 / CLI 文本成对与排序 / `--limit` / `--json` 固定键 / 空库 / 零强化零写入 /
      实体名派生 / 脱敏
- [x] 1.3 更新既有断言：`tests/test_memory_stats_cli.py::test_stats_json_fixed_keys`（+`conflicts`）、
      文本模式含 `conflicts`；`tests/test_memory_metrics.py::test_snapshot_has_fixed_keys`（+`memory.conflicts`）

## 2. 实现

- [x] 2.1 `src/core/memory/stats.py`：`FIXED_METRIC_KEYS` 增 `memory.conflicts`；`MemoryStats.conflicts`
      （缺省 0）与 `to_dict()`；`_count_entries` 计 `superseded_by != ""`（含墓碑化旧版）
- [x] 2.2 `src/core/memory/store.py`：`_audit_event(..., target="")`；`_supersede` 自增
      `memory.conflicts` 并追加 `op="conflict"`（`reason="newer_wins"`, `target=新 id`）
- [x] 2.3 `src/core/entry.py`：`memory conflicts [--json] [--limit N]`（缺省 20、0=全部）——
      从 `memory.audit(None)` 派生、按新版 `ts` 降序、`_one_line_summary` 脱敏、实体名派生；
      注册 `_MEMORY_COMMANDS`、更新 usage 字符串

## 3. 门禁

- [x] 3.1 聚焦跑：`uv run pytest tests/test_memory_conflicts.py tests/test_memory_stats_cli.py
      tests/test_memory_metrics.py tests/test_memory_stats.py`
- [x] 3.2 全量 `uv run pytest`（预期 3592 + 新增）
- [x] 3.3 `uv run ruff check` / `uv run ruff format --check`（改动文件）
- [x] 3.4 `uv run pyright`（`src` 0 error）
- [x] 3.5 反证 5/5（`cp` 到 `/tmp` + `md5sum` 复原）：去指标 ⇒ 计数红；去审计事件 ⇒ 审计行红；
      `conflicts` 改按 `status=="superseded"` ⇒ 墓碑用例红；CLI 改按审计派生 ⇒ 历史链用例红；
      去脱敏 ⇒ 脱敏用例红

## 4. 文档与收口

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0302（只实现第 3 级裁决；被拒：trust/confidence、
      disputed、审计派生 CLI）
- [x] 4.2 `coding-plan/known-risk.md`：E248 + §3 局限行
- [x] 4.3 `doc/04-testing/test-cases.md`：§225（TC-MEMCONF-01~17 + 反证 5/5）
- [x] 4.4 `doc/02-modules/memory.md` §3.25、`doc/03-interfaces/memory-interface.md` §1.5、
      `coding-plan/cli-contract-baseline.md` 26f
- [x] 4.5 `openspec validate 0312-memory-conflicts` 与 `openspec validate --all` 全绿
- [x] 4.6 **用户确认后**归档 + 提交 + 推送；回填 walkthrough / MEMORY.md
