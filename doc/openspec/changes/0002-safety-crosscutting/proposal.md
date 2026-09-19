# Change: Safety & Crosscutting Modules

## Why
六个主轴能力解决了"能跑起来"，但裸模型无约束执行仍存在失控风险，长周期复杂任务缺乏编排、可观测、容错与上下文治理。本变更新增六大横切模块，把 CORE-Harness 从"可运行"升级为"安全、可控、可复盘、可长跑"。

## What Changes
- 新增 `permission` 规格：分级权限体系、人工审批流、沙箱隔离。
- 新增 `orchestration` 规格：任务状态机、子任务拆解、多 Agent 协同。
- 新增 `observability` 规格：全链路日志、指标监控、链路追踪。
- 新增 `constraints` 规格：输入输出校验、容错中间件、上下文压缩。
- 新增 `skills` 规格：原子技能库、版本灰度 A/B、技能路由。
- 新增 `context` 规格：动态上下文构建、信息地图、上下文自动压实。

## Impact
- **Affected specs**: permission, orchestration, observability, constraints, skills, context（全部新增）
- **Affected specs (integration)**: loop（横切中间件插入）、tool-use（coeffect→权限联动）、memory（压实→context 联动）、evolution（结晶→skills 联动）
- **Affected code**: 无（纯规格阶段）
- **Dependencies**: 依赖 0001 主轴能力已就位
