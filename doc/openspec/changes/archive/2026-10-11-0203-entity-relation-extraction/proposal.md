# Proposal 0203 — 实体关系抽取（relations）

## 为什么

外部蓝图（`memory-4-layer-architecture.md` §2）的语义维要求「**实体 — 关系** 结构化沉淀」。
本仓现状：只有**扁平**的 `keyfact.<slug>`（`_write_key_fact`，`content = "<entity>: <value>"`）
—— 有**实体**、无**边**；全仓 `relation` / `edge` / `triple` / `graph` 对 `MemoryEntry` **零命中**，
`MemoryBackend` 只有 `get/put/search/list_index/delete`、`IndexEntry` 是扁平列表。
⇒ 这是本批（Phase 38）**唯一的能力级缺口**，其余三条是口径 / 配比 / 结构层。

## 做什么

1. `Relation(head, predicate, tail)`（frozen dataclass，**独立类型**，不给 `KeyFact` 加字段）+
   `RelationExtractor` 契约 + `RELATION_PREDICATES`（**中英双语闭合白名单**，归一化到规范英文谓词）
   + `build_relation_prompt` / `parse_relations` / `scrub_relation` / `extract_relations_with`
   / `relation_cap`（**别名到 `key_fact_cap`**），全部落在 `src/core/memory/extract.py`。
2. `MemoryStore(relation_extractor=…)` —— **独立 DI 接缝**，缺省 **UNWIRED**（不开新写入路径，
   复用 `write`）；`_extract_relations` / `_plan_relations` / `_write_relation`。
3. 落库形态**完全复用 `_write_key_fact` 的形状**：`id="relation.<h>--<p>--<t>"`、`source="relation"`、
   `kind="semantic"`、`session_id=""`、`trace_id="compaction.<key>"` ⇒ 同 `id` 幂等覆盖、
   `_GATE_EXEMPT_SOURCES` 豁免（补 `"relation"`）、随 `compaction.<key>` 回滚**一并撤销**（免费）。
4. 配置 `memory.relation_extract`（缺省 **`False`**）+ 组合根接线（与 `key_fact_extractor` 同接缝
   `_llm_text`）。
5. **注入面复用既有「相关事实」块**（`exclude_fact_sources=("compaction",)` 自动检索 `source="relation"`
   的 L2 条目 ⇒ 零管线改动、**不加第 11 个提示词块**）。

## 关键决策（逐条有理由，详见 design.md / ADR-0193）

- **不做知识图谱层**：不新增 `MemoryBackend` 方法、不加遍历/查询 API、不加图存储、不动 `IndexEntry`
  —— 那是**后端接口变更 + 迁移成本**，而当前**零消费者**。关系以**普通 L2 条目 + 标签约定**承载。
- **谓词闭合（用户裁决：中英双语白名单）**：谓词若开放，则（a）「图」不可遍历、不可靠查询；
  （b）成为**第四个无界自由文本字段** —— 新的密钥携带面；（c）不可有界 ⇒ 幂等去重的基数失控。
  双语表是「可用」与「有界」的折中；不在表内 ⇒ **丢弃并留痕**（**这正是预期的可观测信号**）。
- **`:ref` 逃生口的有意缺失**：关键事实可给 `coeffect:<名称>` 引用；**关系没有可引用之物**
  ⇒ 本条与「结构化实体抽取」是**有意不对称**（写入 ADR）。
- **密钥判据一处定义**：复用 `extract.looks_like_secret` / `redact_secrets` / `slug_entity`
  （沿 `loop/default.py` 复用先例）。**留痕中的实体名/谓词名一律先 `redact_secrets`** ——
  head 本身可能就是密钥，直接回显即泄漏。
- **独立接缝，不并入 keyfact**：合并会改关键事实的 prompt 字节、打掉 `0155` 的提示词用例。

## 不改什么

- 关键事实的 `id` / `content` / `tags` / prompt 字节**逐字不变**（新增是**加法**）。
- `MemoryStore.read` 的检索语义、`_episodic_groups` 的材料判据、`MemoryBackend` 接口**均不动**。
- **不**给 `ContextPack` / `BudgetManager._measure` 加按块记账；**不加**第 11 个提示词块。

## 规格影响

`memory` **ADDED** 一条要求「实体关系抽取（relations）」。既有 14 条 Requirement **逐字保留**
（不做 MODIFIED）。

## 风险

- **自由文本面扩大**（head / tail 是两个新的模型生成字段）⇒ 脱敏 fail-closed（任一侧密钥形状即整条
  丢弃）+ 长度有界（`_MAX_FACT_CHARS` / `_MAX_MEMORY_ENTRY`）。
- **长 `id`**：3 × `slug(48)` ≈ 105–150 字符 ⇒ 加一条 `FileBackend` 往返 sanity 锚（id 是 JSONL
  的**字段**、非文件名 ⇒ 无路径长度约束，但须**断言**而非假设）。
- **双语白名单上线初期在长尾表达上 drop** ⇒ 忠实登记为局限 + 可观测（warn 分别报「未知谓词」）。
- **每次压实多一次模型调用**（2× 抽取延迟）⇒ 压实是冷路径，接受。
