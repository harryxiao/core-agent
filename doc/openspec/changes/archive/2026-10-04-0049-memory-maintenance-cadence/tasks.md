# Tasks: 记忆维护节拍

## 1. 规格先行

- [x] 1.1 `specs/loop/spec.md` delta：MODIFIED「执行循环」——收尾维护节拍（间隔可配置、时钟可注入、失败降级）；新增场景「维护节拍触发遗忘」「未达间隔不重复维护」
- [x] 1.2 `specs/memory/spec.md` delta：MODIFIED「记忆遗忘（forgetting）」——触发面由维护节拍驱动（循环节拍 / 显式入口），判据与去向不变；新增场景「节拍驱动遗忘」
- [x] 1.3 `specs/cli-ops/spec.md` delta：MODIFIED「运维命令集」——命令集补 `memory maintain`；新增场景「记忆维护命令」
- [x] 1.4 `openspec validate 0049-memory-maintenance-cadence` 全绿

## 2. 测试先行（先红）

- [x] 2.1 `tests/test_loop.py`：`test_maintenance_cadence_skips_before_interval` / `test_maintenance_cadence_forgets_after_interval` / `test_maintenance_failure_degrades`（注入时钟与 SpyMemory，记录 `forget` 调用次数）
- [x] 2.2 `tests/test_entry.py`：`_TOP_LEVEL_COMMANDS` 加 `memory`；`test_memory_maintain_runs_maintenance`（monkeypatch 装配或真 runtime + tmp config，断言输出含归档条数）
- [x] 2.3 运行上述用例确认**失败**（红）

## 3. 实现

- [x] 3.1 `src/core/loop/default.py`：构造参数 `clock` / `maintenance_interval`；`_last_maintenance`；`_maintain_memory(trace_id)` 并在 astream 收尾「记忆」步之后调用
- [x] 3.2 `src/core/memory/protocol.py`：`MemoryStore` 补 `forget(*, threshold: float = ...) -> list[MemoryId]` 声明
- [x] 3.3 `src/core/entry.py`：`_add_memory_parser`（`memory maintain`）+ `_memory_cmd` handler + `_HANDLERS["memory"]`

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/loop-interface.md`：构造面补 `clock` / `maintenance_interval`；收尾维护节拍说明
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：`MemoryStore` 面补 `forget`；遗忘触发面说明

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src + tests）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（合并 delta 入 `doc/openspec/specs/*`、tasks 勾选、`mv` 入 `changes/archive/2026-10-04-0049-memory-maintenance-cadence/`）
- [x] 5.5 `coding-plan/phase-19.md` §1/§2 A1 行标 ✅ 已关闭（change 0049 / commit）；README §2 下一步改 A3
