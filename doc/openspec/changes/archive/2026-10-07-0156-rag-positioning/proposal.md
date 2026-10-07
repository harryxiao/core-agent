# rag 定位文档化：辅助本地知识库，不注入主链路（记忆三面路线图 G5）

## Why

- 记忆三面（`memory` / `notes` / `rag`）职责重划的**最后一站 G5**：把 `rag` 的**定位**明确成文。
  用户裁决倾向（原始三问之③）：「长期记忆重要信息走 **Notes**，**rag 做辅助 + 本地知识库查询**」。
- **现状即答案**：rag 已是「辅助 + 本地知识库」—— 知识文档的**按需**语义检索，经 CLI
  `rag ingest|search|ask` **一次性**驱动；**不**注入 loop 每轮上下文（ADR-0097 ⑥ 明示不做）；
  **不**做结构化实体抽取 / 跨会话实体持久化（该面已由 change `0155` / 关键事实落 **memory**）。
  **零代码行为缺口** —— 缺的是把该定位**写成一处可发现、可守护的契约**。
- 缺口（**文档层**）：定位**散落**在 `ADR-0097 ⑥`（决策内一条）、`11-rag/rag-architecture.md` §1、
  `02-modules/rag.md` §1 —— 三处都未把「`rag` / `memory` / `notes` **三面边界**」与「**不注入主链路**」
  并成**单一目视可达**的定位；G4 落地「实体抽取归 memory」后，读者仍无法一眼看出三面分工。

## What Changes

- `doc/11-rag/rag-architecture.md` §1：把「定位与场景」扩为**三面边界 + 不注入主链路**的明示定位
  （rag 知识文档语义检索 / memory 经验轨迹 + 关键事实 / notes 主题文档）；写明「参与 loop 上下文
  须**先改 ADR-0097 ⑥**」。
- `doc/02-modules/rag.md` §1：同步定位（辅助本地知识库、CLI 一次性、不注入 loop、不做实体抽取）。
- `doc/03-interfaces/rag-interface.md`：新增 §「定位：辅助按需，不注入主链路」。
- `doc/01-architecture/adr.md`：**ADR-0148**（三面职责边界 + rag 定位「现状即答案」+ 门槛）
  ＋ 变更追踪行。
- `tests/test_architecture.py`：**定位守护** —— 主链路 / 三面兄弟（`loop` / `context` / `memory` /
  `notes`）SHALL NOT import `core.rag`（把「不注入主链路」由**散文**变**可执行不变量**；与既有 Phase
  边界守护同构）。
- `coding-plan/known-risk.md` §3：登记 ADR-0148 已知局限。

## 规格中性（`.openspec.yaml: schema: spec-driven + skip_specs: true`）

**不改任何规格行为**：rag 规格已有的「与 CodeBase Engine 职责边界」与各 SHALL 均已覆盖 rag 的**能力面**；
本变更只**补文档定位**并**加一条结构守护**。无新 SHALL、无行为变更 ⇒ **无规格 delta**（`skip_specs: true`）。

## 明确不做

- **不把 RAG 注入 loop**（承 ADR-0097 ⑥）：那是**特性**，牵动 context 预算与 prompt 装配 —— 若要做，
  **先改 ADR-0097 ⑥**，再开规格变更。本变更只**文档化门槛**，不跨越它。
- **不把结构化实体抽取 / 跨会话实体放进 rag**：该面归 **memory** 关键事实（change `0155`）；rag 不重复建面。
- **不加 rag 代码 / CLI / 行为**（**零 `src/` 改动**）。
- **不引三方库**（守护用 stdlib `ast`，沿 `test_architecture.py` 既有实现）。
- **不动 rag 既有裁决**（`HashEmbedder` 离线降级基线 / 不引本地语义模型 / 暴力余弦不换 ANN —— 承
  `rag-offline-embedder-decision` 与 ADR-0097）。
