# CORE-Harness 产品需求文档（Requirements / PRD）

> 版本 v0.1 ｜ 需求编号规则：`CORE-<模块>-R<n>`，与 `openspec/specs/*`、`04-testing/test-cases.md` **同号**。
> 每条功能需求（FR）必须可追踪到 `openspec/specs/` 中对应的 Requirement；非功能需求（NFR）追踪到架构/测试文档。

---

## 1. 功能需求（Functional Requirements）

### 1.1 插件注册与组合（plugin-registry）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PLG-R1 | 系统 SHALL 支持注册任意符合插件契约的能力单元，无需改动核心代码 | P0 | plugin-registry/spec.md |
| CORE-PLG-R2 | 系统 SHALL 在插件加载/卸载/升级时记录可逆副作用，支持一键回滚 | P0 | plugin-registry/spec.md |
| CORE-PLG-R3 | 系统 SHALL 解析并注入每个插件的 coeffect（权限/宪章/配置），缺失时拒绝执行 | P0 | plugin-registry/spec.md |
| CORE-PLG-R4 | 系统 SHALL 支持运行时热插拔（HMR）插件，不中断主循环 | P1 | plugin-registry/spec.md |

### 1.2 智能体循环（loop）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-LOOP-R1 | 循环 SHALL 执行 感知→推理→行动→写记忆 四阶段，每轮结束必须写记忆 | P0 | loop/spec.md |
| CORE-LOOP-R2 | 循环 SHALL 支持插件化替换（不同策略可互切），默认实现不超过 ~100 行 | P0 | loop/spec.md |
| CORE-LOOP-R3 | 循环 SHALL 在行动阶段对每个 action 做可逆追踪，异常时可回滚该轮 | P0 | loop/spec.md |
| CORE-LOOP-R4 | 循环 SHALL 遵守人机确认门：不可逆/高风险操作必须先 ask_user | P0 | loop/spec.md |

### 1.3 分层记忆（memory）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-MEM-R1 | 记忆 SHALL 分 L0元规则/L1索引/L2事实/L3技能/L4归档 五层，层间可单向/双向迁移 | P0 | memory/spec.md |
| CORE-MEM-R2 | 记忆 SHALL 支持按相关性检索，控制注入上下文的 token 上界 | P0 | memory/spec.md |
| CORE-MEM-R3 | 记忆 SHALL 支持将 L3 技能"结晶"为插件，及反向"溶解"回记忆 | P0 | memory/spec.md |
| CORE-MEM-R4 | 记忆后端 SHALL 可插拔（文件后端先行），接口与存储解耦 | P1 | memory/spec.md |

### 1.4 工具使用（tool-use）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-TOOL-R1 | 系统 SHALL 提供至少 9 个原子工具插件（code_run/file_*/web_*/ask_user/进程/memory） | P0 | tool-use/spec.md |
| CORE-TOOL-R2 | 每个工具 SHALL 声明 JSON Schema 参数，非法参数调用返回结构化错误 | P0 | tool-use/spec.md |
| CORE-TOOL-R3 | 每个写类工具 SHALL 提供撤销函数（可逆效应），支持时间旅行回滚 | P0 | tool-use/spec.md |
| CORE-TOOL-R4 | 工具执行 SHALL 有超时/资源上限，异常不拖垮主循环 | P1 | tool-use/spec.md |

### 1.5 MCP 集成（mcp）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-MCP-R1 | 系统 SHALL 作为 MCP client 发现并调用外部 MCP server 的 tools | P0 | mcp/spec.md |
| CORE-MCP-R2 | 系统 SHALL 支持读取外部 resources 与 prompts，并纳入 loop 的上下文 | P1 | mcp/spec.md |
| CORE-MCP-R3 | MCP 工具调用 SHALL 同样受可逆追踪与确认门约束 | P0 | mcp/spec.md |
| CORE-MCP-R4 | 系统 SHALL 支持 stdio 与 HTTP 两种 MCP 传输 | P1 | mcp/spec.md |

### 1.6 进化引擎（evolution）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-EVO-R1 | 进化引擎 SHALL 执行 诊断→提案→验证→评测 四阶段闭环 | P0 | evolution/spec.md |
| CORE-EVO-R2 | 诊断 SHALL 定位缺陷到**单个插件**级别（可归因） | P0 | evolution/spec.md |
| CORE-EVO-R3 | 提案 SHALL 产出世代化的不可变产物，过验证门前不进入运行 | P0 | evolution/spec.md |
| CORE-EVO-R4 | 评测 SHALL 使用留出集，进化在留出集上退化时自动回滚 | P0 | evolution/spec.md |

### 1.7 权限与审批管控（permission）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-PERM-R1 | 系统 SHALL 将操作分为只读/数据编辑/高危三级，高危操作默认拦截（deny-by-default） | P0 | permission/spec.md |
| CORE-PERM-R2 | 系统 SHALL 对高危操作走人工审批流，审批 TTL 超时默认拒绝并审计归档 | P0 | permission/spec.md |
| CORE-PERM-R3 | 系统 SHALL 提供沙箱隔离执行，异常 fail-closed 并自动销毁沙箱 | P0 | permission/spec.md |
| CORE-PERM-R4 | 权限判定 SHALL 与 coeffect 声明联动，越权/缺失一律拒绝执行 | P0 | permission/spec.md |

