# Tasks 0202 — 情景链（时序相邻标注）

## 1. 规格（spec-first）

- [ ] `specs/memory/spec.md`：ADDED「情景链（时序相邻标注）」+ 5 Scenario
- [ ] ADR-0192（`doc/01-architecture/adr.md`）+ 「变更追踪」表行
- [ ] **既有规格零改动**（`memory` 既有 13 条 Requirement、`loop` 规格**全部**逐字保留）

## 2. 测试先行（红）

- [ ] `tests/test_loop_causal_link.py`：开 ⇒ 同会话连续两轮失败，第二条失败条目 `tags` 含
      `after:<tid1>`（红：`_last_trace` 与标签均未实现）
- [ ] 关（缺省）⇒ `tags == ["loop", "failure"]`（**逐字锚**）
- [ ] 带 `after:` 标签 ⇒ `_episodic_groups` **仍排除**该条目
- [ ] 带 `after:` 标签 ⇒ `exclude_fact_tags={"steps"}` 下**仍进**「相关事实」面
- [ ] `session_chain`：只含该会话、按 `ts` 不减；调用前后 `reuse_count` **不变**、
      效应追踪器**零新增记录**

## 3. 实现（绿）

- [ ] `src/core/loop/default.py`：`_last_trace: dict[str, str]` + 构造参 `causal_links: bool = False`
      + `remember` 标注与末尾登记
- [ ] `src/core/memory/store.py`：`ChainNode`（frozen）+ `session_chain`
- [ ] `src/core/memory/__init__.py`：导出 `ChainNode`
- [ ] `src/core/configuration/manager.py`：`loop.causal_links`（ConfigSpec 行 + 独立访问器 +
      `_loop_errors` 校验）
- [ ] `src/core/runtime.py`：注入四只 loop

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
      （2263 → 2268）
- [ ] **反证**：令标注**忽略开关**（无条件加 `after:`）⇒ 缺省逐字锚转红；复原 ⇒ 绿
- [ ] `openspec validate 2026-10-11-0202-episodic-causal-link`
- [ ] 手工归档（ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §115 + 基线 bump；台账 E139（`known-risk.md` §1）+
      §3 ADR-0192 行；`doc/02-modules/memory.md` 增一节
- [ ] 单次提交 `feat(memory): …`
