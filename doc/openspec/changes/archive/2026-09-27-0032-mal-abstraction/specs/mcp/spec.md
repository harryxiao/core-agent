传输层抽象与依赖注入隔离：底层 MCP 传输实现经 Transport 抽象接口隔离，MCPClient 与 MCPServer 只依赖抽象，替换 SDK 或传输实现调用方零改动。（来源：架构审计 MAL 约定，2026-09-27）

## ADDED Requirements

### Requirement: 传输层抽象与依赖注入隔离
系统 SHALL 通过 Transport 抽象接口隔离底层 MCP 传输实现（stdio/http/streamable-http 的 SDK 或 JSON-RPC 实现），MCPClient 与 MCPServer 只依赖该抽象；替换底层传输实现或 MCP SDK 时，调用方零改动。

#### Scenario: 替换传输实现
- **GIVEN** 需要替换底层 MCP 传输实现（如官方 SDK → 自研 JSON-RPC）
- **WHEN** 注册新的 Transport 实现
- **THEN** MCPClient / MCPServer 及所有调用方无需改动即可切换
