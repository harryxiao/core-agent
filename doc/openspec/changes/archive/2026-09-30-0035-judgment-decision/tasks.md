# Tasks

## 1. spec 契约（P0）

- [x] 1.1 ADDED「决策原语路由」choice/score/noul 三类原语
- [x] 1.2 ADDED「JEV 提供方接入」OpenAI 兼容端点挂 /v1/systemone
- [x] 1.3 ADDED「置信度回退」低置信度回退主 LLM
- [x] 1.4 ADDED「决策审计」决策轨迹落 observability
- [x] 1.5 ADDED「决策模型配置」judgment 配置项纳入 ConfigSpec

## 2. 提供方接入接线（M2，P1）

- [x] 2.1 JEVProvider：懒 import，经 api_key/base_url/model 建 HTTP 客户端
- [x] 2.2 适配 System One 协议：state + typed questions → typed answers + probability + confidence
- [x] 2.3 新增 ConfigSpec：judgment.provider / judgment.model / judgment.base_url / judgment.api_key（HIDDEN）/ judgment.confidence_threshold

## 3. 决策点接线（M2，P1）

> 注：DecisionRouter / Compactor / Guardrail 三组件本 Phase 已落地并各提供 choice/score/noul 原语；loop/memory/permission 三决策点的实际 DI 接线为后续 Phase（本 Phase 仅交付组件 + 原语抽象）。

- [x] 3.1 DecisionRouter：AgentLoop 决策点用 choice 原语
- [x] 3.2 Compactor：记忆压实用 score 原语
- [x] 3.3 Guardrail：约束守卫用 noul 原语

## 4. 置信度回退（M2，P1）

- [x] 4.1 阈值判定：confidence 低于阈值回退主 LLM
- [x] 4.2 回退轨迹标注，供审计
