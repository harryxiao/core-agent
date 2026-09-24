Harness Host 常驻服务：单一 Host 进程常驻承载内核与多客户端，前端与后端解耦部署。（来源：探索 subagent 结论 + 用户决策，2026-09-21）

## ADDED Requirements

### Requirement: Harness Host 常驻服务
系统 SHALL 提供 Harness Host 常驻服务形态：单一 Host 进程常驻运行，承载 Core-Agent 内核并作为统一接入端点，支持多个 Web/Desktop 客户端并发接入，各客户端建立独立会话、互不串扰。

#### Scenario: 常驻 Host 多客户端接入
- **GIVEN** 一个 Harness Host 常驻进程已启动并承载内核
- **WHEN** 多个 Web/Desktop 客户端经统一后端 API 连接该 Host
- **THEN** 各客户端各自建立独立会话并可并发会话，互不串扰

#### Scenario: 统一接入端点
- **GIVEN** Harness Host 常驻进程已启动
- **WHEN** 任一客户端发起连接
- **THEN** 客户端经统一接入端点建立会话，无需各自拉起后端进程

