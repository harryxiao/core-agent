# CodeBase Engine 横向评估报告

> 日期：2026-09-20
> 关联变更：本报告为**任务3**交付物，结论落地于 `doc/10-codebase-engine/integration-plan.md`（引入方案，走 MCP 接入，不新增 capability）。
> 调研原始记录：`plan_rag_codebase/research_findings.md`

---

## 1. 定位澄清（关键结论）

GitHub 上以「codebase / 代码智能」命名的 5 个主流项目，本质是**「代码知识图谱」路线**（AST 解析 → 符号 / 依赖 / 调用链图谱），与任务2 RAG（向量库 + embedding 语义检索）**正交互补、不重叠**：

- **CodeBase Engine** = 代码**结构化**理解（symbol / dependency / call graph，确定性 AST + LSP）
- **RAG** = 知识**语义**检索（文档 / 知识库，向量相似度，弥补 LLM 知识缺口）

两者应**同时引入**：codebase-memory-mcp 作为「代码索引工具」（外部单二进制走 MCP 接入），RAG 作为「知识检索基建」（内部向量库）。一个管「代码长什么样」，一个管「知识记了什么」，职责正交。

---

## 2. 五项目横向评估矩阵

| 维度 | codebase-memory-mcp | GitNexus | graphify | codegraph | code-review-graph |
|---|---|---|---|---|---|
| repo | DeusData/codebase-memory-mcp | abhigyanpatwari/GitNexus | Graphify-Labs/graphify | colbymchenry/codegraph | tirth8205/code-review-graph |
| ★ | 43.8k | 47.5k | 119.8k | 71.5k | 31.6k |
| 语言 | C | TypeScript | Python | C | Python |
| License | **MIT** | **PolyForm Noncommercial**（商用受限） | MIT | 未确认 | 未确认 |
| 定位 | 代码知识图谱 MCP | 企业代码库上下文引擎 | Claude Code skill（/graphify） | 预索引代码知识图谱（auto-sync） | Local-first 代码智能图谱 |
| 是否向量库 | ❌ 无（纯 AST+LSP） | ⚠️ 可选（opt-in embeddings） | ❌ 无 | ❌ 无 | ❌ 无 |
| 接入形态 | MCP stdio，单 binary | 服务 / Node 运行时 | 依赖 Claude Code 宿主 | 常驻索引服务 | 本地服务 |
| 零依赖 | ✅ 单静态二进制零基础设施 | ❌ 依赖 Node + 可选 DB | ❌ 依赖 Claude Code | ❌ 常驻 daemon | ❌ Python 生态 |
| 语言覆盖 | **162 语言** | 企业主流若干 | Claude 托管 | 未确认 | 主流若干 |
| 许可商用适配 | ✅ MIT 可商用 | ❌ **Noncommercial 排除** | ✅ MIT | ⚠️ 未确认 | ⚠️ 未确认 |

### 排除 / 降级理由

- **GitNexus**：`PolyForm Noncommercial` 许可，商用受限，且 TypeScript 运行依赖 Node 运行时，与 Core-Agent「嵌入式零服务、零依赖」定位冲突 → **排除**。
- **graphify**：是 Claude Code 的 skill（`/graphify`），非独立引擎，能力受宿主 Claude Code 限制，无法作为 Core-Agent 的通用索引基建 → **不适用**。
- **codegraph**：auto-sync 常驻索引，需常驻 daemon，与「按需一次性索引」偏好不符；License 未确认 → 备选。
- **code-review-graph**：Local-first，Python 生态，若需与 Core-Agent Python 工具链深度耦合可选 → 备选。

---

## 3. 重点评估：codebase-memory-mcp（首选）

| 维度 | 实测数据 | 评估 |
|---|---|---|
| 语言 / 许可 | 纯 C，**MIT**，单静态二进制，**零依赖、零基础设施**（无向量库 / 无外部 DB / 无 daemon） | ✅ 与 Core-Agent「嵌入式零服务」定位完全契合 |
| 语言覆盖 | 162 语言（158 vendored tree-sitter grammars + 4 通用）；13 语言 Hybrid LSP 语义类型解析（Python/TS/JS/JSX/TSX/PHP/C#/Go/C/C++/Java/Kotlin/Rust/Perl） | ✅ 覆盖 Coding 全场景 |
| 索引管线 | RAM-first（LZ4 压缩 + 内存 SQLite + 结束单次 dump），内存索引后释放 | ✅ 无常驻资源占用，可纳入一次性子任务 |
| 查询性能 | sub-ms 级；99% fewer tokens（vs ~412k file-by-file search） | ✅ 显著降低 LLM token 成本 |
| MCP tools | 15 个：search / trace / architecture / impact analysis / coverage checks / Cypher 查询 / dead code 检测等 | ✅ 直接经 MCP 暴露给 Core-Agent |
| 客户端面 | 45 client surfaces（39 auto + 6 conditional），3 层 agent（Scout / Verify / Auditor） | ✅ 多客户端接入面广 |
| 可视化 | 内置 3D 图可视化（localhost:9749，binary 自服务） | ✅ 免部署可视化 |
| IaC 支持 | Dockerfile / K8s manifests / Kustomize overlays 索引 | ✅ 含基础设施即代码 |
| 语义关系 | SIMILAR_TO（MinHash+LSH 近克隆）、SEMANTICALLY_RELATED、包/模块解析（manifest 扫描） | ✅ 近克隆与语义关联能力 |
| MCP 接入 | stdio，单 binary command，无需 daemon | ✅ 零服务接入 |
| 工程成熟度 | SLSA3、VirusTotal 扫描、8050 tests、macOS/Linux/Windows | ✅ 供应链与质量成熟 |

**综合评级：A（首选引入）**。在零依赖、语言覆盖、接入形态、工程成熟度四个关键维度全面领先，且 MIT 许可无商用顾虑。

---

## 4. 推荐引入方案

- **首选**：codebase-memory-mcp（MIT / 零依赖 / 15 tools / 45 client / 成熟度最高 / 内置 3D 可视化）
- **排除**：GitNexus（PolyForm Noncommercial 商用受限 + Node 运行时依赖）
- **备选**：code-review-graph（若需 Python 生态深度耦合）、codegraph（若需 auto-sync 常驻索引）
- **不适用**：graphify（Claude Code skill，非独立引擎）

**落地形态（D4 决策）**：不新增 `codebase` capability，codebase-memory-mcp 作为**外部 MCP 工具**接入，复用既有 `mcp` capability 的 server 接入机制，由 `tool-use` 统一调度。详见 `integration-plan.md`。
