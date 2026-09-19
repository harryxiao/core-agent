# 模块设计：任务规划与编排（Task Planning & Orchestration）

> 对应规格：`doc/openspec/specs/orchestration/spec.md` ｜ 接口：`doc/03-interfaces/orchestration-interface.md`
> 定位：**L3 之上**，把零散的 LLM 循环升级为可处理长周期复杂任务的执行引擎。

---

## 1. 模块定位

单一 loop 只能处理"一轮一步"的短任务；复杂目标需要**跨多轮、多子任务、甚至多智能体**的编排。

本模块在 AgentLoop（L3）之上提供三层能力：**状态机管理、子任务拆解、多 Agent 协同**，使 CORE 从"循环"升级为"执行引擎"。

---

## 2. 内部组成

```
Orchestrator（L3.5）
├── StateMachine      任务状态机：状态转移规则，防跑偏/死循环
├── SubtaskDecomposer 子任务拆解器：大目标 → 分步 Todo，逐步校验
├── MultiAgentRouter  多 Agent 协同：能力匹配 + 消息协议交接
└── ProgressTracker   进度与校验：每步完成校验后再推进
```

---

## 3. 关键设计

### 3.1 状态机管理

```
CREATED → PLANNING → EXECUTING → VERIFYING → DONE
                     ↑            │
                     └── RECOVERING（异常恢复）
                          ↑       │
                          └── FAILED（熔断后终止）
```

- 定义合法状态转移规则（转移表），非法转移被拒绝。
- 每步执行后检查"是否仍在向目标推进"（进度哨兵），检测到跑偏/死循环 → 触发 RECOVERING 或 FAILED。

### 3.2 子任务拆解器

- 把大目标拆为可校验的分步 Todo 列表（每项含：目标、验收标准、依赖关系）。
- 执行采用 **DAG 拓扑序**：依赖完成才启动下一步；无依赖项可并行。
- **逐步校验**：每完成一个子任务，用其验收标准校验结果，通过才推进；失败则回退重试或重新规划。

### 3.3 多 Agent 协同编排

- 注册多个不同能力的子 Agent（各自是一组插件 + profile）。
- MultiAgentRouter 按任务类型匹配最合适的 Agent。
- 通过**标准化消息协议**完成交接：`TaskHandoff {task, context_pack, acceptance, deadline}`。
- 交接上下文由 context 模块打包（信息地图 + 必要事实），避免全量塞入。

---

## 4. 与 loop 的关系

- Orchestrator **不替换** loop，而是驱动多个 loop 实例 / 复用单 loop 处理子任务。
- 每个子任务仍遵守 loop 的四阶段 + 确认门 + 可逆效应约束。
- 状态机事件通过 L0 EventBus 发布，observability 模块订阅做遥测。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 非法状态转移 | 拒绝并记录，不破坏任务状态 |
| 子任务校验失败 | 回退重试（有限次）→ 重新规划 → 标记 FAILED |
| 检测到死循环 | 触发 RECOVERING，注入"换策略"提示或人工介入 |
| 交接目标 Agent 不可用 | 降级到备用 Agent 或转为人工审批 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/orchestration-interface.md`
- 规格：`doc/openspec/specs/orchestration/spec.md`
- 测试：`doc/04-testing/test-cases.md`（ORCH 系列）
