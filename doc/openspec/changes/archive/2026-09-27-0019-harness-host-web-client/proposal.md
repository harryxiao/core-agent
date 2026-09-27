# Change: Harness Host 常驻服务 + Web Client 分离

## Why

ui capability 现有 R1「三模统一内核启动」下，Web/Desktop 前端以「与后端同机运行」方式接入内核，缺少一个可常驻、可独立托管的 Host 后端承载多客户端并发接入。当多个 Web/Desktop 客户端需同时接入同一 Core-Agent 实例时，缺乏统一的常驻进程形态：每个前端各自拉起后端会导致资源重复与状态割裂。引入 Harness Host 常驻服务（deployment）与 Web Client 分离形态（ui），将前端与后端解耦部署：单一 Host 进程常驻承载多个客户端，各客户端建立独立会话、互不串扰。

## What Changes

- 扩展 `deployment` capability：ADDED R5「Harness Host 常驻服务」——系统 SHALL 提供常驻 Host 服务形态，以单一常驻进程承载 Core-Agent 内核并对外暴露统一接入端点，多客户端并发接入各自建立独立会话
- 扩展 `ui` capability：ADDED R9「Web Client 分离」——系统 SHALL 支持 Web 前端以纯静态资源独立托管，通过统一后端 API 连接远程或本机 Harness Host，前端与后端解耦部署、独立升级
- 新增 ADR-0031「单进程多会话进程模型」——记录单一 Host 进程内多会话隔离的进程模型决策

## Impact

- **Affected specs**：扩展 `deployment`（ADDED R5 Harness Host 常驻服务）、`ui`（ADDED R9 Web Client 分离）
- **Affected docs**：`specs/deployment/spec.md`、`specs/ui/spec.md`、`00-product/requirements.md`（1.20 节追加 CORE-DEP-R5 行 + 1.13 节追加 CORE-UI-R9 行）、`02-modules/deployment.md`、`03-interfaces/deployment-interface.md`、`03-interfaces/ui-interface.md`、`01-architecture/adr.md`（追加 ADR-0031）
- **Affected code**：无（本 change 声明部署形态与进程模型，不涉及具体实现代码）
- **Dependencies**：复用 mcp R7「会话与调用隔离」的应用层会话隔离语义、0018 R8「会话多流复用」的单连接多会话能力
