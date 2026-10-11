# Rag Specification Delta — rag 文档进信息地图（change 0210）

## MODIFIED Requirements

### Requirement: 本地向量库存储
系统 SHALL 以本地嵌入式零服务向量库存储文档向量与索引：零服务、**零三方依赖**，无需独立 daemon 或
外部向量数据库；索引落盘于 `$CORE_STATE_DIR`，**跨进程复用**（一次 `ingest` 的成果在后续进程的检索中
可见）。**默认实现**为 stdlib `sqlite3` 嵌入式库（向量以 BLOB 存储、相似度在进程内计算）；`sqlite-vec`
等向量扩展在可得时经同一 `VectorStore` 抽象替换，调用方零改动。索引 SHALL 记录**向量维度**：
写入或检索的向量维度与索引不一致时（如更换 embedding 后端后沿用旧索引）SHALL 以**结构化错误**
拒绝并提示**重建索引**，SHALL NOT 静默截断比较（静默降级会产出无意义的相似度）。索引 SHALL 同时记录各文档的
`content_hash`（与向量同落盘），使**后续进程**的重复摄取按内容判定为**无变更**、不重复重建。
`VectorStore` SHALL 另暴露两个**读侧访问器**供目录面消费：文档 id 列表与某文档的**块文本序列**。
二者 SHALL 为**fail-soft 缺省实现**（基类返空列表、非抽象）⇒ 既有第三方实现**零改动**即静默
no-op、契约不破坏；实现方若提供，块文本 SHALL 按**块序号升序**返回（使定长切片的块可无损拼回原文）。

#### Scenario: 嵌入式零服务存储
- **GIVEN** 知识文档完成 embedding
- **WHEN** 向量写入向量库
- **THEN** 向量落盘于本地嵌入式向量库（默认 stdlib `sqlite3`），无需启动独立服务或外部向量数据库

#### Scenario: 索引跨进程复用
- **GIVEN** 一次 `ingest` 已把文档向量写入落盘索引
- **WHEN** 后续**另一个进程**装载同一索引并检索
- **THEN** 命中该文档的块（落盘索引为检索真源，不依赖进程内内存）

#### Scenario: 向量维度不一致时拒绝
- **GIVEN** 索引已按维度 N 建立（如缺省 HashEmbedder 的 128 维）
- **WHEN** 以维度 M（M≠N，如更换 embedding 后端）写入或检索
- **THEN** 以结构化错误（`INDEX_CORRUPT`）拒绝并提示重建索引，不产出错误相似度

#### Scenario: 块文本按序号拼回原文
- **GIVEN** 一份长文档经 `ingest` 切成超过 10 个块（块 id 形如 `doc#0…#12`）
- **WHEN** 经访问器取该文档的块文本并按序拼接
- **THEN** 拼接结果**等于原文**（按块序号升序，而非 `chunk_id` 字典序 —— `#10 < #2` 是错序）
