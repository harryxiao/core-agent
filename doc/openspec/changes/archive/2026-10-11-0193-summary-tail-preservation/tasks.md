# Tasks 0193 — 滚动摘要首尾保留（尾部不销毁）+ 价值闸留痕

## 1. 规格（spec-first）

- [x] `specs/memory/spec.md`：MODIFIED「记忆压实」（首尾保留条款 + 价值门控留痕条款
      + 2 Scenario「摘要越界首尾保留（尾部不销毁）」/「价值门控跳过留痕（只报会话键）」），
      既有 20 Scenario 标题零丢失
- [x] ADR-0183（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_memory.py`：>2000 prior ⇒ prompt 的既有摘要槽含**尾部**（原文末段）与中略标记；
      节选总长 ≤ `MAX_SUMMARY_CHARS`
- [x] `test_memory.py`：≤2000 prior ⇒ **逐字**投喂全文（与变更前一致）
- [x] `test_memory.py`：越界**触发**语义仍准点 —— 由既有
      `test_memory_summary_promotion.py::test_summary_crossing_bound_delivers_promotion_once`
      承载（触发路径**零改动**，本条以回归绿作证，不另写重复用例）
- [x] `test_memory.py`：价值闸跳过 ⇒ `warnings.warn` 留痕**只报会话键**（不回显正文）

## 3. 实现（绿）

- [x] `memory/summarize.py`：增 `_SUMMARY_TAIL_CHARS` + `_elide_summary()`；`build_prompt` 用
- [x] `memory/store.py`：`_summarize_sessions` 价值闸跳过补 `warnings.warn`（只报会话键）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
      （**2227 passed** = 2223 + 4）
- [x] `openspec validate 2026-10-11-0193-summary-tail-preservation`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E130（`known-risk.md` §1）+
      `doc/02-modules/memory.md` / `doc/03-interfaces/memory-interface.md` 对应面
- [x] 单次提交 `feat(memory): …`
