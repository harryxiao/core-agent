Web Client 分离：Web 前端作为纯静态资源独立托管，经统一后端 API 连接常驻 Harness Host 后端，前后端解耦部署。（来源：探索 subagent 结论 + 用户决策，2026-09-21）

## ADDED Requirements

### Requirement: Web Client 分离
系统 SHALL 支持 Web 前端作为纯静态资源独立托管，与常驻 Harness Host 后端解耦部署：前端经统一后端 API 连接 Host，前端升级不要求后端重启。

#### Scenario: 纯静态独立托管
- **GIVEN** Web SPA 构建产物
- **WHEN** 部署到任意静态托管
- **THEN** 前端可加载并连接常驻 Harness Host 后端 API 正常会话

#### Scenario: 前后端解耦升级
- **GIVEN** Web Client 与 Host 后端独立部署
- **WHEN** 前端发布新版本
- **THEN** 前端可独立升级，无需重启 Host 后端（后端 API 兼容时）
