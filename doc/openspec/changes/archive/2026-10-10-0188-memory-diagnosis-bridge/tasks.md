# 任务 — 记忆面 → 诊断面桥（change 0188 / ADR-0179 / 台账 E125）

## 1. 规格（spec-first）

- [x] `specs/evolution/spec.md` — MODIFIED「对比诊断」（追加失败摘要条款：有界 / 不改判定 /
      缺省逐字 / fail-open）+ 1 新 Scenario；既有 3 Scenario 逐字保留
- [x] `proposal.md` / `design.md`（含 D2 依赖倒置、D3 新增字段而非改 `issue`、D5 走 `search("")`
      **不**走 `read`）/ `tasks.md`

## 2. 红测试（先失败）

- [x] `tests/test_evolution_attribution.py`（单元 5）+ `tests/test_evolution_wiring.py`（组合根 1）新增节「失败摘要桥」：
      未接线逐字不变（回归锚）/ 注入后含摘要 / 查询抛错降级 / 有界（截断 + 封顶 + 只查失败 trace）/
      组合根接线（端到端取回）
- [x] 既有归因用例继续绿（回归锚）
- [x] 确认红

## 3. 实现

- [x] `src/core/evolution/models.py`：`DiagnosisReport` 增 `failure_notes: list[str] = []`
- [x] `src/core/evolution/diagnoser.py`：`__init__` 增 `failure_lookup` 接缝；
      `diagnose` 三处返回分支**统一**经一个私有 `_with_failure_notes(report, failed)` 挂摘要
- [x] `src/core/runtime.py`：`Diagnoser(failure_lookup=…)`（闭包走 `backend.search("")` 按 id 取正文）

## 4. 四门禁（直连二进制）

- [x] `.venv/bin/ruff check src tests` → All passed
- [x] `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [x] `.venv/bin/pytest -q` → 基线 2200 → 2206（+6）

## 5. 归档（手工）

- [x] `openspec validate 2026-10-10-0188-memory-diagnosis-bridge` → valid
- [x] 脚本化合并（MODIFIED 替换同名 Requirement 块；断言 0 标题丢失 / 未触碰块逐字不变）⇒ `mv`
      至 `archive/`
- [x] `openspec validate --all` 全绿

## 6. 文档 / 台账

- [x] `doc/01-architecture/adr.md`：ADR-0179 + 变更追踪行
- [x] `doc/02-modules/evolution.md`；`doc/03-interfaces/evolution-interface.md`
- [x] `doc/04-testing/test-cases.md` 新 TC 节（§101）+ 基线 bump
- [x] `coding-plan/known-risk.md` §1 E125 行 + §3 ADR-0179 局限行

## 7. 记忆 / 提交

- [x] `MEMORY.md` + `coding-plan-leftover-walkthrough.md`（`0188` 节 + 批次进度）
- [x] 单次提交 `feat(evolution): …（change 0188 / ADR-0179 / 台账 E125）`
