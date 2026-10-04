# 文档层未闭合项收口（doc-layer-closeout）

## Why

账本 **E9**「文档层其他未闭合项」列出四处，逐条一手核实后**性质不同**，本变更只做其中两处
**真缺口**（另两处已在账本中改判归属，见「明确不做」）：

1. **`data-model.md` §4「待补定义实体」从未回填**（`:130-138`）。该表记
   Session / ExecContext / ExecRequest / ExecResponse「被接口引用但无定义……字段以**编码阶段
   落地为准**」。编码阶段早已结束，四个实体在源码中均已存在
   （`core/im/models.py:27`、`core/constraints/models.py:16/24/34`），但文档一直没回填 ——
   即「编码阶段落地为准」这句**过期承诺**仍在指引读者。
2. **ADR-0040 的替换性锚点在 rag/mcp/git 三处悬空**（`adr.md:329`）。ADR-0040 声称 MAL 的
   可替换性「可被『替换 X → 调用方零改动』测试锚点验证（llm-provider 已有 TC-LLM-03、
   im 已有 TC-IM-01，**rag/mcp/git 待补**）」。核实：三条锚点**测试早已存在**
   （`Retriever(_FixedEmbedder(), store)` / `MCPClient(transport_factory=...)` /
   `GitClient(backend=FakeBackend())`），缺的是**测试用例追踪号**——即规格
   「…依赖注入隔离」三条 Requirement 的场景，在 `test-cases.md` 里没有对应行，
   读者无法从规格走到用例。

两处都是**文档与事实的偏差**，不是代码缺陷：无行为变更、无接口变更。

## What Changes

- `doc/01-architecture/data-model.md`：§4 由「待补定义实体」改为**已回填**，四实体给出
  权威源码位置与字段；§3 裁决表第 5 行（Session）同步指向落地类型。
- `doc/04-testing/test-cases.md`：为三条 DI 隔离 Requirement 补追踪行
  —— `TC-RAG-10`（存储与 Embedding 注入隔离）、`TC-MCP-06`（传输层注入隔离）、
  `TC-GIT-11`（GitClient 注入隔离），各指向既有测试。
- `doc/01-architecture/adr.md`：ADR-0040「后果」补记锚点登记结果（保留原文，追加日期补记，
  不改写历史裁决）。
- `doc/00-product/retrospective.md`：§六.1「`src = 0` 是唯一短板」已过时（`src/` 已按 22 个
  能力模块落地），按补记订正。

## 规格中性（`.openspec.yaml: schema: spec-driven + skip_specs: true`）

三处改动**均无规格行为变更**：被补的两处，规格（`rag`/`mcp`/`git` 的「依赖注入隔离」
Requirement）、接口文档、源码**三者本就一致**，本变更只是把**已存在的事实**登记到
数据模型 / 测试追踪层。故不产出 spec delta。

## 明确不做（账本已改判归属，不在本变更内）

- **远程制品仓库与凭证 / market-registry 远端服务**（`adr.md:293,302`）：真后端未接，
  归 **C 类**（`debug-gaps.md` §2.3），非文档缺口。
- **`retrospective.md` 之外的 D 类订正**：D 类已在账本 §9 第 1 步清尾，不重开。
- **不为「替换向量库」新造第二个 `VectorStore` 实现**：仅为凑测试而写生产代码属投机
  （CLAUDE.md §2）；`InMemoryVectorStore` 即注入替身，生产 sqlite-vec 未接属 C 类。
- **不改任何 `src/` 与 `tests/`**：本变更纯文档。
