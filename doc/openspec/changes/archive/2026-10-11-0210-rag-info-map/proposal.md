# Proposal 0210 — rag 文档进信息地图（InfoMap×rag 接线）

## 为什么

`InfoMap.register` / `index`（`context/info_map.py:44/:55`）**生产只在组合根接了一处**：Core.md
项目信息段（`runtime.py:713-721`，change `0140` / 账本 E77）。context spec「信息地图」的
**千页级业务文档**场景（`context/spec.md:71`）从未兑现 —— 而 rag 摄取（`ingest.py:52-64`）恰好
把整份文档切成块写入落盘向量库，**原文就在库里**，只是没有任何路径把它交给信息地图。

这是六能力走查中「有规格无接线」死代码的一支：**rag 检索面（`search`/`ask`）通了，目录面（指针块）
不通** —— 模型只能靠 top-k 相似度撞片段，无法先看目录再按需取详情。

## 做什么

- **`VectorStore` 补两个 fail-soft 访问器**（`rag/vector_store.py`）：`document_ids()` /
  `chunk_texts(doc_id)`。**缺省实现返 `[]`**（非 `abstractmethod`）⇒ 第三方 `VectorStore` 实现
  **零改动即静默 no-op**，不破坏既有契约（守「存储与 Embedding 依赖注入隔离」Requirement）。
- **`SqliteVectorStore` 实现之**：块文本按**块序号升序**拼回原文 —— `_build_chunks` 是定长切片
  （`chunk_id = f"{doc_id}#{i}"`，`i` 为 `enumerate` 下标）⇒ 数字序拼接**无损还原**原文；
  按 `chunk_id` 的**字典序**拼会踩 `#10 < #2` 陷阱（错序），故按**数字后缀**排序。
- **组合根接线**（`runtime.py`）：`context.rag_info_map` 旗开时，装配期把 rag 库文档
  `info_map.index(doc_id, "".join(chunk_texts(doc_id)))` —— **`index` 而非 `register`**（`index`
  产出真目录指针；`register` 只缓存原文 ⇒ 走线性扫描兜底，仍可行但丢目录层）。
  **文档数上限 `_RAG_INFO_MAP_MAX_DOCS = 16`**：目录层指针块**不受预算裁剪**
  （`context/assembler.py:_gather_pointers` 逐文档注入、只按**每文档**条数设上界）⇒ 文档数无界
  即每步无界注入，必须有总量上限。跳过 `core-profile`（已由 `profile.context` 分支以**真源**
  建索引，不重复）。逐文档**降级不炸**：单文档读取失败只跳过它（地图是**增益**面，不得因一档
  失败阻断装配）。
- **配置**：单键 `context.rag_info_map`（bool，**缺省 `False` = 不进地图**）；`context` 为
  **非结构化段**（非法取值不阻断启动，集合外取值归一为**关闭**，方向恒为「不进地图」）。

## 不做（边界）

- **不动 `DynamicAssembler` / `_gather_pointers`**：目录层已在消费 `documents()`，接线只在
  **生产侧**（谁往地图里放文档）。
- **不给 `BudgetManager` 加按块记账**：以**文档数上限**替代（同 `0210` 计划期裁决；改预算器
  影响面远超本缺口）。
- **不让 rag 摄取**（CLI `rag ingest`）**反向触达运行中的 serve**：InfoMap 是**进程内**对象，
  CLI 摄取后运行中的进程**重启才可见**（同 `skills.json` 先例）。
