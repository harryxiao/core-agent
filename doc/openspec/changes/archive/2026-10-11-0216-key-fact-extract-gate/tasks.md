# Tasks 0216 — 关键事实抽取门控

## 1. 规格先行

- [x] `specs/memory/spec.md`：**MODIFIED**「结构化实体抽取（关键事实）」（整段替换：末句扩写 ＋
      15 既有 Scenario 逐字保留 ＋ ADD Scenario ×2）
- [x] ADR-0206（`doc/01-architecture/adr.md`）

## 2. 实现

- [x] `configuration/manager.py`：`_CONFIG_SPECS` memory 块加 `memory.key_fact_extract`
      （`default=True`、`ADVANCED`、`map_to` 同名、三面 flag/env 齐备）
- [x] `configuration/manager.py`：新访问器 `key_fact_extract()`（镜像 `relation_extract()`；
      **唯一差异 = 缺省 True ＋ 非法值回落 True**，`not in _FEATURE_FALSE`）
- [x] `runtime.py:578`：`key_fact_extractor=extract_with(_llm_text) if config.key_fact_extract() else None`
- [x] **零改动**：`memory` 非结构化段 ⇒ **不加** `_memory_errors` 校验

## 3. 测试（`tests/test_key_fact_gate.py`，8 用例）

- [x] 三面声明（flag/env/default/map_to）/ 缺省 on / yaml 关（＋非「未知段」）/ env 关 /
      非法值回落 on / 组合根两态接线 / 逐字锚（关与开的摘要产物逐字相同）

## 4. 反证

- [x] A 摘门 ⇒ 1 红；B 缺省翻 False ⇒ 3 红；复原 `diff -q` 逐字节相同（见 design.md §4）

## 5. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0216-key-fact-extract-gate`
- [x] 手工归档（MODIFIED 整段替换 + 2 ADD Scenario）
- [x] `doc/04-testing/test-cases.md` §129 + 基线 bump；台账 E153（`known-risk.md` §1/§3）
- [x] 单次提交 `feat(configuration): …`（change 0216 / ADR-0206 / 台账 E153）
