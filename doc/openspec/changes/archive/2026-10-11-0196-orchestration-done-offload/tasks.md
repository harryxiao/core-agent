# Tasks 0196 — 任务完成回调卸载

## 1. 规格（spec-first）

- [x] `specs/orchestration/spec.md`：MODIFIED「异步执行单元契约」（+「收尾回路不阻塞」bullet
      + 1 Scenario「完成回调不阻塞事件循环」），既有 3 Scenario 标题零丢失
- [x] ADR-0186（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_scheduler.py`：桩 `on_done` 在**工作线程**执行（记录 `threading.current_thread().ident`
      ≠ 主线程 ident）（红：变更前等于主线程 ident）
- [x] `test_scheduler.py`：回调内 `time.sleep` 不阻塞事件循环（同波次并发 / 流式产出不被同步阻塞）

## 3. 实现（绿）

- [x] `orchestration/scheduler.py`：`DONE` 分支 `self._on_done(...)` → `await asyncio.to_thread(...)`
      ＋ 文件头 `import asyncio`

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0196-orchestration-done-offload`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E133（`known-risk.md` §1）+
      `doc/02-modules/orchestration.md` / `doc/03-interfaces/*` 对应面
- [x] 单次提交 `feat(orchestration): …`
