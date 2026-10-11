# Design 0210 — rag 文档进信息地图

## D1 为什么是「生产侧接线」而非改装配器

目录面（`DynamicAssembler._gather_pointers`）**早已在消费** `InfoMap.documents()`：它逐文档
`lookup(doc_id, task)` 取任务匹配指针。缺的不是「读」而是「**谁往地图里放文档**」——
生产只有 Core.md 一处（`runtime.py:713-721`）。故本 change **零改动** `context/` 包内代码，
只在组合根补第二条来源。这也是 **ADR-0097⑥**（rag 参与 loop 上下文的**唯一合法路径**是组合根
注入）下的正确落点：`tests/test_architecture.py:326-347` 守护三面边界，`context` 不 import `rag`、
`rag` 不 import `context`，桥只能由组合根搭。

## D2 `index` 而非 `register`

`InfoMap` 两个入口语义不同：`index` = 原文 **＋ 目录索引**（一阶）；`register` = 仅原文
（**索引不可用**态，`lookup` 走二阶线性扫描兜底）。要兑现规格「千页级业务文档 → 指针 → 按需取详情」，
必须**有目录** ⇒ 用 `index`。用 `register` 也能"工作"（线性扫描逐段命中）但**丢目录层**，
且每步对全文做受控扫描（段数上界 20 ⇒ 千页文档只看到头 20 段），语义上退化为兜底路径。

## D3 块文本按**数字后缀**序拼回

`IngestionPipeline._build_chunks`（`ingest.py:52-64`）把原文按**定长** `chunk_size` 切片，
`chunk_id = f"{doc_id}#{i}"`（`i` = `enumerate` 下标）。因此：
- **按块序号升序拼接 = 无损还原原文**（定长切片无重叠无遗漏）；
- 按 `chunk_id` **字典序**拼则踩 `#10 < #2` 陷阱（`"1" < "2"` 逐字符比较）⇒ 错序。

故 `chunk_texts` 内的排序键 = **数字后缀** `int(chunk_id.rpartition("#")[2])`；解析失败者排最后并
按 `chunk_id` 定序（确定性，不因脏 id 抛错）。`document_ids()` 亦 **`ORDER BY doc_id`** ⇒ 上限截断
`[:16]` 是**确定性**的（否则 DB 行序不定，「谁进谁不进」不可测）。

## D4 fail-soft 访问器为何**非抽象**

`VectorStore` 是**对外契约**（规格「存储与 Embedding 依赖注入隔离」：第三方实现可替换 sqlite）。
加抽象方法 = **破坏性变更**（既有第三方实现一 import 就 `TypeError`）。故两访问器给
**基类缺省实现返 `[]`**（非 `abstractmethod`）⇒ 既有实现**零改动**即静默 no-op：目录面拿不到
rag 文档，但**不炸**。这正是「增益面」的正确降级方向 —— 与 `reversible` 挂钩的重试白名单
（`0209` fail-closed）**方向相反**，因为此处的失败语义是「少一块能力」而非「多做一次副作用」。

## D5 上限 `_RAG_INFO_MAP_MAX_DOCS = 16` 是**硬约束**

目录层指针块**不受预算裁剪**：`_gather_pointers` 对每个文档取 `lookup(...)[:_MAX_POINTERS_PER_DOC]`
—— 上界是**每文档**条数，**没有**跨文档总量上界。N 个 rag 文档 ⇒ 每步注入 O(N) 行。若不设上限，
一个 `rag ingest` 了 500 份文档的库会让**每一次** loop 感知阶段都注入数千行指针。

替代方案「给 `BudgetManager` 加按块记账」被**否决**（计划期裁决）：改预算器影响面远超本缺口，
且既有 `plan_blocks` 纪律（`0201`）刚立，不宜同批再动。以**文档数上限**换有界性，代价是
「超 16 份文档时只看到前 16 份（按 `doc_id` 序）」—— 记入 ADR 已知局限。

> 16 的取值：与 `_MAX_POINTERS_PER_DOC`（每文档条数上界）同量级思路，保证**最坏情形**注入行数
> 与「一份千页文档」同阶（16 文档 × 每文档上界），而非无界。

## D6 跳过 `core-profile`

Core.md 项目信息段已由 `profile.context` 分支 `index(_CORE_PROFILE_DOC_ID, ...)` 从**真源**
（Core.md 原文，带 `# {section}` 头）建索引。rag 库里若存在同名 `doc_id` 的摄取副本，再 `index`
一次会用**块拼回文本**覆盖真源（丢 `#` 标题 ⇒ 建不出 heading 指针）。故**显式跳过**
`_CORE_PROFILE_DOC_ID`（`runtime.py:386`）。

## D7 逐文档降级不炸

`_index_rag_docs` 对每个文档独立 `try/except Exception: continue`：单文档 `chunk_texts` 读到
坏行（`INDEX_CORRUPT` / sqlite 错误）**只跳过它**。理由：地图是**增益**面，装配必须成功 ——
一份坏文档不得让整个 runtime 起不来（同 `0206` 的「坏行跳过」精神，但此处**连告警都不发**，
因为该路径每次装配都会走，逐次告警会刷屏；坏档的可见性由 rag 自身的检索面错误码承担）。
`document_ids()` 本身失败亦返空（整体降级）。

## D8 已知局限（记入 ADR）

1. **CLI 摄取 → 运行中进程不可见**：InfoMap 是**进程内**对象，`rag ingest`（另一进程）写的是
   **落盘向量库**；运行中的 serve 要**重启**才把新档建进地图（同 `skills.json` 先例）。
2. **`fetch_detail` 只回 heading/summary**：既有契约（`assembler.py:101-111` 返回
   `pointers[0].summary`），非本缺陷 —— 建在块拼回文本上的指针 summary 即 heading 文本。
3. **全语料进内存**：`InfoMap.index` 把原文缓存于 `self._docs` ⇒ 16 份文档的全文常驻内存
   （上限即兜）。大库场景需换增量/按需装载，不在本批。
