# Tasks 0207 — 恢复扫描入口全覆盖

## 1. 规格（spec-first）

- [x] `specs/durability/spec.md`：**MODIFIED**「崩溃恢复」（全量替换，narrative 补「全部交互入口」
      句 + **ADD** Scenario「全部交互入口启动扫描呈现」；其余 7 Scenario 逐字保留）
- [x] ADR-0197 +「变更追踪」表行
- [x] 其余 3 条 `durability` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] `tests/test_entry.py` 增补：桩 runtime（`recover()` 返回未完成任务句柄）⇒ repl / run / app /
      mcp serve 四入口启动后 stderr 含「未完成任务」+ `task --resume` 提示；无未完成任务 ⇒ 静默
- [x] **反证**：摘掉 `surface_recovery=True`（repl/run/app）与 `mcp serve` 的 `_surface_incomplete`
      调用 ⇒ 相应用例红

## 3. 实现（绿）

- [x] `src/core/entry.py`：`_repl`（`:499`）/ `_run`（`:1687`）/ `_app`（`:523`）
      `_build_ui(..., surface_recovery=True)`；`_mcp_serve`（`:775` 后）显式 `_surface_incomplete(runtime)`

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] **反证**：见 §2 末
- [x] `openspec validate 2026-10-11-0207-recovery-scan-coverage`
- [x] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失；
      `durability` 4→4 req / 13→14 scen）
- [x] `doc/04-testing/test-cases.md` §120 + 基线 bump；台账 E144（`known-risk.md` §1）+
      §3 ADR-0197 行；`doc/02-modules/cli-ops.md`（或 entry 相关节）增补
- [x] 单次提交 `feat(durability): 恢复扫描入口全覆盖（change 0207 / ADR-0197 / 台账 E144）`
