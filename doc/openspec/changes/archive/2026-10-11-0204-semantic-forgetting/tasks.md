# Tasks 0204 — 语义遗忘面

## 1. 规格（spec-first）

- [ ] `specs/memory/spec.md`：**MODIFIED**「记忆遗忘（forgetting）」（全量替换，含 7 既有 Scenario
      + 3 新 Scenario；`提炼产物与元策略不被遗忘` GIVEN 收窄、标题不动）
- [ ] ADR-0194（`doc/01-architecture/adr.md`）+「变更追踪」表行
- [ ] 其余 14 条 `memory` Requirement **逐字保留**

## 2. 测试先行（红）

- [ ] `tests/test_semantic_forgetting.py`：
      - 缺省关 ⇒ 陈旧 `source="extraction"`/`"relation"` 仍留 L2（零回归锚）
      - 开 ⇒ 陈旧 `keyfact.*`/`relation.*` 迁 L4 + 返回句柄 + `audit` 可见
      - 开 ⇒ 陈旧 `source="compaction"`/`"context"` **仍留 L2**
      - 开 ⇒ 新鲜派生事实不留；开 ⇒ `reuse_count=3` 派生事实被延缓
      - 开 ⇒ 归档**可逆**（`rollback("forgetting.<id>")` 迁回 L2）
      - 开 ⇒ L0/L3 仍不受影响
      - 配置缺省关 + 三面（CLI/ENV/原生 bool）解析
- [ ] **反证**：同一陈旧 `extraction` 条目，`False ⇒ forget()==[]`；翻 `True ⇒` 被归档

## 3. 实现（绿）

- [ ] `src/core/memory/store.py`：`_FORGETTABLE_SEMANTIC_SOURCES` 常量 + `MemoryStore.__init__`
      新增 `semantic_forgetting: bool = False` + `forget()` 守卫改短路布尔 + docstring 收窄
- [ ] `src/core/configuration/manager.py`：`memory.semantic_forgetting`（ConfigSpec 行 + 访问器）
- [ ] `src/core/runtime.py`：`MemoryStore(..., semantic_forgetting=config.semantic_forgetting())`

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：摘掉 `self._semantic_forgetting and` 短路项 ⇒ 缺省锚转红；复原 ⇒ 绿
- [ ] `openspec validate 2026-10-11-0204-semantic-forgetting`
- [ ] 手工归档（MODIFIED 合并；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §117 + 基线 bump；台账 E141（`known-risk.md` §1）+
      §3 ADR-0194 行；`doc/02-modules/memory.md` 增一节
- [ ] 单次提交 `feat(memory): 派生事实参与遗忘（语义遗忘面，缺省关）`
