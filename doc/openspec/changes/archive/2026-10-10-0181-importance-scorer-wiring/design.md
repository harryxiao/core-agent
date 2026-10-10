# Design: 写入侧重要度闸门的生产接线与内部产物豁免面（change 0181 / ADR-0172 / 台账 E118）

## 背景取证（全部 `file:line` 已核）

| 面 | 现状 | 文件 |
|---|---|---|
| 契约 | `ImportanceScorer = Callable[[MemoryEntry], float]` | `memory/store.py:74` |
| 构造 | `importance_scorer: ImportanceScorer \| None = None`（存 `:182`） | `memory/store.py:173` |
| 闸门 | `write()` 先 `_gate_score` 再落库；<FLOOR 拒收 / [FLOOR,AMBIT) 降 L4 / ≥AMBIT 写回 importance | `memory/store.py:248-277` |
| 打分 | `_gate_score`：UNWIRED→None；抛错/界外→None（降级放行 + 留痕） | `memory/store.py:298-323` |
| 工厂先例 | `summarize_with(llm)` / `extract_with(llm, *, max_facts=)` —— 同一 `llm: str→str` 接缝 | `memory/summarize.py:54-60` / `memory/extract.py:231-251` |
| **接线缺口** | `MemoryStore(...)` **无** `importance_scorer=` 实参 | `runtime.py:383-393` |
| 内部产物来源 | 摘要/中层摘要 `source="compaction"`；压实产物 `source="context"`；关键事实 `source="extraction"` | `store.py:449-453,88-115` / `:731` |

⇒ 闸门一旦接线，内部产物**同过闸门** ⇒ ADR-0168 局限①（误杀）成为真实路径。

## 裁决与理由

### D1 工厂放新模块 `memory/importance.py`，接缝与两先例同形

`score_with(llm)` 与 `summarize_with` / `extract_with` 共享「`llm: Callable[[str], str]`」接缝 ⇒
memory **不 import 任何 LLM 抽象**（ADR-0045 单向），prompt 文本属 memory 域，模型调用由组合根注入。
`_llm_text`（`runtime.py:341`）已是摘要/抽取/补丁三条 DI 接缝的共用闭包 ⇒ 评分复用同一条。

解析：取模型输出中**首个** [0,1] 浮点；无 ⇒ 抛 `ValueError` ⇒ 闸门**降级放行**（既有路径，不新增分支）。
**不**在工厂内 clamp/兜底：越权解析会把「模型没给分」静默成「给了 0 分」而误杀 —— 与
`_gate_score` 的「界外/异常 ⇒ 不评分」口径一致，方向恒为**放行**。

### D2 豁免面按 `source`，与 `_ARCHIVE_SOURCES`/`_PRESERVE_TAGS` 同 idiom

`_GATE_EXEMPT_SOURCES = frozenset({"compaction", "context", "extraction"})` —— 与
`notes/store.py` 的 `_ARCHIVE_SOURCES`、`memory/store.py` 的 `_PRESERVE_TAGS` **同一「模块常量排除面」
惯用法**（判据落稳定字段、单点定义、可单测）。

**为何按 source 而非 kind**：`kind`（episodic/semantic）是**内容分类**，`source` 是**来源命名空间**——
误杀风险来自「**谁**产生了它」（管道派生 vs 有机写入），故判据落 source。**为何**不豁免 `kind="semantic"`：
summary/mid/compaction-fact/keyfact 皆 semantic，但未来若有**有机** semantic 写入（人工/导入）应受评分，
按 source 才能精确豁免「系统管道」而非「语义内容」。

### D3 豁免面**只缩小**评分面，不引入新分支

`write()` 单行改：
```python
score = None if entry.source in _GATE_EXEMPT_SOURCES else self._gate_score(entry)
```
`score is None` 已由既有路径处理为「不评分、不拒收、不降层、不写 importance」（UNWIRED 同款）⇒
豁免条目与 UNWIRED 条目**逐字同路径**。零新增行为分支（P2 最小改动）。

### D4 配置开关缺省关，接线**零扰动**

新键 `memory.importance_gate`（`ConfigSpec`，default=False，ADVANCED，`map_to="memory.importance_gate"`）。
**`_KNOWN_EXTRA_SECTIONS` 不动** —— `_known_sections()`（`manager.py:373-375`）已并入「ConfigSpec 声明段的
`map_to` 前缀」，声明段自动进白名单，故 `memory:` 段不报「未知配置段」（取证：`_build_config`
的 `extra` 收纳所有非结构化段，`manager.py:672-674`）。
访问器 `importance_gate()` 对齐 `history_turns()` 独立访问器纪律；取值归一与 feature flag 同集
（原生布尔 / `true`·`false`·`yes`·`no`·`on`·`off`·`1`·`0`，大小写不敏感；非结构化段不阻断启动，
故不引入校验期拒绝 —— 方向恒为「不开启」）。`runtime.py`：
```python
importance_scorer=score_with(_llm_text) if config.importance_gate() else None,
```
缺省 false ⇒ `None` ⇒ 与变更前逐字一致。

### D5 明确不动的部分

- `_gate_score` / 阈值常量 / 迁移与写回路径**逐字不动**（豁免在**调用点**短路，不进打分器）。
- `summarizer` / `key_fact_extractor` / `summary_promoter` 接线**不动**。
- `evolution`（经 `MemoryBackend.put` 直写）与 `notes`（独立存储）**不**受影响。

## 契约不变量（must-hold，逐条对应测试）

| # | 条件 | 必须成立 |
|---|---|---|
| I1 | scorer 注入 + 条目 `source="compaction"` | 按意向层入库、不降层、`importance` 不变、**无留痕** |
| I2 | scorer 注入 + 条目 `source="loop"` | 拒收（`None`）+ 留痕（豁免面**不**覆盖有机写入） |
| I3 | 注 source∈{`context`,`extraction`} | 同 I1（豁免面三来源齐） |
| I4 | scorer UNWIRED（缺省） | 写入逐字不变（既有 6 用例全绿，零回归） |
| I5 | `score_with` 解析 `"0.8"` | 返回 0.8 |
| I6 | `score_with` 解析无浮点 / 界外 | 抛错 / 返回界外 ⇒ 闸门降级放行（`write` 成功 + 留痕） |
| I7 | 配置缺省 | `importance_gate() is False` ⇒ `runtime` 不注入评分器 |
| I8 | 配置 `true` | `runtime` 注入评分器（可经 `_importance_scorer` 断言） |

## 落点

- `src/core/memory/importance.py`（新）：`score_with` + prompt 构造 + 解析。
- `src/core/memory/store.py`：`_GATE_EXEMPT_SOURCES` + `write()` 一行短路。
- `src/core/memory/__init__.py`：导出 `score_with`。
- `src/core/configuration/manager.py`：`ConfigSpec` + `importance_gate()` + `_KNOWN_EXTRA_SECTIONS` 加 `memory`。
- `src/core/runtime.py`：`memory` 构造加 `importance_scorer=`。
