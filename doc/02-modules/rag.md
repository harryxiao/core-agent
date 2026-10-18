# 模块设计：检索增强生成（Retrieval-Augmented Generation, RAG）

> 对应规格：`doc/openspec/specs/rag/spec.md` ｜ 接口：`doc/03-interfaces/rag-interface.md`
> 定位：**L3 检索底座**，以本地向量库做知识文档的语义检索，弥补 LLM 训练截止 / 私有领域知识缺口。

---

## 1. 模块定位

LLM 存在固有知识缺口：训练截止、私有/领域知识缺失。RAG（检索增强生成）让 Core-Agent 通过本地向量库语义检索知识文档（产品文档、领域知识、内部规范等），把最相关片段作为上下文注入生成链路，使回答基于本地知识库而非仅凭模型参数。

职责边界：RAG 管「知识文档」的**语义检索**，codebase-memory-mcp 管「代码结构」的**结构化理解**，二者正交互补、同时引入。

### 1.1 定位：辅助本地知识库，**不**注入主链路（change `0156` / ADR-0148 / 路线图 G5）

**现状即答案**：RAG 是**辅助的本地知识库查询面** —— 知识文档的**按需**语义检索，经 CLI
`rag ingest|search|ask` **一次性**驱动，**不**参与 loop **每轮**上下文装配（不占固定窗口、不进系统提示）。

- **三面各归其位**：`memory` = 经验轨迹 + **关键事实**（结构实体，change `0155`）；`notes` = 主题文档
  （canonical 真相层）；**`rag`** = 外部知识文档（分块 + 向量，按需 top-k）。互不越界。
- **不注入 loop**（承 ADR-0097 ⑥）：主链路与三面兄弟（`loop` / `context` / `memory` / `notes`）**不得**
  `import core.rag`（可执行守护 `test_architecture.py::test_rag_not_imported_by_reference_chain`）；
  `core.rag` 仅由组合根（`runtime.rag`）与 CLI（`entry` 的 `rag` 命令族）引用。
- **不做结构化实体抽取 / 跨会话实体**：该面归 `memory` 关键事实（change `0155` / ADR-0147）。
- **门槛**：若要令 RAG 参与 loop 上下文，**须先改 ADR-0097 ⑥**（属特性，牵动 context 预算与 prompt 装配）。

---

## 2. 内部组成

