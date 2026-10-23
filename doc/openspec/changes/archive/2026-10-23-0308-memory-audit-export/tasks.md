# Tasks — 记忆治理审计与导出（0308）

## 1. 规格与红灯

- [x] 1.1 写 `specs/memory/spec.md`、`specs/configuration/spec.md` delta（本目录）
- [x] 1.2 新增 `tests/test_memory_audit.py`：事件字段/无正文、幂等与拒收不审计、删除、
      遗忘 reason/hash、fail-open + 单次告警、0600 + 坏行容错、配置三面 + 归一 + 接线
- [x] 1.3 新增 `tests/test_memory_export_cli.py`：`--yes` 确认门、jsonl/json 脱敏与 0600、
      导出审计事件、`memory audit` 尾部读取与空态
- [x] 1.4 跑新用例确认全红（`ImportError: MemoryAuditLog`，25 项）

## 2. 实现

- [x] 2.1 `src/core/memory/audit.py`：`MemoryAuditLog`
      （record / read / 0600 / 单行 `os.write` / 字段脱敏截断 / 失败一次告警）
- [x] 2.2 `src/core/memory/__init__.py` 导出新类型
- [x] 2.3 `MemoryStore(audit_log=None)`；`write()` / `_delete_entry` / `forget` 三处钩子；
      `record_export(count, target, format)`
- [x] 2.4 `ConfigManager`：ConfigSpec `memory.audit_log`（缺省 true，三面）+ `audit_log_enabled()`
      （集合外归一为 true）
- [x] 2.5 `runtime.py`：启用时注入 `MemoryAuditLog($CORE_STATE_DIR/memory.audit.jsonl)`，
      关闭时 `None`；新增 `_memory_audit_path()`
- [x] 2.6 `entry.py`：`memory audit [--limit]`、`memory export [--format|--out|--yes]`、
      分派表与用法串同步
- [x] 2.7 新用例转绿；全量 `uv run pytest` **3487 passed**

## 3. 门禁与反证

- [x] 3.1 `uv run ruff check`、`uv run ruff format --check`、`uv run pyright`（0 errors）
- [x] 3.2 反证 5/5（`cp` 到 `/tmp` + `md5sum` 复原）：
      - 去掉 `write` 钩子 ⇒ 1 红；
      - 审计行写入 `content` ⇒ 1 红；
      - 去掉 `--yes` 判断 ⇒ 1 红；
      - `audit_log_enabled` 集合外归一改为 false ⇒ 3 红；
      - 去掉 `delete` 钩子 ⇒ 1 红
- [x] 3.3 `openspec validate 2026-10-23-0308-memory-audit-export` 通过；
      `openspec validate --all` **32/0**

## 4. 文档

- [x] 4.1 `doc/02-modules/memory.md`：§3.22 审计与导出 + §5 边界行
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：构造参、`record_export`、§1.2 审计日志
- [x] 4.3 `doc/03-interfaces/configuration-interface.md`：§2.22 `memory.audit_log`
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0298（含被拒备选与局限）+ 追踪行
- [x] 4.5 `coding-plan/known-risk.md`：E244
- [x] 4.6 `doc/04-testing/test-cases.md`：§221
- [x] 4.7 `doc/03-interfaces/prompts.md` ⑭ 落点行号同步（`entry.py:2067`）
- [ ] 4.8 更新台账与 `MEMORY.md` 索引（归档提交后）

## 5. 收口（需用户显式确认）

- [ ] 5.1 归档 change（归档后 `validate --all` 31/0）
- [ ] 5.2 提交、推送；提交信息 `feat(memory): 治理审计与导出（change 0308 / ADR-0298 / 台账 E244）`
