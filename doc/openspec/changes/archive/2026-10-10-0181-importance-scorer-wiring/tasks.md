# Tasks: 写入侧重要度闸门的生产接线与内部产物豁免面

**测试先行**：每层先写测试（红），再实现（绿）。四门禁直连二进制、**禁** `uv run`。

## Layer A —— 豁免面：内部派生产物不经评分 `src/core/memory/store.py`

- [x] A1. 测试：追加 `tests/test_memory.py`（红）—— ① scorer 恒返 0.1 + `source="compaction"`
  ⇒ 条目按意向层入库、`importance` 不变、**无** `warnings.warn` 留痕；
  ② `source="context"` / `source="extraction"` 同 ①（豁免面三来源齐）；
  ③ 回归锚：`source="loop"` 恒返 0.1 ⇒ **仍被拒收** + 留痕（既有用例不改，本条目明示不覆盖有机写入）
- [x] A2. 实现：模块常量 `_GATE_EXEMPT_SOURCES = frozenset({"compaction", "context", "extraction"})`；
  `write()` 中 `score = None if entry.source in _GATE_EXEMPT_SOURCES else self._gate_score(entry)`

## Layer B —— 评分器工厂 `src/core/memory/importance.py`（新）

- [x] B1. 测试：新建 `tests/test_memory_importance.py`（红）—— ④ `score_with(λ→"0.8")` 对条目的分值
  为 0.8；⑤ 输出含散文 + `0.35` ⇒ 取首个浮点 0.35；⑥ 无浮点 ⇒ 抛 `ValueError`；
  ⑦ 界外 `1.7` ⇒ 原值返回（**不** clamp）⇒ 经 `_gate_score` 界外路径降级放行；
  ⑧ 工厂 **不** import LLM/rag 抽象（AST 断言：`memory/importance.py` 无 `core.llm_provider` /
  `core.rag` import）
- [x] B2. 实现：`score_with(llm: Callable[[str], str]) -> ImportanceScorer` + `_PROMPT_TEMPLATE` +
  `_parse_score(text) -> float`；`memory/__init__.py` 导出 `score_with`

## Layer C —— 配置开关 + 组合根接线

- [x] C1. 测试：新建 `tests/test_memory_config.py`（红，照 `tests/test_loop_budget_config.py` 模板）——
  ⑨ `config_specs()` 含 `memory.importance_gate`（单真源）；⑩ `memory:` 段 **不**报「未知配置段」；
  ⑪ 访问器缺省 `False`、yaml/env 可覆写；⑫ `build_runtime` 缺省 ⇒ `_importance_scorer is None`；
  ⑬ `memory.importance_gate: true` ⇒ `_importance_scorer is not None`
- [x] C2. 实现：`configuration/manager.py` —— `ConfigSpec("memory.importance_gate", "--memory-importance-gate",
  "CORE_MEMORY_IMPORTANCE_GATE", False, "memory.importance_gate", EXPOSURE_ADVANCED)` +
  `importance_gate()` 访问器 + `_KNOWN_EXTRA_SECTIONS` 加 `"memory"`；
  `runtime.py` —— `MemoryStore(..., importance_scorer=score_with(_llm_text) if config.importance_gate() else None)`

## Layer D —— 收尾

- [x] D1. 规格 delta：`specs/memory/spec.md`（MODIFIED「写入侧重要度闸门」+ 2 Scenario；既有 6 逐字保留 ⇒ 8）
  —— 已完成
- [x] D2. `doc/01-architecture/adr.md`：**ADR-0172** + 追踪行
- [x] D3. 模块文档：`doc/02-modules/memory.md`（闸门接线 + 豁免面）
- [x] D4. 接口文档：`doc/03-interfaces/memory-interface.md`（`score_with` 契约 + 配置键）
- [x] D5. `doc/04-testing/test-cases.md`：新增 TC 节 + 基线 bump（2125 → N）
- [x] D6. `coding-plan/known-risk.md`：§1 新 **E118** 行 + §3 ADR-0172 局限行
- [x] D7. 四门禁 + `openspec validate <全目录名>` + 手工归档 + `openspec validate --all`
- [x] D8. 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）+ **单次提交**
