# UI Specification Delta

## MODIFIED Requirements

### Requirement: Web 界面访问
系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送。
后端 SHALL 在 SPA 构建产物存在时将其挂载为站点根，并在**产物缺失时降级为纯 API 模式**（后端照常
可用，不因缺前端而启动失败）；静态挂载 SHALL NOT 遮蔽既有 REST/SSE 端点。

实现：Svelte SPA

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

#### Scenario: SSE 断线重连
- **GIVEN** Web 会话的 SSE 流式连接因网络抖动或服务端重启而断开
- **WHEN** 连接中断
- **THEN** 客户端按指数退避自动重连并恢复流式推送，期间以心跳探测连接存活，避免流式输出卡死

#### Scenario: 未构建前端时降级为纯 API
- **GIVEN** 后端以 `serve` 启动，而 SPA 构建产物不存在
- **WHEN** 服务就绪
- **THEN** 服务照常启动，REST/SSE 端点全部可达（不因缺前端而失败）

#### Scenario: 静态挂载不遮蔽端点
- **GIVEN** SPA 构建产物已挂载为站点根
- **WHEN** 客户端请求既有 REST 端点（如 `GET /llm-config`）
- **THEN** 返回该端点的 JSON 响应，不被静态文件兜底吞掉

### Requirement: 桌面打包
系统 SHALL 支持将桌面端打包为可执行安装文件（Windows / macOS / Linux），并内置拉起本地后端的能力。
桌面壳 SHALL 复用与 Web 相同的 SPA 构建产物，且 sidecar 拉起 SHALL 由 `DesktopBridge` 实现
（spawn 本地后端进程），壳仅负责开窗口 / 挂 SPA / 启 sidecar。

实现：Tauri 壳 + sidecar

#### Scenario: 安装包运行
- **GIVEN** 用户安装桌面安装包
- **WHEN** 启动应用
- **THEN** 桌面壳自动拉起本地后端，加载同一 SPA 并可正常会话

#### Scenario: sidecar 拉起
- **GIVEN** 桌面入口启动
- **WHEN** 调用 sidecar 拉起
- **THEN** 以本地后端进程形式 spawn（不经 shell 解释执行、参数逐项传递），失败以结构化错误报告而非静默成功
