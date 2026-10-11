# Tasks 0203 — 实体关系抽取（relations）

## 1. 规格（spec-first）

- [ ] `specs/memory/spec.md`：ADDED「实体关系抽取（relations）」+ 10 Scenario
- [ ] ADR-0193（`doc/01-architecture/adr.md`）+ 「变更追踪」表行
- [ ] **既有规格零改动**（`memory` 既有 14 条 Requirement 逐字保留，不做 MODIFIED）

## 2. 测试先行（红）

- [ ] `tests/test_memory_relations.py`：未注入 ⇒ 零 `relation` 条目
- [ ] 落库形态（`id` / `content` / `tags` / `source` / `kind` / `session_id=""` / `trace_id`）
- [ ] 中文谓词「依赖」⇒ 规范 `depends_on`（`id` 与 `predicate:` 标注同规范）
- [ ] 未知谓词 ⇒ 丢弃 + `warnings.warn`（含实体名 / 原始谓词、不含取值）
- [ ] 密钥形状的 `head` / `tail` ⇒ 整条丢弃；留痕中实体名**已脱敏**
- [ ] 空 `head` / `tail` ⇒ 丢弃
- [ ] **同一三元组两次 ⇒ 一条条目**（幂等覆盖）
- [ ] `relation_cap(n)` 界住批量，且 `relation_cap is key_fact_cap`
- [ ] 关系**不进** `_episodic_groups`（`kind="semantic"`）
- [ ] 关系随 `compaction.<key>` 回滚**一并撤销**
- [ ] 关系**确实到达**「相关事实」面（`pack.facts` 含 `head --pred--> tail`）
- [ ] 长 `id` 经 `FileBackend` 往返（`put` → 新实例重载 `get`）

## 3. 实现（绿）

- [ ] `src/core/memory/extract.py`：`Relation` / `RelationExtractor` / `RELATION_PREDICATES`
      + `normalize_predicate` / `build_relation_prompt` / `parse_relations` / `scrub_relation`
      / `extract_relations_with` / `relation_cap`
- [ ] `src/core/memory/store.py`：构造参 `relation_extractor` + `_extract_relations`
      / `_plan_relations` / `_write_relation`；`_GATE_EXEMPT_SOURCES` 补 `"relation"`；
      `_RELATION_TAG` 常量；`_summarize_sessions` 调 `_extract_relations`
- [ ] `src/core/memory/__init__.py`：导出新公开面
- [ ] `src/core/configuration/manager.py`：`memory.relation_extract`（ConfigSpec 行 + 独立访问器）
- [ ] `src/core/runtime.py`：`relation_extractor=… if config.relation_extract() else None`

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：接线抽取器（或缺省翻 `True`）⇒ 出现 `relation.*` 条目；复原 ⇒ 绿
- [ ] `openspec validate 2026-10-11-0203-entity-relation-extraction`
- [ ] 手工归档（ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §116 + 基线 bump；台账 E140（`known-risk.md` §1）+
      §3 ADR-0193 行；`doc/02-modules/memory.md` 增一节
- [ ] 单次提交 `feat(memory): …`
