# 0155 · 结构化实体抽取（关键事实）—— 记忆三面路线图 G4

## 背景与动机

账本 **E92**（`coding-plan/known-risk.md` §1）：外部参考件 `Agent-Memory.md` 的 M4「结构化信息并行抽取」
提出四类实体 Schema（`user_preferences` / `project_constraints` / `completed_tasks` / `key_facts`），
本仓当前只有 `MemoryEntry.kind ∈ {episodic, semantic}` + `tags`，无结构化实体面。

**落地红线（E92 已登记）**：参考 Schema 的示例把**密钥明文**写进长期记忆
（`Agent-Memory.md:35` `{"entity": "测试环境API Key", "value": "sk-xxxxxxxxx"}`），与本仓红线
「**密钥只引用不读取、绝不进日志/记忆**」**直接冲突**。

**实体归属裁决**（路线图 G4 的开放问题，本次由用户拍板）：四类中**只取 `key_facts`**。其余三类
各有**既有归属**，不重复建面 —— `project_constraints` → `notes` 常驻笔记（**操作者显式**置的
任务级硬约束锚，0154）；`completed_tasks` → `notes.observe_turn`（任务后写回主题文档）；
`user_preferences` → L0 Core Profile（用户**自述**人格）。故本 change 的价值**不在覆盖面**，而在
「**自动抽取的、可检索的关键事实**」这一维 + **把参考 Schema 的密钥红线防守做成真代码**。

## 变更内容

`memory` 规格 **ADDED**「结构化实体抽取（关键事实）」：

1. **注入面**：`MemoryStore(..., key_fact_extractor=...)`，契约
   `KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`（缺省 UNWIRED）。新增
   `src/core/memory/extract.py`：`KeyFact` 数据类 + `build_extract_prompt` / `parse_key_facts` /
   `extract_with(llm)` 适配器（照 `summarize.py` 先例 —— prompt 文本属 memory 域，memory 不 import LLM）。
2. **落库形态**：`id="keyfact.<slug>"`（同实体至多一条、覆盖式不增长）、`kind="semantic"`、
   `source="extraction"`、`trace_id="compaction.<sid>"`（与压实一并可撤销）、
   `tags=["key_fact", "entity:<slug>", ("ref:<ref>")?]`、`content="<entity>: <value>"`。
3. **触发点**：`_summarize_sessions` 于 `_commit_summary` / `_deliver_promotion` **之后**，对**同一批**
   被聚合的 episodic 条目抽取 ⇒ 复用同一价值门控与同一 trace。

## 设计原则

- **信任边界在 store，不在注入方**：脱敏由 memory 侧对**每一条**抽取结果**无条件**执行
  —— 抽取器（组合根注入的模型调用）**不构成**信任边界。
- **fail-closed / over-redact**：拿不准即多脱敏；裸密钥**无可用引用** ⇒ **整条丢弃**（记不住引用
  就不记），并留痕。方向永远是安全侧。
- **引用式**：`ref` 形如 `coeffect:<名称>`，取值在使用时经 `CoeffectResolver` 注入 —— 记忆里
  只留**名字**，从不留**值**。
- **零回归**：抽取器 UNWIRED（缺省）⇒ 压实行为逐字不变；`extract.py` 新增模块，既有文件不改语义。
- **零新依赖**：仅用标准库 `re` / `json`；**不引**向量库 / 三方抽取库。

## 非目标（明确不做）

- **不做**其余三类实体（偏好 / 工程约束 / 完成任务的自动抽取）—— 归属见上「实体归属裁决」。
- **不落** `notes`：`key_facts` 是**可检索的事实切片**，不是主题文档；`notes` 是 canonical 真相层
  （主题文档）。二者分工不变。
- **不改** `read` / 排名 / 预算 / 压缩口径；**不加** CLI（关键事实是普通 semantic 条目，经既有
  `read` / `audit` 面可见；`memory maintain` 即触发面）。
- **不做**输入侧（episodic 事件文本）的密钥过滤 —— 该面承既有摘要路径同口径，**不在本 change 扩面**。
- **不引**本地语义模型（承 `rag-offline-embedder-decision`）。

## 影响面

| 文件 | 改动 |
|---|---|
| `src/core/memory/extract.py` | **新增**：`KeyFact` / 脱敏 `scrub_key_fact` / prompt / 解析 / 适配器 |
| `src/core/memory/store.py` | `key_fact_extractor` 注入面 + `_extract_key_facts()` |
| `src/core/memory/__init__.py` | 导出 |
| `src/core/runtime.py` | 组合根接线 `extract_with(_llm_text)` |
| `doc/02-modules/memory.md` / `doc/03-interfaces/memory-interface.md` / `doc/04-testing/test-cases.md` | 同步 |
| `coding-plan/known-risk.md` | E92 → **已修**；§3 加 ADR-0147 局限行 |

## 风险

- **脱敏是启发式**（前缀族 + 长随机串 + 赋值式），**不能**保证穷尽未知密钥格式 ⇒ 方向取
  over-redact（安全侧），并要求「拿不准即引用/丢弃」。局限在 ADR-0147 明记。
- **误伤**：正常长标识符可能被脱敏（如长哈希 id）⇒ 可接受（安全侧），且 `ref` 在场时取值本就
  应脱敏。
- **抽取质量**依赖注入的模型与 prompt；`parse_key_facts` 不可解析即**不抽取**（宁缺勿滥）。
