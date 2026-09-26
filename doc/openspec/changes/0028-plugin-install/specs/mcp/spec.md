# MCP Specification

## Purpose
MCP（Model Context Protocol）集成层为智能体提供双向模型上下文协议能力：作为 client 消费外部 tools/resources/prompts（工具/资源统一外部入口），作为 server 对外暴露自身 L1 工具与技能（供外部 Agent 挂载复用），二者共用同一内核安全链路；并支持运行时安装与移除 MCP 服务端（复用统一插件来源）。

## ADDED Requirements

### Requirement: MCP Server 安装与移除
系统 SHALL 支持在运行时安装与移除 MCP 服务端：安装复用插件来源（mcp-endpoint）经 discover → verify → install → register 进入现有连接管理；移除经 deactivate → uninstall 释放连接资源。

#### Scenario: 运行时安装 MCP Server
- **GIVEN** 一个 MCP 服务端来源（mcp-endpoint）
- **WHEN** 执行 mcp add
- **THEN** 安装并注册该 MCP 服务端，进入现有连接管理，其工具可被动态发现

#### Scenario: 移除 MCP Server
- **GIVEN** 一个已安装的 MCP 服务端
- **WHEN** 执行 mcp remove
- **THEN** 停用并卸载该服务端，释放连接/会话/socket 资源，相关工具标记不可用
