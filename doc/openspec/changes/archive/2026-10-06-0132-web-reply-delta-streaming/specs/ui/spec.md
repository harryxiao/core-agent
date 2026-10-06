# ui — spec delta（change 0132）

## MODIFIED Requirements

### Requirement: Web 界面访问
系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送。
后端 SHALL 在 SPA 构建产物存在时将其挂载为站点根，并在**产物缺失时降级为纯 API 模式**（后端照常
可用，不因缺前端而启动失败）；静态挂载 SHALL NOT 遮蔽既有 REST/SSE 端点。

流式输出 SHALL 区分**增量帧**与**终态帧**：增量 SHALL 以**专类型**帧推送（载荷为增量文本），
终态结果 SHALL 以结果帧推送（载荷为完整结果）——两类帧 SHALL NOT 共用一个类型。前端消费增量帧
SHALL 以**文本追加**方式呈现（首帧新建、其后原地追加，终态帧收口），SHALL NOT 逐帧新建行，SHALL NOT
把载荷序列化为 JSON 文本展示。

实现：Svelte SPA

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

#### Scenario: 增量帧以文本追加（非逐帧 JSON）
- **GIVEN** Web 会话正在流式生成回复，后端逐段推送增量帧
- **WHEN** 前端消费这些增量帧
- **THEN** 增量文本**追加**到同一条回复中（不逐帧新建行、不逐帧渲染 JSON 载荷），终态帧收口为完整回复

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
