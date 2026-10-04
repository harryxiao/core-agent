# 设计：doc-layer-closeout（E9）

## 1. 判定：为什么这是文档缺口而非代码缺口

E9 四处逐一核实（一手读源码 + 测试 + 规格）：

| E9 项 | 一手核实结论 | 本变更处置 |
|---|---|---|
| `data-model.md` §4 待补 4 实体 | 四实体**均已存在**于源码；文档未回填 | ✅ 回填 |
| rag/mcp/git 替换锚点 | 三条锚点**测试均已存在**；缺 `test-cases.md` 追踪行 | ✅ 补追踪行 |
| 远程制品仓库 / market-registry 远端 | 代码未接（真后端） | ✋ 归 **C 类**，账本改判 |
| `retrospective.md` `src = 0` 过时 | 陈述与现状相反（`src/` 已落地） | ✅ 补记订正 |

「锚点已存在」的证据（每条都能指到具体测试）：

- **rag**：`tests/test_rag.py:71` `_FixedEmbedder(Embedder)` → `:162` `Retriever(_FixedEmbedder(), store)`。
  调用方 `Retriever` 只依赖 `Embedder` 抽象（`src/core/rag/embedder.py`）与 `VectorStore`
  ABC（`vector_store.py:30`），换实现不改调用方。
- **mcp**：`MCPClient(transport_factory=...)`（`src/core/mcp/client.py:55,207`）→
  `tests/test_mcp.py` 全篇用 `FakeTransport` 注入（如 `:77,108,151`）。
- **git**：`GitClient(backend=...)`（`src/core/git/client.py:27`）+ `build_backend()`
  （`backend.py:50`）→ `tests/test_git.py:11` `FakeBackend` 注入。

## 2. 追踪行的粒度（为什么是 TC-RAG-10 / TC-MCP-06 / TC-GIT-11）

`test-cases.md` 的既有约定是「一行 = 一个场景」，且列 `对应需求`。故新增行按
**规格 Requirement**（而非 ADR）挂靠——三条 Requirement 的名字本身就是
`…依赖注入隔离`，正是 ADR-0040 的落地形态：

| 用例 | 对应 Requirement | 步骤 | 期望 |
|---|---|---|---|
| TC-RAG-10 | rag「存储与 Embedding 依赖注入隔离」 | 注入 `Embedder` / `VectorStore` 替身 | 检索与调用方零改动 |
| TC-MCP-06 | mcp「传输层抽象与依赖注入隔离」 | `transport_factory` 注入替身传输 | `MCPClient` 调用方零改动 |
| TC-GIT-11 | git「GitClient 抽象接口与依赖注入隔离」 | 注入 `GitBackend` 替身 | `GitClient` 调用方零改动 |

**只登记既有覆盖，不造新测试**：三个 Scenario 已被上述用例实际执行（`_FixedEmbedder` /
`FakeTransport` / `FakeBackend` 就是「替换 X」本身），再造一个同义测试是重复建设。
rag 的「替换向量库实现」Scenario 目前只有 `InMemoryVectorStore` 一个实现（生产 sqlite-vec
未接 → C 类），追踪行**如实标注**该半覆盖状态，不虚报。

## 3. ADR 与回顾文档的订正方式：补记，不改写

ADR-0040 是 Accepted 的**历史裁决**；`retrospective.md` 是某阶段的**历史快照**。
两者的正文陈述在当时为真，今天过时——正确的处置是**追加带日期的补记**，而非把历史正文改成
「当时就应该知道」的样子（那会伪造决策记录）。故：

- ADR-0040「后果」行在其后追加 `（2026-10-05 补记：…）`，不改原句。
- `retrospective.md` §六.1 保留原句，追加 `**（2026-10-05 更新：…）**`。

## 4. 风险

极低：纯文档，零 `src/`、零 `tests/`、零 spec 改动。唯一可感风险是「回填的字段与源码漂移」——
故 §4 每个实体都写**源码位置**（`core/im/models.py:27` 等），读者可一步核对。
