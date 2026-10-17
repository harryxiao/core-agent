# Tasks 0241

## 1. 规格
- [x] 1.1 `specs/memory/spec.md`：MODIFIED「记忆压实」＋ Scenario；MODIFIED「写入侧重要度闸门」
      （豁免面补 `relation` / `episodic`）＋ Scenario
- [x] 1.2 `specs/loop/spec.md`：MODIFIED「执行循环」（轨迹内容口径改为「除密钥形态脱敏外逐字不变」）
      ＋ Scenario
- [x] 1.3 `specs/evolution/spec.md`：ADDED「进化写回与技能内容的密钥形态脱敏」＋ 3 Scenario

## 2. 测试（先红）
- [x] 2.1 `tests/test_evolution_gate_data.py`：打分器抛异常 ⇒ `freeze`；`run_cycle` ⇒ `frozen`
- [x] 2.2 `tests/test_memory_episodic.py`：低分 scorer 下 `episodic` 仍入 L2、不降层、无评分留痕
- [x] 2.3 `tests/test_memory_summary_promotion.py`（或既有 summary 测试）：摘要落库前脱敏
- [x] 2.4 `tests/test_loop_memory_sequence.py`：轨迹条目写入前脱敏、结构保留
- [x] 2.5 `tests/test_evolution.py`（或 pending/engine 测试）：`dissolve` / `reject` / 技能字段脱敏

## 3. 实现
- [x] 3.1 `evolution/evaluator.py`：`evaluate` 捕获打分异常 ⇒ `_frozen`；docstring
- [x] 3.2 `memory/store.py`：`_GATE_EXEMPT_SOURCES` 加 `episodic`；注释修正；`_commit_summary` 脱敏
- [x] 3.3 `loop/default.py`：轨迹条目整条 `redact_secrets`；docstring
- [x] 3.4 `evolution/engine.py`：`dissolve` / `reject` / `_crystallize_skill` / `_crystallize_plugin` 脱敏

## 4. 文档
- [x] 4.1 ADR-0229
- [x] 4.2 `doc/03-interfaces/evolution-interface.md`（如有涉及）
- [x] 4.3 memory / loop 模块文档（如有涉及）

## 5. 收口
- [x] 5.1 四门禁：ruff check / ruff format --check / pyright（无参）/ pytest
- [x] 5.2 `openspec validate --all`
- [x] 5.3 归档（`/tmp/openspec_archive.py`，断言 0 Requirement / 0 Scenario 丢失）
- [x] 5.4 台账 `known-risk.md` E176、`test-cases.md` §152
- [x] 5.5 单次提交（含 `Co-Authored-By`）
