# 变更提案 — 记忆面 → 诊断面桥（change 0188）

## 为什么

**ADR-0170 局限②**（失败经验的独立沉淀面）：轮级失败已由 `loop` 写入 L2 条目
`loop.failure.<trace_id>`（`src/core/loop/default.py:833-846`，`tags=["loop","failure"]`，
正文来自 `failure_digest(...)` —— 任务 + 失败原因 + 失败轮次与动作），但**没有任何读者**：

- `Diagnoser.diagnose(traces, prior)`（`src/core/evolution/diagnoser.py:26-28`）只看
  `Trace.success` 与 `Trace.plugin_id` —— 归因线索里**没有**那条已沉淀的失败摘要；
- `src/core/evolution/` 对 memory 是**只写不读**（`engine.py` 只用 `memory` /
  `memory_crystallizer` 做回写）⇒ **失败摘要不驱动进化**。

后果：进化闭环的起点（「缺陷定位到具体插件」）**只有结构化线索**，而系统**已经**在 L2 里
沉淀了人类可读的失败叙述 —— 归因报告与失败摘要之间**缺少一条读取桥** ⇒ 诊断面（以及经
`EvolutionOutcome.diagnosis` 暴露给运维/观测的报告）看不到「这一轮到底怎么失败的」。

## 改什么

| 面 | 变更 |
|---|---|
| `evolution/diagnoser.py` | `Diagnoser.__init__` 新增**可选**接缝 `failure_lookup: Callable[[str], str \| None] \| None`（**依赖倒置**：注入 reader，不 import memory）；`diagnose` 对**每条失败 trace** 取回 `loop.failure.<trace_id>` 摘要并**并入报告**（有界：单条截断 + 总数封顶） |
| `evolution/models.py` | `DiagnosisReport` 新增**可选**字段 `failure_notes: list[str] = []`（缺省空 ⇒ 既有构造 / 相等 / 消费面**逐字不变**；`Proposer.propose` 取 `issue` 的逻辑**不动**） |
| `runtime.py` | 组合根注入闭包：从 `MemoryBackend` 按 id `loop.failure.<trace_id>` 精确取正文（**零副作用**、层无关） |
| 规格 | `evolution` **MODIFIED**「对比诊断」（失败摘要条款 + 有界 + fail-open + 缺省逐字）+ 1 Scenario |
| 测试 | 未接线逐字不变（回归锚）/ 注入后报告含摘要 / 查询抛错降级 / 有界（截断 + 封顶 + 只查失败 trace）/ 组合根接线（端到端取回） |

## 影响

- **行为变更（有意且保守）**：接线后 `DiagnosisReport.failure_notes` 携带已沉淀失败摘要。
  **归因判定（`target_plugin` / `confidence` / `evidence`）与 `issue` 文本逐字不变** —— 桥只
  **增补**证据面，不改判定。缺省 UNWIRED ⇒ 报告与既往**逐字一致**。
- **可逆 / 无副作用**：本 change **不新增任何写入**；组合根的 lookup 走
  `MemoryBackend.search("")`（**不**经 `MemoryStore.read`）⇒ 不强化 `reuse_count`、不落盘
  （与 change `0187` 的「有副作用但有界」读取面**划清**）。
- **方向不变**：`evolution` 不 import `memory`（注入接缝）；`memory` / `context` **零改动**。
- 无新增第三方依赖；无新配置键。
