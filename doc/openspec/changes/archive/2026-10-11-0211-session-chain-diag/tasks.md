# Tasks 0211 — session_chain 读侧进只读诊断面

## 1. 规格（spec-first）

- [x] `specs/memory/spec.md`：**MODIFIED**「情景链（时序相邻标注）」（全量替换；narrative 补 (g)
      只读呈现面 ＋ **ADD** Scenario ×2「只读诊断面呈现链」/「句柄未注入或空链时不抛」；
      既有 (a)-(f) 与 5 个 Scenario **逐字保留**）
- [x] ADR-0201 +「变更追踪」表行
- [x] 其余 `memory` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] `tests/test_diagnostics.py` 增补：`_deps(chain=…)` ⇒ `render_chain` 呈现失败标记与 `after`；
      未注入 ⇒ `未接线`；空链 ⇒ `（空）`；脏句柄（抛异常）⇒ 降级一行不抛
- [x] `tests/test_diagnostics.py`：把 `render_chain` 并入 `_all_views`（泄漏断言面）与列对齐断言
- [x] `tests/test_repl.py`：`_READONLY_KINDS` 增 `/chain`（结果块 / 无 `❯` / 零对话轮次）
- [x] `tests/test_diagnostics.py`：**零效应锚** —— 调用前后 `memory.jsonl` 无写入、
      `reuse_count` 不变
- [x] **反证**：摘 `render_chain`（或 `Deps.chain` 接线）⇒ TUI 用例红

## 3. 实现（绿）

- [x] `diagnostics/deps.py`：`Deps` 加 `chain: Callable[[str], list[ChainNode]] | None = None`
- [x] `diagnostics/views.py`：`_MAX_CHAIN_ROWS = 20` ＋ `render_chain(deps)`（`_sealed` 包裹、
      按 `deps.sessions` 分组、逐会话取最近 N 节、`align_rows` 列对齐）
- [x] `diagnostics/__init__.py`：导出 `render_chain`
- [x] `entry.py`：`_diag_deps` 注入裸店句柄（`MemoryStore(backend=FileBackend(
      _state_path("memory.jsonl"))).session_chain`）
- [x] `ui/repl.py`：`_COMMANDS` 加 `/chain` ＋ `_show_chain`（走既有 `_readonly_report`）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] **反证**：见 §2 末
- [x] `openspec validate 2026-10-11-0211-session-chain-diag`
- [x] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` §124 + 基线 bump；台账 E148（`known-risk.md` §1）+
      §3 ADR-0201 行；`doc/02-modules/`（memory / diagnostics 或 ui）增补
- [x] 单次提交 `feat(memory): session_chain 读侧进诊断面（change 0211 / ADR-0201 / 台账 E148）`
