# Tasks 0191 — 恢复呈现接线（启动扫描+呈现，续跑仍显式）

## 1. 规格（spec-first）

- [x] `specs/durability/spec.md`：MODIFIED「崩溃恢复」（纯扫描语义 + 降级跳过 + 句柄标识任务 +
      2 Scenario），既有 5 Scenario 标题零丢失
- [x] `specs/cli-ops/spec.md`：MODIFIED「会话命令族与交互入口续聊」（入口启动呈现 + `--resume`
      ts 序 + 2 Scenario），既有 6 Scenario 逐字保留
- [x] ADR-0181（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_durability_crash.py`：`RestoreHandle` 标识所属 task id
- [x] `test_phase15.py`：坏任务（检查点全无有效快照）降级跳过、其余任务句柄照常返回 + 告警
- [x] `test_entry.py`：`task` 启动呈现未完成任务（打印 + 不重执行）；空库静默；`serve` 启动呈现；
      `--resume` 取 ts 最新检查点（落盘序 ≠ 时间序）

## 3. 实现（绿）

- [x] `durability/models.py`：`RestoreHandle` 增 `task_id`
- [x] `durability/manager.py`：`restore` 构造补 `task_id`
- [x] `runtime.py`：`_recover_incomplete` 对 `restore` 包 try/except + 告警
- [x] `entry.py`：`_surface_incomplete` 助手 + `_build_ui(surface_recovery=…)` + `_serve` 传入 +
      `_task` fresh 启动扫 + `--resume` ts 序

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0191-recovery-surfacing`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E128（`known-risk.md` §1）
- [x] 单次提交 `feat(durability): …`
