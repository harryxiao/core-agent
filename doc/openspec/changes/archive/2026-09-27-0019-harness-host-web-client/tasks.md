# Tasks

## 1. Harness Host 常驻服务（P0）

- [x] 1.1 在 deployment spec 追加 R5「Harness Host 常驻服务」Requirement（常驻进程 + 统一接入端点 + 多客户端独立会话）
- [x] 1.2 在模块文档 deployment.md 同步 Host 常驻形态描述
- [x] 1.3 在接口文档 deployment-interface.md 同步 Host 接入端点

## 2. Web Client 分离（P0）

- [x] 2.1 在 ui spec 追加 R9「Web Client 分离」Requirement（纯静态独立托管 + 后端 API 连接 Host）
- [x] 2.2 在接口文档 ui-interface.md 同步 Web Client 与 Host 分离接口

## 3. 同步与决策（P0）

- [x] 3.1 在 requirements.md 1.20 节追加 CORE-DEP-R5 行 + 1.13 节追加 CORE-UI-R9 行
- [x] 3.2 在 adr.md 追加 ADR-0031「单进程多会话进程模型」+ 变更追踪表末尾行