### 1.8 任务编排（orchestration）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-ORCH-R1 | 编排 SHALL 以状态机驱动任务，非法状态转移拒绝执行 | P0 | orchestration/spec.md |
| CORE-ORCH-R2 | 编排 SHALL 支持子任务拆解并按依赖拓扑执行 | P0 | orchestration/spec.md |
| CORE-ORCH-R3 | 编排 SHALL 支持多 Agent 路由与 TaskHandoff 上下文交接 | P1 | orchestration/spec.md |
| CORE-ORCH-R4 | 编排 SHALL 支持长任务挂起/恢复/取消（断点续跑） | P1 | orchestration/spec.md |

### 1.9 可观测性（observability）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-OBS-R1 | 系统 SHALL 输出结构化 JSONL 日志，并对敏感信息脱敏 | P0 | observability/spec.md |
| CORE-OBS-R2 | 系统 SHALL 聚合指标（完成率/token/循环数/错误率） | P0 | observability/spec.md |
| CORE-OBS-R3 | 每轮 loop SHALL 携带 trace_id 贯穿全链路，支持 replay 复现 | P0 | observability/spec.md |
| CORE-OBS-R4 | 遥测 SHALL 作为单一数据源，统一供给进化经验采集与审批审计 | P1 | observability/spec.md |

### 1.10 约束与容错（constraints）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CONS-R1 | 系统 SHALL 对工具输入做 schema 校验，对输出做结构化解析 | P0 | constraints/spec.md |
| CORE-CONS-R2 | 系统 SHALL 提供熔断/降级/重试/回滚容错中间件 | P0 | constraints/spec.md |
| CORE-CONS-R3 | 系统 SHALL 提供上下文压缩中间件，控制 token 预算 | P1 | constraints/spec.md |
| CORE-CONS-R4 | 约束 SHALL 作为横切中间件插入 loop 关键节点，可排序可配置 | P0 | constraints/spec.md |

### 1.11 技能封装（skills）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-SKILL-R1 | 系统 SHALL 维护原子技能库，技能有前置条件检查 | P0 | skills/spec.md |
| CORE-SKILL-R2 | 技能 SHALL 支持版本管理与灰度发布，A/B 退化自动回退 | P1 | skills/spec.md |
| CORE-SKILL-R3 | 技能路由 SHALL 按 Top-K 相似度匹配，未命中则沉淀为候选 | P0 | skills/spec.md |
| CORE-SKILL-R4 | 技能库 SHALL 作为 evolution 结晶/溶解的唯一交接面 | P0 | skills/spec.md |

### 1.12 上下文工程（context）

| ID | 需求描述 | 优先级 | 追踪规格 |
|---|---|---|---|
| CORE-CTX-R1 | 系统 SHALL 动态装配上下文并按 token 预算裁剪 | P0 | context/spec.md |
| CORE-CTX-R2 | 系统 SHALL 提供信息地图（目录索引 + 按需 fetch + hash 失效重建） | P0 | context/spec.md |
| CORE-CTX-R3 | 系统 SHALL 对多轮对话关键信息自动压实并写回记忆 | P0 | context/spec.md |
| CORE-CTX-R4 | 千页级文档 SHALL 以轻量索引呈现，不挤占有限上下文窗口 | P1 | context/spec.md |

---

## 2. 非功能需求（Non-Functional Requirements）

### 2.1 可观测性（Observability）

| ID | 需求 | 目标 | 追踪 |
|---|---|---|---|
| CORE-NFR-OBS1 | 所有副作用可追踪、可回放 | 100% 写操作有审计日志 | adr.md / test-plan |
| CORE-NFR-OBS2 | 结构化日志（trace-id 贯穿一轮 loop） | 单轮可复现 | test-plan |

### 2.2 性能（Performance）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-PERF1 | loop 单轮延迟（不含 LLM） | < 50ms |
| CORE-NFR-PERF2 | 记忆检索延迟 | < 100ms（1 万条事实规模） |
| CORE-NFR-PERF3 | 插件热插拔 | < 1s 完成加载/卸载 |

### 2.3 可靠性与安全（Reliability & Safety）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-REL1 | 进化回滚成功率 | 100% |
| CORE-NFR-SEC1 | 密钥/敏感文件 | 只引用不读取，禁止进入日志/记忆 |
| CORE-NFR-SEC2 | 不可逆操作（rm/写系统/杀进程） | 必须人工确认 |
| CORE-NFR-SEC3 | 爆炸半径控制 | 单次操作影响面可预估、可回退 |

### 2.4 可移植性 / 兼容性（Portability）

| ID | 需求 | 目标 |
|---|---|---|
| CORE-NFR-PORT1 | 运行环境 | Python 3.11+，跨 Linux/macOS/Windows |
| CORE-NFR-PORT2 | MCP 协议版本 | 兼容 MCP 最新稳定版 |

---

## 3. 需求优先级说明

- **P0（Must）**：MVP 验收必需，缺一不可。
- **P1（Should）**：MVP 应有，确有正当理由可延期。
- **P2（May）**：可选，后续迭代。

---

## 4. 关联文档

- 产品定义：`doc/00-product/product-definition.md`
- 规格（可追踪的唯一事实来源）：`doc/openspec/specs/*`
- 测试用例：`doc/04-testing/test-cases.md`