```
RAG（L3）
├── VectorStore        向量存储：stdlib sqlite3 嵌入式向量 CRUD + 索引（落盘 $CORE_STATE_DIR）
├── IngestionPipeline  摄取管线：文档导入 → 分块 → embedding → 索引（增量更新）
├── Embedder           embedding：离线 HashEmbedder 降级基线 / LLMEmbedder 语义（llm-provider）
├── Retriever          语义检索：查询 embedding → 向量相似度 top-k
├── RagGenerator       生成融合：检索片段注入 → llm-provider 生成（无结果降级）
└── RagService         主链路门面：组合根装配（runtime.rag）+ CLI `rag ingest|search|ask`

> **接线状态（change 0104）**：上述链路此前**无生产调用方**（死代码）——组合根现装配
> `RagService` 挂 `runtime.rag`，CLI 三子命令驱动同一门面，一次 `ingest` 的成果在后续进程
> 的 `search` / `ask` 中可见（落盘索引为真源）。

---

## 3. 关键设计

### 3.1 嵌入式零服务存储

- 向量库默认取 **stdlib `sqlite3`**（`SqliteVectorStore`）：嵌入式、零服务、**零三方依赖**（`sqlite-vec`
  是需另行安装的扩展，离线不可得）；表结构 = `chunks`（块 + 向量 BLOB）/ `documents`（内容指纹）/
  `meta`（`dim` 向量维度），落盘 `$CORE_STATE_DIR/rag-index.db` ⇒ 跨进程复用。
- 契合「无特权核心」原则，不引入特权服务；`VectorStore` 负责向量 CRUD 与索引，落盘即持久化。
- `sqlite-vec` / LanceDB（同为嵌入式、多模态更强）作为经同一抽象替换的扩展点——若规模或多模态需求
  到位再评估，不属本期范围。
- **订正**：本文与规格此前称「与 Core-Agent 既有 SQLite 生态统一」——全仓 `src/` 无任何 sqlite 使用，
  该前提不成立（change 0104 已订正规格与本文）。
- **读侧访问器（change `0210`／ADR-0200）**：`VectorStore` 另暴露 `document_ids()`（已索引文档 id，
  升序）与 `chunk_texts(doc_id)`（某文档块文本，按**块序号**升序 ⇒ 定长切片的块可**无损拼回原文**）
  供**目录面**（信息地图）消费。二者为 **fail-soft 缺省**（基类返 `[]`、**非抽象**）⇒ 既有第三方
  `VectorStore` 实现**零改动**即静默 no-op、契约不破坏（与 `0209` 重试白名单的 fail-closed 方向
  刻意相反：此处失败语义是「少一块增益能力」而非「多做一次副作用」）。

### 3.2 摄取与增量更新

- 摄取管线：`IngestionPipeline.ingest` 将知识文档 **分块 → 逐块 embedding → 写入向量索引**。
- 增量更新：`refresh` 按 `content_hash` 检测源文档变更，不一致则重建受影响块；内容指纹**随索引落盘**（`documents` 表）⇒ 判定跨进程成立（CLI 每次调用都是新进程）；重建窗口期该文档检索**降级旧索引**，不阻塞查询。
- 摄取/重建失败降级：记录失败、可重试，不阻断主流程。

### 3.3 embedding 后端选择与降级

- 默认 **`HashEmbedder`**：字符 n-gram 哈希生成确定性向量，**零三方依赖、零外呼**（离线降级基线；
  有效 embedding 模型为空时组合根选用，CLI 打印降级提示）。依据 memory 既有裁决「HashEmbedder
  是降级基线不完善，语义走 `LLMEmbedder`，不引入本地语义模型」（不引 sentence-transformers）。
- 配 `llm.embedding_model`，或端点命中内置表且 `llm.embedding_auto` 开启（change `0271` /
  ADR-0261）⇒ **`LLMEmbedder`** 经 llm-provider 归一化入口调远端 embedding 模型，
  检索与调用方零改动。**维度随后端变化**：索引记录 `dim`，不一致即 `INDEX_CORRUPT` 并提示重建。

### 3.4 语义检索

- `Retriever.search`：查询语句 embedding → 向量相似度 **top-k** 检索，返回片段 + 相关度得分（降序），供后续裁剪排序。

### 3.5 生成融合与降级

- `RagGenerator.generate`：检索片段经 **context 装配器按预算裁剪**后注入提示词 → llm-provider 生成。
- 检索无结果时**降级纯 LLM 生成**，不阻断流程。

### 3.6 摄取的**可选**摘要（`--summarize`，change `0213`／ADR-0203／台账 E150）

`rag ingest <path> --doc-id ID` 加 `--summarize` 旗：摄取**成功后**，入口侧把**全文**交一次模型调用
产摘要、落 canonical 结论笔记（`notes.rag`）。**显式旗即 opt-in** —— 无配置键、无环境行为，不带旗
⇒ 既有摄取行为**逐字不变**、**零笔记**。

**本包零改动**：摘要调用在 `entry._rag_ingest`（复刻组合根 `_llm_text` 4 行接缝）、落盘在
`entry._doc_summary_note`（调**公开** `NoteStore.update`）—— rag 包**不感知 notes**，守 **RAG 三面
边界**（ADR-0097⑥ / ADR-0148；`entry` 是 `test_rag_not_imported_by_reference_chain` 明列的 rag
例外）。摘要是**结论层**，**不**回写 chunk 面（避免摘要与原文在检索语料里重复入场）。

**失败不阻断**：摘要（模型调用 / 落盘）失败**不**回退摄取、**不**改退出码（摄取已是既成事实），
告警落 stderr 且**只报 `doc_id`**（绝不回显正文）。

---

## 4. 与 codebase-memory-mcp 的分工

| 维度 | RAG | codebase-memory-mcp |
|---|---|---|
| 对象 | 知识文档（产品/领域/规范） | 代码结构（symbol / 依赖 / 调用图） |
| 手段 | 向量库 + embedding 语义相似度 | AST + LSP 结构化理解（确定性） |
| 结果 | top-k 片段 + 相关度得分 | 符号 / 依赖 / 调用链 |

文档语义检索走 RAG，代码结构理解走 codebase-memory-mcp，一次查询中两者各归其位、互不重叠。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| embedding 生成失败 | 返回 `EMBEDDING_FAILED`，该文档检索降级旧索引或纯 LLM |
| 向量索引损坏 / 维度不一致 | 返回 `INDEX_CORRUPT`，提示重建索引（换 embedding 后端后沿用旧索引） |
| 增量重建失败 | 返回 `REBUILD_FAILED`，降级旧索引，可重试 |
| 检索无结果 | 返回空列表，降级纯 LLM 生成，不阻断 |
| 生成器未装配（服务层无 llm-provider 通路） | 返回 `GENERATION_UNAVAILABLE`，不返回空答案（fail-closed） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/rag-interface.md`
- 规格：`doc/openspec/specs/rag/spec.md`
- 架构：`doc/11-rag/rag-architecture.md`（ADR-0025、数据流）
- 变更：`doc/openspec/changes/0010-rag/`；**主链路接线**：`doc/openspec/changes/2026-10-05-0104-rag-mainline-wiring/`（ADR-0097）
- 上游：`doc/02-modules/llm-provider.md`（embedding 归一化入口 + 生成）、`doc/02-modules/context.md`（上下文装配裁剪）
