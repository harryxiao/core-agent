# 测试设计：测试计划（Test Plan）

> 版本 v0.1 ｜ 本文给出整体测试策略；具体用例见 `test-cases.md`。
> 规格 → 需求 → 测试三者同号追踪，确保**规格可验证**（SDD 核心）。

---

## 1. 测试策略（Test Strategy）

| 层级 | 目标 | 覆盖内容 | 工具 |
|---|---|---|---|
| **单元测试** | 每个插件/接口的契约符合性 | schema、coeffect、undo、错误码 | pytest |
| **集成测试** | 层间协作 | L0↔L1、L1↔L2、L3 装配 | pytest |
| **规格测试（BDD）** | 规格 Scenarios 逐条验证 | 每个 GIVEN/WHEN/THEN | pytest-bdd / behave |
| **留出评测** | 进化不退化、不拟合 | held-out 集 | evolution runner |
| **端到端（E2E）** | 真实任务走通全链路 | 一个完整 agent 任务 | 手动 + 脚本 |

---

## 2. 测试覆盖矩阵（追踪）

| 需求 ID | 用例组 | 测试层级 |
|---|---|---|
| CORE-PLG-R1~R4 | TC-PLG-* | 单元 + 集成 |
| CORE-LOOP-R1~R4 | TC-LOOP-* | 集成 + BDD |
| CORE-MEM-R1~R4 | TC-MEM-* | 单元 + 集成 + 留出 |
| CORE-TOOL-R1~R4 | TC-TOOL-* | 单元 + 集成 |
| CORE-MCP-R1~R4 | TC-MCP-* | 集成 + E2E |
| CORE-EVO-R1~R4 | TC-EVO-* | 集成 + 留出 |
| CORE-PERM-R1~R4 | TC-PERM-* | 单元 + 集成 + 安全 |
| CORE-ORCH-R1~R4 | TC-ORCH-* | 集成 + E2E |
| CORE-OBS-R1~R4 | TC-OBS-* | 单元 + 集成 + 专项 |
| CORE-CONS-R1~R4 | TC-CONS-* | 单元 + 集成 |
| CORE-SKILL-R1~R4 | TC-SKILL-* | 单元 + 集成 + 留出 |
| CORE-CTX-R1~R4 | TC-CTX-* | 单元 + 集成 |
| CORE-UI-R1~R6 | TC-UI-* | 集成 + E2E |
| CORE-IM-R1~R6 | TC-IM-* | 集成 + E2E + 安全 |
| CORE-LLM-R1~R5 | TC-LLM-* | 单元 + 集成 |
| CORE-NFR-* | TC-NFR-* | 专项（性能/安全/可观测） |

---

## 3. 可观测性测试

- 每个写操作必须产生审计日志（`EffectTracker.audit` 可查）。
- 每轮 loop 有 `trace_id`，可复现单轮（重放）。

## 4. 性能测试目标（对齐 NFR）

| 项 | 目标 | 测试方法 |
|---|---|---|
| loop 单轮（不含 LLM） | < 50ms | 打桩模型，循环 1k 轮取 P95 |
| 记忆检索 | < 100ms（1 万条） | 预置 1 万条事实 |
| 插件热插拔 | < 1s | load/unload 计时 |

## 5. 安全测试

- 密钥只引用不读取：检查日志/记忆无密钥明文。
- 不可逆操作必触发确认门：模拟 rm/杀进程，断言被阻断。

## 6. 留出评测（进化安全）

- 留出集与进化数据**不相交**，来源隔离。
- 每次进化候选在留出集上评分，退化即回滚。

---

## 7. 验收标准（Definition of Done）

1. 所有 P0 需求对应的规格 Scenarios 全部通过。
2. 覆盖矩阵无空缺（每条需求有至少 1 个用例）。
3. 关键路径（单轮 loop + 一次进化循环）E2E 通过。
4. NFR 性能/安全项达标。

---

## 8. 关联

- 测试用例：`doc/04-testing/test-cases.md`
- 需求：`doc/00-product/requirements.md`
- 规格：`doc/openspec/specs/*`
