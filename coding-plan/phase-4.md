# Phase 4 — 多 Agent 编排（orchestration / rag）

> 里程碑：**M3 多 Agent 编排**（roadmap §3）
> 位置：分层图 L4 编排层（任务规划编排）+ L3 检索底座（RAG）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 3（单 Agent 闭环）

---

## 1. 范围与定位

本 Phase 交付 **2 个能力，把「单 Agent」升级为「多 Agent 协同」**：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| orchestration | 任务状态机 + 子任务拆解 + 多 Agent 协同 + 断点续跑 + 并行扇出 | L4 编排层 |
| rag | 本地向量库（sqlite-vec）+ 文档摄取分块 + 语义检索 + 生成融合 | L3 检索底座 |

**关键事实**：`rag` 在仓库中**无 interface 文件、无错误码定义**（contracts_summary.md §21 明确标注「无接口」），因此本 Phase **首步任务是补齐 rag 契约**（见 §4）。

---

## 2. 里程碑验收（M3 多 Agent 编排）

**M3 标志**：编排 DAG + RAG 检索可运行。以下全部勾选才算 Phase 4 完成：

- [ ] orchestration：合法状态转移、非法转移拒绝、死循环检测
- [ ] orchestration：拆解拓扑执行、子任务校验通过才推进
- [ ] orchestration：能力匹配交接、无匹配 Agent 处理；挂起/恢复/取消
- [ ] orchestration：波次划分并行扇出、fan-in 汇总推进、资源上限、fan-out 幂等派发
- [ ] orchestration：成功标准 + 进度追踪、未达标重试/重规划
- [ ] orchestration：优先级排序、同优先级稳定、缺省处理
- [ ] orchestration：复用异步接口、扇出真并发非阻塞、契约空白闭合
- [ ] rag：文档导入建索引、源变更增量更新、摄取/重建失败降级
- [ ] rag：本地推理无外部依赖、可经 llm-provider 切远端模型
- [ ] rag：top-k 相似度检索；检索上下文注入生成、无结果降级
- [ ] rag：与 CodeBase Engine 职责边界（文档/代码各归其位）
- [ ] 端到端：一个多子任务任务经编排 DAG 分发到多个 Agent，检索结果注入生成全程可跑

---

## 3. 依赖与前置

- **上游**：Phase 0（plugin-registry / configuration / observability）+ Phase 1（llm-provider / tool-use / memory）+ Phase 2（durability / constraints）+ Phase 3（loop / context / skills / skillhub）。
- 关键前置：
  - `orchestration` 的 `MultiAgentRouter` 依赖 Phase 3 的 loop 能作为「可被编排的 Agent 单元」复用——多 Agent 交接前，单 Agent 必须先能跑。
  - `orchestration` 的「复用异步接口」依赖 Phase 3 loop 的 `arun()/astream()`，扇出必须真并发非阻塞。
  - `rag` 的「可经 llm-provider 切远端模型」依赖 Phase 1 的 llm-provider 模型路由。
  - `rag` 与 CodeBase Engine 的职责边界——文档走 rag，代码走 CodeBase，不得混入。

---

## 4. 首步任务

**补 rag 契约（本 Phase 的唯一硬前置）**：

1. 依据 contracts_summary.md §21 的能力/契约描述，为 `rag` 补齐：
   - `specs/rag/spec.md` 的接口与错误码定义（当前无 interface 文件）
   - `03-interfaces/rag.md` 接口文件
   - 建议接口命名：`VectorStore`、`DocIngestor`、`Embedder`、`Retriever`、`RAGFusion`
   - 建议方法：`ingest()`、`index()`、`update()`、`search()`、`fuse()`、`embed()`
   - 建议错误码：`INGEST_FAILED`、`INDEX_REBUILD_FAILED`、`NO_RESULT_DEGRADED`
2. rag 契约补齐走 openspec_sop（新增 capability 需 validate 全绿）后再进入编码。

**启动前核对**（按顺序执行）：
1. 确认 orchestr 的 spec/interface 完整（contracts_summary §18）。
2. 先补 rag 契约并 validate 通过，再开始 orchestration。

---

## 5. 实现顺序（模块级拓扑序）

### 5.1 rag（先，独立，仅依赖 llm-provider 可选切换）

- 首步补契约后实现：`VectorStore`、`DocIngestor`、`Embedder`、`Retriever`、`RAGFusion`
- 验收重点：嵌入式零服务存储（sqlite-vec）、增量更新、失败降级、本地推理无外部依赖、top-k 检索、无结果降级

### 5.2 orchestration（后，依赖 rag + loop + skills + tool-use）

- 核心类/接口：`StateMachine`、`SubtaskDecomposer`、`MultiAgentRouter`
- 数据类型：`TaskState` / `Subtask` / `Plan` / `VerifyResult` / `TaskHandoff`
- 关键方法：`transition()`、`state()`、`decompose()`、`verify()`、`match()`、`handoff()`
- 错误码：`DEADLOOP_DETECTED`、`INVALID_TRANSITION`、`NO_AGENT_MATCH`、`PROGRESS_NOT_MET`、`SUBTASK_VERIFY_FAILED`、`WAVE_FANOUT_LIMIT`
- 验收重点：状态机死循环检测、拆解拓扑执行、能力匹配交接、并行扇出 + fan-in、断点续跑

---

## 6. 契约对齐

以 `contracts_summary.md` 为唯一契约基线（本 Phase 对应第 18/21 章）：

| Capability | 章节 | 关键接口/方法（实现必须覆盖） |
|---|---|---|
| orchestration | §18 | `StateMachine`(transition/state)、`SubtaskDecomposer`(decompose/verify)、`MultiAgentRouter`(match/handoff) |
| rag | §21 | 无现成接口——首步补齐（`VectorStore`/`Retriever` 等，见 §4） |

**契约红线**（违反即返工）：
1. 非法状态转移必须拒绝，任务图必须能检测死循环并报 `DEADLOOP_DETECTED`。
2. 子任务未通过校验不得推进下一步（`SUBTASK_VERIFY_FAILED`）。
3. 无匹配 Agent 必须显式报 `NO_AGENT_MATCH`，不得静默跳过。
4. fan-out 必须幂等派发，波次扇出超上限报 `WAVE_FANOUT_LIMIT`。
5. rag 检索无结果必须降级，不得让生成链路崩断；摄取/重建失败必须降级不阻塞。

---

## 7. 门禁验收

全局四命令（见 `doc/05-development/development-standards.md`）全部通过：

```bash
ruff check src tests
ruff format --check
pyright
pytest -q
```

本 Phase 专属校验（附加于全局门禁）：

- [ ] 架构测试：orchestration 不得反向依赖 composition（Phase 6 才引入）
- [ ] 状态机测试：非法转移拒绝 + 死循环检测生效
- [ ] 并行扇出测试：fan-out 真并发非阻塞，fan-in 汇总正确，幂等无重复派发
- [ ] 断点续跑测试：挂起后恢复，进度不丢失
- [ ] rag 摄取测试：文档导入建索引、源变更增量更新、失败降级
- [ ] rag 检索测试：top-k 相似度正确、无结果降级、生成融合上下文注入
- [ ] 端到端冒烟：编排 DAG 分发多子任务 + RAG 检索注入生成全程可跑

---

## 8. 提交规范

- **一个 Phase 一个 commit**：rag 契约补齐 + 2 模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase4): orchestration/rag 多 Agent 编排（M3）`
- 提交后回填 roadmap §3 的 M3 里程碑状态为「完成」，并同步更新 `README.md` Phase 4 行状态。
