# Tasks

## 1. spec 契约（P0）

- [x] 1.1 ADDED「MCP 客户端消费安全」三场景（stdio 沙箱 / http 白名单 / 不可逆确认）
- [x] 1.2 MODIFIED「MCP Server 安装与移除」覆盖本地 stdio + 远端 http 两类来源

## 2. transport 生产实现接线（M2，P1）

- [ ] 2.1 stdio transport：**stdlib 手写**（`asyncio` + `json` + `create_subprocess_exec`，零新依赖），拉起本地子进程
- [ ] 2.2 http / streamable-http transport：**懒 import `mcp` SDK**（optional extra `[mcp]`），连接 + `Mcp-Session-Id` 复用

## 3. client 安装分流（P1）

- [ ] 3.1 `MCPClient.add` 按 transport 分流构建 `MCPEndpoint`（stdio `command+args` / http `url+headers`）

## 4. 消费侧安全接线（P1）

- [ ] 4.1 本地 stdio 子进程过 `SandboxManager`（资源配额 + 受限文件系统 + 出站白名单）
- [ ] 4.2 远端 http 请求走出站网络白名单校验
- [ ] 4.3 `MCPToolAdapter` 标注 coeffects / `reversible=False`，确认门 + 审计

## 5. 验证（P0）

- [ ] 5.1 openspec validate --all 全绿
- [ ] 5.2 测试：stdio 沙箱越界拒绝 / http 白名单拒绝 / 不可逆工具确认 / add 分流
