# CodeBase Engine 引入方案

> 日期：2026-09-20
> 关联评估：`codebase-engine-evaluation.md`
> 关联 SOP：openspec_sop（MCP 类工具不新增 capability，复用 mcp server 接入机制）

---

## 1. 结论

引入 **codebase-memory-mcp** 作为 Core-Agent 的代码结构化理解工具，走 **MCP 接入**（复用既有 `mcp` capability），**不新增 `codebase` capability**（D4 决策 A）。

**定位分工**：codebase-memory-mcp = 代码**结构化**理解（symbol / dependency / call graph，AST + LSP，确定性）；RAG（`doc/11-rag`）= 知识**语义**检索（向量库 + embedding）。两者正交互补。

---

## 2. 引入形态

| 项 | 方案 |
|---|---|
| 组件 | codebase-memory-mcp（MIT，纯 C 单静态二进制，零依赖零基础设施） |
| 接入方式 | MCP stdio，单 binary command，无常驻 daemon |
| 挂载点 | 复用 `mcp` capability 的 server 注册与工具路由，`tool-use` 统一调度 |
| 生命周期 | 按需一次性索引（RAM-first，LZ4 压缩 + 内存 SQLite + 结束 dump 释放） |
| 能力面 | 15 MCP tools：search / trace / architecture / impact analysis / coverage / dead code / Cypher 查询 |
| 语言覆盖 | 162 语言（tree-sitter）+ 13 语言 Hybrid LSP 语义类型解析 |

---

## 3. 落地步骤（声明，具体实现由后续 change 驱动）

1. **MCP server 注册**：在 `mcp` capability 的 server 清单中登记 codebase-memory-mcp（stdio 传输，binary 路径可配置）。安装方式：`curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash`（默认装至 `~/.local/bin/codebase-memory-mcp`；Cursor 项目级 MCP 配置见 `.cursor/mcp.json`）。
2. **工具暴露**：15 个 tools 经 `mcp` 工具路由暴露给内核，纳入 `tool-use` 权限与审批沙箱（对齐 `permission`）。
3. **索引子任务**：定义「代码索引」子任务模板——触发条件、索引范围（.git 保护，见 `doc/12-git`）、dump 产物落盘位置。
4. **审计留痕**：索引与查询走 `observability` 审计链路，标注 engine / repo / 结果。
5. **可视化（可选）**：binary 内置 3D 图可视化（localhost:9749），按需开启，不常驻。

---

## 4. 依赖与兼容

- **复用**：`mcp`（server 接入 + 工具路由）、`tool-use`（权限/审批/调度）、`permission`（沙箱）、`observability`（审计）。
- **不重叠**：与 `rag`（语义检索）正交；与 `git`（版本控制操作）互补——codebase-memory-mcp 做代码理解，git 做版本控制。
- **零基础设施**：无外部 DB、无 daemon、无向量库，符合「嵌入式零服务」定位。

---

## 5. 备选与排除（详见评估报告）

- **排除** GitNexus（PolyForm Noncommercial 商用受限 + Node 运行时依赖）
- **不适用** graphify（Claude Code skill，非独立引擎）
- **备选** codegraph（auto-sync 常驻索引）/ code-review-graph（Python 生态深耦合场景）
