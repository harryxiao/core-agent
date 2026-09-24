# 测试策略（Test Strategy）

> 版本 v0.1 ｜ 本文定义 CORE-Harness 测试方法论的三大支柱：**测试金字塔**、**可逆效应性质测试**、**留出评测**。
> 具体层级/环境/进出准则/责任人见 `04-testing/test-plan.md`；逐条用例见 `04-testing/test-cases.md`（与规格 Scenario 同号，实现"规格 → 需求 → 测试"同号追踪）。

---

## 1. 测试金字塔（Test Pyramid）

按成本与隔离度由低到高分层，**底层多、顶层少**：越靠近底层越贴近"契约"，越靠近顶层越贴近"真实行为"。

| 层级 | 占比 | 目标 | 覆盖内容 | 工具 |
|---|---|---|---|---|
| **单元测试** | ~70% | 每个插件/接口的契约符合性 | schema、coeffect、undo、错误码、参数校验 | pytest + hypothesis |
| **集成测试** | ~20% | 层间协作与装配 | L0↔L1、L1↔L2、L3 装配、中间件链 | pytest |
| **规格测试（BDD）** | ~7% | 规格 Scenarios 逐条验证 | 每个 GIVEN/WHEN/THEN | pytest-bdd / behave |
| **端到端（E2E）** | ~3% | 真实任务走通全链路 | 一个完整 agent 任务（单轮 loop + 一次进化循环） | 手动 + 脚本 |
| **专项测试** | 定量不占比 | NFR 达标 | 性能 / 安全 / 可观测 / 留出 | 见 test-plan 4–6 章 |

**原则**：能用单元测的不上集成，能用集成测的不上 E2E；E2E 只保关键路径不断。

---

## 2. 可逆效应性质测试（Reversible Effect Property Testing）

### 2.1 为什么测"性质"而非"逐例"

CORE-Harness 的 L0 基底提供**可逆效应追踪**：一切写操作先记录 undo 再执行，可回滚。逐条枚举副作用太脆，
真正要保证的是几条**不变量（性质）**——对任意满足前置条件的操作都成立。性质测试以属性化方式
（随机输入 + 不变量断言）替代手写海量用例，覆盖面远大于逐例枚举。

### 2.2 可逆性

- **性质**：对任意写操作 `f`，存在其逆 `f⁻¹`（undo），满足 `apply(f) ∘ undo(f) = identity`（状态恢复原状）。
- **验证**：随机生成写操作序列，逐一 apply 再逆序 undo，断言状态（文件内容 / 记忆事实 / 注册表）与执行前逐字节一致。

### 2.3 幂等性

- **性质**：undo 幂等——对同一操作重复 undo 不产生额外副作用。
- **验证**：undo 两次与 undo 一次，断言最终状态相同且无新增审计副作用。

### 2.4 可观测性

- **性质**：每个写操作必产生审计记录（`EffectTracker.audit` 可查），且无密钥明文落日志。
- **验证**：任意写操作后审计流必有对应记录；全量扫描日志 / 记忆无密钥明文（对齐 NFR-SEC1）。

### 2.5 前置条件完备性

- **性质**：声明 coeffect 但环境未注入 → 返回 `COEFFECT_MISSING`，拒绝执行，不产生副作用。
- **验证**：对每个插件遍历其声明的 coeffect，逐个缺失注入，断言拒绝且状态不变。

---

## 3. 留出评测（Held-out Evaluation）

进化引擎（L4）的**安全护栏**：防止"进化"变成"过拟合 + 退化"。

### 3.1 数据隔离

- 留出集与进化数据**不相交**，来源隔离（不同任务 / 场景 / 时段）。
- 留出集只读，永不参与任何训练 / 结晶 / 技能生成。

### 3.2 退化拦截

- 每次进化候选（新技能 / 新插件 / SOP 变更）在留出集上评分；
- 若候选在留出集上**差于基线**（退化），自动回滚，不并入生产。

### 3.3 防拟合

- 进化打分只看留出集（而非训练集）指标；
- 连续 N 次"训练集涨、留出集平/跌"触发过拟合告警，暂停进化并评审。

### 3.4 与测试的关系

- 留出评测是 E2E 之上的长期回归层，运行于 evolution runner；
- 与 TC-EVO-*、TC-MEM-*、TC-SKILL-* 的留出用例同源。

---

## 4. 三支柱与需求追踪

| 支柱 | 覆盖需求 | 用例组 |
|---|---|---|
| 测试金字塔 | 全部 FR / NFR | 全部 TC-* |
| 可逆效应性质测试 | CORE-PLG-R2、CORE-TOOL-R3、CORE-OBS-R1 | TC-PLG-02/05、TC-TOOL-03/05、TC-OBS-01 |
| 留出评测 | CORE-EVO-R*、CORE-MEM-R*、CORE-SKILL-R* | TC-EVO-*、TC-MEM-*、TC-SKILL-* |

