# CORE-Harness 架构设计 · 最终复盘报告

> 复盘基准：`doc/` 全量 197 个 md / 11,385+ 行 · git HEAD `c83a2b6` · `openspec validate --all` 实跑 **43 passed / 0 failed / 0 WARNING / 0 INFO**
> 数据来源：实测（ls / grep / git log / validate），非记忆断言

---

## 一、项目总览

**目标**：从零设计一个「可自演进」的通用 Agent 架构（CORE-Harness），以 OpenSpec（spec-driven）驱动，输出到「可落地」级设计文档。

**定位边界**：纯设计文档，`src = 0`（无实现代码）——属设计完整度审计的定位，非缺陷。

**最终交付规模（实测）**：

| 维度 | 实测值 |
|---|---|
| 一级目录 | 14 个（00-product ~ 12-git + openspec + paper） |
| 能力模块 / specs | **22 个** |
| OpenSpec changes | **22 个 active**（0001~0022 连续）+ 1 个 archive 空骨架 |
| 接口文档（03-interfaces） | **20 个** |
| 模块实现文档（02-modules） | **17 个**核心运行时模块（另 ui/im/rag/git/distributed 5 个领域模块设计落各自顶层目录） |
| ADR | **31 个**（ADR-0001 ~ ADR-0031，连续无跳号） |
| 功能需求 FR | **119 条**（22 模块，`CORE-<模块>-R<n>`） |
| 论文研读 | 4 篇 arXiv PDF + self-improvement 对比沉淀 |

---

## 二、最终架构全貌（六维度完整性）

审计结论：**设计文档「可落地」级，六维度全部有实质内容覆盖**，非仅有文件占位。

| 维度 | 覆盖情况 |
|---|---|
| 系统架构 | 分层插件化架构 + 31 条 ADR 决策记录，末尾含 ADR→文档映射表 |
| 模块设计 | 22 能力模块，17 核心实现文档 + 22 spec |
| 异常处理 | 21/22 spec 含异常处理；「查漏补缺」补齐 19 模块的异常处理 + 连接管理（涉及连接的模块必带连接管理） |
| 数据结构 | 统一数据模型 `data-model.md` + 各接口文档 schema/数据契约 |
| 接口设计 | 20 接口文档，README 目录树与实际 100% 一致 |
| 前后端交互 | UI 三模（CLI/Web/Desktop）+ Harness Host/Web Client 分离方案 |

核心架构理念落地：**Orchestrator-workers 编排（Plan）→ 子 Agent 递归 ReAct（Act）**，loop 保持简单（不做自适应测量）；自我迭代对齐 **ModularRSI 四阶段**（论文实证）。

---

## 三、演进历程（关键里程碑，按时间线）

| 阶段 | 关键提交 | 内容 |
|---|---|---|
| 地基 | `7ac023e` / `3fded33` / `66021bc` | 统一数据模型 + ADR-0027；CLI 斜杠命令交互；OpenClaw/Hermes 横向对比 |
| 领域模块 | `a24c62e`~`ee54848` | deployment(0013)、ui 实时语音(0014)、core-profile(0015)、题词工程(0016)、Cursor 四件套 + Core.md |
| 论文对齐 | `42d669c` / `5741382` | 下载 4 篇 arXiv；沉淀 self-improvement comparison（对齐 ModularRSI） |
| 编排运行时 | `90c9b38` | 0017 编排三能力：并行扇出 / 目标监控 / 优先级调度 |
| 连接技术 | `25b57e0` | 0018 MCP Streamable HTTP 会话多流复用 + 0019 Harness Host/Web Client 分离 |
| 需求追踪 | `5a578aa` | requirements 1.5 节 MCP 追踪条目补齐（R5/R6/R7/R9） |
| 查漏补缺 | `53fc19a` | 0020/0021/0022 补齐 19 模块异常处理 + 连接管理（高4+中8+低7） |
| 审计修复闭环 | `c83a2b6` | P1/P2 修复 + **34 处 delta↔merged 漂移全量对齐** → validate 归零 |

---

## 四、系统级审计与修复闭环

**审计结论**（`design-completeness-audit.md`）：整体 PASS，发现 6 项真实缺陷（P1×3 + P2×3）+ 2 项观察项（P3×2）。

- 🔴 **P1（测试文档脱节）**：test-strategy 覆盖矩阵缺 deployment/core-profile 2 行 + 8 处 R 编号过期；test-cases 缺 RAG/GIT/DEP/PROF 4 模块用例。
- 🟡 **P2（规范瑕疵）**：deployment R 编号乱序；distributed「可选 P2P」缺 SHALL/MUST；0010/0017 delta 头重名。
- ⚪ **P3（无需改）**：src=0；R 编号非严格同号（README 已明示追踪映射）。

**修复结果**：
1. P1/P2 全部修复，validate → **43 passed / 0 failed / 0 WARNING / 0 INFO**。
2. 修复过程中**深挖出历史遗留深坑**：validate 的 INFO 每文件只报第一条，表面「2I」实为全仓 **34 处 delta↔merged 漂移**（11 对 + 23 处残留），已 100% 纯增式对齐（merged 超集覆盖 delta，0 反向删改），彻底归零。

---

## 五、方法论沉淀（本轮新增 4 条 SOP 教训）

| 任务 | 沉淀教训（openspec_sop） |
|---|---|
| 0017 编排 | Affected docs 除「文件名逐字一致」还须「列全」所有实际改动文档，用 git status 一一对应核对 |
| 0018 术语重构 | 术语重构除正文外还须 grep 全 doc/ 查 scenario **标题**术语一致性，历史快照 change 不动 |
| 查漏补缺 | proposal↔delta 正向复核口径（每模块异常/连接管理逐条对照） |
| P1/P2 修复 | **validate 的 INFO/WARNING 每文件只报第一条**——表面 N 条 ≠ 实际 N 处，归零须逐 change 全量 diff；删 ADDED 段会报 ERROR 勿删 |

---

## 六、遗留项与未来方向

1. **实现落地**：设计已达「可落地」级，`src = 0` 是唯一短板，下一步可据 119 FR + 22 spec 进入编码阶段。**（2026-10-05 更新：该短板已消除 —— `src/core/` 按 22 个能力模块全部落地（Phase 0–18 完成，700+ 测试），本文其余结论为当时快照，未随编码阶段改写。）**
2. **P3 观察项**：spec Requirement 数与 requirements R 数非严格同号（README 已明示追踪映射规则，符合规范，无需改）。
3. **自我演进闭环**：ModularRSI 四阶段（Self-Harness）设计已对齐论文，待有实现后进入实证验证。

---

**一句话总结**：22 能力模块、20 接口、119 FR、31 ADR 的架构设计，历经「地基 → 领域模块 → 论文对齐 → 编排 → 连接技术 → 查漏补缺 → 审计修复」七阶段演进，最终以 **validate 43/0/0W/0I 全绿** 收官，达到「可落地」级交付标准。
