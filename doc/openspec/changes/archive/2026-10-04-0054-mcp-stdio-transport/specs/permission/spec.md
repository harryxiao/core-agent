# permission spec delta — mcp-stdio-transport

沙箱管理器增「以资源配额拉起**常驻**子进程」能力（长连接消费者用，如本地 stdio MCP 服务端），
与既有一次性执行 `run` 互补，共享同一 rlimit 施加路径。（来源：MCP stdio 传输消费侧沙箱接线，2026-10-04）

## MODIFIED Requirements

### Requirement: 沙箱隔离
系统 SHALL 在独立沙箱环境中执行代码/Shell，执行完成后自动销毁，不污染宿主系统。

#### Scenario: 沙箱内执行与销毁
- **GIVEN** 一个代码执行请求被放行
- **WHEN** 沙箱管理器执行该请求
- **THEN** 代码在受限沙箱中运行，结束后沙箱自动销毁且无残留

#### Scenario: 沙箱不可用
- **GIVEN** 沙箱环境启动失败
- **WHEN** 需要执行代码操作
- **THEN** 操作阻断并返回 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑

#### Scenario: 沙箱销毁与资源回收
- **GIVEN** 沙箱内执行结束或异常终止
- **WHEN** 沙箱管理器销毁该沙箱实例
- **THEN** 进程被终止、CPU/内存/磁盘配额释放、临时挂载与网络规则清理，无残留进程或资源泄漏

#### Scenario: 常驻子进程受配额约束
- **GIVEN** 一个长连接型消费者需在沙箱内**常驻**运行（如本地 stdio MCP 服务端）
- **WHEN** 沙箱管理器以资源配额拉起该常驻子进程
- **THEN** 进程按 rlimit（内存/CPU）约束运行，句柄归调用方持有并在其销毁时终止；拉起失败降级 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑
