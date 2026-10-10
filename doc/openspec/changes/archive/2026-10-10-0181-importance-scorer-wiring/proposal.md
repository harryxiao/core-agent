# Proposal: 写入侧重要度闸门的生产接线与内部产物豁免面

> 规格：`memory`（**MODIFIED × 1**）

## Why

用户 2026-10-10 追问「记忆模块彻底完善了吗」，逐行取证（探索代理 + 台账复核）确认：

1. **built-but-unwired**：写入侧重要度闸门的**契约与实现齐备** —— `ImportanceScorer` 契约
   （`src/core/memory/store.py:74`）、构造形参（`:173`）、闸门（`write()` `:248-277` /
   `_gate_score()` `:298-323`）全在，但 `src/core/runtime.py:383-393` **未接线** ⇒ 生产环境里该闸门
   永远走「UNWIRED ⇒ 不评分」路径。同 `summarizer` / `key_fact_extractor` 早已经组合根注入相对照，
   这是**唯一**漏接的记忆接缝。
2. **误杀风险（ADR-0168 局限①）**：闸门对**所有**经 `write()` 的条目评分 —— 而**内部派生产物**
   （会话摘要 `source="compaction"`、中层摘要 `source="compaction"`、压实产物 `source="context"`、
   结构化关键事实 `source="extraction"`）**同样过闸门**。一旦注入 LLM 评分器，一条**由系统管道从已准入
   材料派生**的摘要就可能被判「低价值」而拒收/降层 —— 派生结论凭空丢失。

⇒ 本 change：**补接**生产接线，并同时在闸门内加**内部派生产物豁免面**，使接线**不引入**局限① 的误杀。

**用户已裁决**（AskUserQuestion，2026-10-10）：E97 全做、诊断桥纳入 —— 本条属「built-but-unwired」
组，方向为**接线 + 豁免面**（豁免面是本条自定的最小护栏，不涉用户岔口）。

## What Changes

1. **评分器工厂**（新模块 `src/core/memory/importance.py`）：新增
   `score_with(llm: Callable[[str], str]) -> ImportanceScorer` —— 与 `summarize_with`
   （`summarize.py:54-60`）/ `extract_with`（`extract.py:231-251`）**同一 llm 接缝**，把
   「prompt → 文本」的模型调用适配为闸门的评分契约。解析失败 / 界外 ⇒ 由闸门既有路径**降级放行**。
2. **内部产物豁免面**（`src/core/memory/store.py`）：新增模块常量
   `_GATE_EXEMPT_SOURCES = frozenset({"compaction", "context", "extraction"})`；`write()` 中
   `score = None if entry.source in _GATE_EXEMPT_SOURCES else self._gate_score(entry)` —— 派生/内部
   产物**不经评分**，写入与 UNWIRED 逐字一致。
3. **配置开关 + 组合根接线**：新配置键 `memory.importance_gate`（bool，**缺省 false** ⇒ 行为逐字不变），
   `ConfigurationManager.importance_gate()` 访问器；`runtime.py` 在 true 时注入
   `importance_scorer=score_with(_llm_text)`。
4. **loop / context / notes 零改动**：豁免面与接线**只**落在 memory 与组合根。

## Impact

- **specs**：`memory/spec.md`——**MODIFIED**「写入侧重要度闸门」（追加「内部/派生产物豁免」条款 +
   2 Scenario：豁免面不经评分 / 非豁免来源仍受评分）。既有 6 Scenario 逐字保留 ⇒ 8。
  `loop` / `context` / `notes` / `configuration` **不动**（契约无变化；配置键是接线细节，归 design）。
- **src**：`memory/importance.py`（新）、`memory/store.py`（常量 + 一行闸门短路）、
  `memory/__init__.py`（导出 `score_with`）、`configuration/manager.py`（ConfigSpec + 访问器 +
  已知段白名单加 `memory`）、`runtime.py`（接线）。**无新增第三方依赖**。
- **风险**：低。缺省 false ⇒ **行为逐字不变**（零扰动回归）；豁免面**只**缩小评分面（不扩大）；
  LLM 评分器仅在显式开启时构造，且每条目一次模型调用受既有 `_MAX_SCORED_PER_COMPACT` 口径约束。
- **已知局限**（详见 `design.md` / `coding-plan/known-risk.md`）：豁免面按 `source` 判据 —— 新增派生
  来源须同步登记（漏登记 ⇔ 该来源被评分）；评分器为逐条目 LLM 调用（开启后写入延迟随条目数上升）；
  `evolution` 侧经 `MemoryBackend.put` 直写、**不**过本闸门（不受豁免面影响，亦不被评分）。

## Non-goals

- 评分**批量/缓存**优化（一次压实最多 `_MAX_SCORED_PER_COMPACT`=20 条打分原语，本 change 不新增批量面）。
- 评分器选型/本地模型（评分 = 一次 LLM 文本调用，承 `_llm_text` 同一接缝）。
- `evolution` / `notes` 写入路径的闸门化（各走 `MemoryBackend.put` / 独立存储）。