### 4.1 重点模块展开（UI / IM / LLM / COMP / DIST）

| 模块 | 关键需求 | 测试重点（按金字塔层级） | 用例组 |
|---|---|---|---|
| CORE-UI（CLI/Web/Desktop 三模桥接） | CORE-UI-R1~6 | 单元：统一后端 API + SSE 6 事件契约、三模消息编解码；E2E：三模各跑通一条完整会话 | TC-UI-01~09 |
| CORE-IM（wechat/feishu/telegram/discord 网关） | CORE-IM-R1~6 | 集成：长连接重连/幂等、多平台适配器隔离；E2E：一条消息进出→单轮 loop | TC-IM-01~11 |
| CORE-LLM（任意三方模型归一化） | CORE-LLM-R1~5 | 单元：llm-provider 适配器契约、API KEY/URL 解析；性质：幂等、审计、无密钥明文 | TC-LLM-01~05 |
| CORE-COMP（组合与分发） | CORE-COMP-R1~4 | 单元：profile 命名组合 / bundle 分发格式 / patch.yml 局部覆盖 / 层叠解析契约；性质：可逆组合、可回退 | TC-COMP-01~04 |
| CORE-DIST（分布式协作） | CORE-DIST-R1~7 | 集成：A2A 双向互调 / AgentCard 发现与签名 / 三种协议绑定 / 四类设备拓扑角色；安全：最小权限 scope 鉴权；E2E：跨设备委派单轮 loop | TC-DIST-01~12 |


### 4.2 模块覆盖矩阵（21 模块，NFR 另计）

与 `test-plan.md` §2 对齐：全部 21 个业务模块均有需求与用例覆盖，NFR 专项另计。

| 模块 | 需求 | 测试层级 | 用例组 |
|---|---|---|---|
| CORE-PLG（插件注册与组合） | CORE-PLG-R1~R4 | 单元 + 集成 | TC-PLG-* |
| CORE-LOOP（智能体循环） | CORE-LOOP-R1~R4 | 集成 + BDD | TC-LOOP-* |
| CORE-MEM（分层记忆） | CORE-MEM-R1~R4 | 单元 + 集成 + 留出 | TC-MEM-* |
| CORE-TOOL（工具使用） | CORE-TOOL-R1~R4 | 单元 + 集成 | TC-TOOL-* |
| CORE-MCP（MCP 集成） | CORE-MCP-R1~R9 | 集成 + E2E | TC-MCP-* |
| CORE-EVO（进化引擎） | CORE-EVO-R1~R4 | 集成 + 留出 | TC-EVO-* |
| CORE-PERM（权限与审批管控） | CORE-PERM-R1~R4 | 单元 + 集成 + 安全 | TC-PERM-* |
| CORE-ORCH（任务编排） | CORE-ORCH-R1~R7 | 集成 + E2E | TC-ORCH-* |
| CORE-OBS（可观测性） | CORE-OBS-R1~R5 | 单元 + 集成 + 专项 | TC-OBS-* |
| CORE-CONS（约束与容错） | CORE-CONS-R1~R4 | 单元 + 集成 | TC-CONS-* |
| CORE-SKILL（技能封装） | CORE-SKILL-R1~R5 | 单元 + 集成 + 留出 | TC-SKILL-* |
| CORE-CTX（上下文工程） | CORE-CTX-R1~R4 | 单元 + 集成 | TC-CTX-* |
| CORE-UI（前端） | CORE-UI-R1~R9 | 集成 + E2E | TC-UI-* |
| CORE-IM（IM 网关） | CORE-IM-R1~R6 | 集成 + E2E + 安全 | TC-IM-* |
| CORE-LLM（三方模型归一化） | CORE-LLM-R1~R6 | 单元 + 集成 | TC-LLM-* |
| CORE-COMP（组合与分发） | CORE-COMP-R1~R4 | 单元 + 集成 | TC-COMP-* |
| CORE-DIST（分布式协作） | CORE-DIST-R1~R8 | 集成 + E2E + 安全 | TC-DIST-* |
| CORE-RAG（检索增强生成） | CORE-RAG-R1~R6 | 单元 + 集成 | TC-RAG-* |
| CORE-GIT（版本控制） | CORE-GIT-R1~R5 | 单元 + 集成 + 安全 | TC-GIT-* |
| CORE-DEP（部署与托管） | CORE-DEP-R1~R6 | 单元 + 集成 + E2E | TC-DEP-* |
| CORE-PROF（核心画像） | CORE-PROF-R1~R7 | 单元 + 集成 | TC-PROF-* |
| CORE-NFR（NFR，另计） | CORE-NFR-* | 专项（性能/安全/可观测） | TC-NFR-* |

---

## 5. 关联

- 测试计划（层级 / 环境 / 进出准则 / 责任人）：`04-testing/test-plan.md`
- 测试用例（逐条对齐规格场景）：`04-testing/test-cases.md`
- 需求：`00-product/requirements.md`
- 规格：`openspec/specs/*`
