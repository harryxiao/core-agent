# Context Specification Delta — rag 文档进信息地图（change 0210）

## MODIFIED Requirements

### Requirement: 信息地图
系统 SHALL 把长文档转化为轻量化目录索引，模型按需跳转获取细节，不把全文塞入窗口。
地图的**文档来源** SHALL 至少覆盖：项目信息段（Core.md，装配期从真源建索引）与 —— 旗开时 ——
**rag 库已索引文档**（`context.rag_info_map`，缺省 `False`）。rag 文档 SHALL 经
``InfoMap.index``（**产出目录指针**）而非 ``register``（仅缓存原文、走线性扫描兜底）登记，
其原文 SHALL 由向量库块文本按**块序号升序**拼回（`_build_chunks` 定长切片 ⇒ 拼接无损）。
因目录层指针块**不受预算裁剪**，rag 文档 SHALL 施加**总量上限**（`_RAG_INFO_MAP_MAX_DOCS = 16`）：
文档数无界即每步无界注入。单个文档读取失败 SHALL **只跳过该文档**（地图是增益面，
不因一档失败阻断装配）。旗关（缺省）⇒ 目录层**逐字不变**。

#### Scenario: 地图定位与按需取详情
- **GIVEN** 一份千页级业务文档已建立信息地图
- **WHEN** 模型需要某章节细节
- **THEN** 先用地图定位指针，再 fetch 对应片段，而非加载全文

#### Scenario: 地图失效重建
- **GIVEN** 源文档内容变更导致地图索引失效
- **WHEN** 检测到 hash 不一致
- **THEN** 触发增量重建，期间降级为全文检索

#### Scenario: 重建失败二阶兜底
- **GIVEN** 地图索引失效且增量重建失败，全文检索同样不可用或超预算
- **WHEN** 模型仍需获取文档细节
- **THEN** 降级为对原始文档的受控分段线性扫描并逐段命中，任务不中断，不因索引不可用而失败

#### Scenario: rag 文档进目录层
- **GIVEN** rag 库已索引若干业务文档，且 `context.rag_info_map` 旗开
- **WHEN** 装配器构建上下文
- **THEN** 目录层 `pointers` 含这些文档的目录指针（从块文本拼回的原文上建索引）

#### Scenario: 旗关时目录层逐字不变
- **GIVEN** rag 库已索引若干业务文档，但 `context.rag_info_map` 未配置（缺省关）
- **WHEN** 装配器构建上下文
- **THEN** 目录层与**未接线前逐字相同**（rag 文档不进地图）

#### Scenario: rag 文档进地图的总量有界
- **GIVEN** rag 库已索引的文档数超过 `_RAG_INFO_MAP_MAX_DOCS`
- **WHEN** 旗开、装配器构建上下文
- **THEN** 进地图的 rag 文档**不超过上限**（其余不进；指针块不受预算裁剪，故上限是硬约束）
