# 任务：配置写回的可逆效应（change 0130 / E68）

## 1. 规格先行

- [x] 写 `specs/configuration/spec.md` delta（MODIFIED「配置校验与生效」+ 1 Scenario）
- [x] `openspec validate --all` 通过（31/0 → 归档后 30/0）

## 2. ADR

- [x] `doc/01-architecture/adr.md` 增 ADR-0123 + `## 变更追踪` 行

## 3. 测试先行（红）

- [x] `test_write_patch_records_reversible_effect`：写回后 `rollback("config")` ⇒ yaml 原文复现
- [x] `test_apply_change_and_write_patch_share_one_trace`：一次回滚同时回退内存与磁盘
- [x] `test_write_patch_undo_is_recorded_before_replace`：记录先于 `os.replace`（替换失败则 yaml 未变、undo 幂等）

## 4. 实现

- [x] `write_patch` 在 `os.replace` 前 `record(Effect(op="config_write_patch", …, trace_id="config"))`
- [x] 新增 `_restore_yaml(previous: bytes | None)`

## 5. 门禁

- [x] `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` = 0/0/0
- [x] `.venv/bin/pytest -q`（1614 → 1617）

## 6. 文档与归档

- [x] `doc/03-interfaces/configuration-interface.md` / `doc/02-modules/configuration.md` / `doc/04-testing/test-cases.md`
- [x] 手工归档 `archive/2026-10-06-0130-config-write-patch-reversible/`
- [x] `coding-plan/phase-34.md` §1 E68 + §9 行；`coding-plan/README.md` 索引
- [x] 记忆文件更新
- [x] 单次提交 `fix(configuration): 配置写回可逆（change 0130）`
