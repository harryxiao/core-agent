## MODIFIED Requirements

### Requirement: 模型调用可靠性
系统 SHALL 保障模型调用的可靠性：调用失败自动重试（retry，指数退避）、超时（timeout）控制、服务降级（degrade 切换备用 provider/model）、底层连接复用（connection reuse / keep-alive）、流式（stream）响应断流可恢复。
超时阈值与最大重试次数 SHALL 有**明确的实现缺省**（单次调用 `60.0` 秒、最多重试 `3` 次），
且 SHALL 可经配置（`llm.timeout` / `llm.max_retries`，口径见 configuration「LLM 提供商配置（必选）」）
覆盖并由组合根注入实现；**未配置时** SHALL 取该缺省，行为与既有实现**逐字一致**。

#### Scenario: 失败自动重试
- **GIVEN** 模型调用因网络抖动或瞬时错误失败
- **WHEN** 错误可重试
- **THEN** 按指数退避自动 retry，达到最大重试次数仍失败则抛出归一化异常

#### Scenario: 调用超时控制
- **GIVEN** 发起 completion / stream / embedding 调用
- **WHEN** 响应超过 timeout 阈值
- **THEN** 判定调用超时，取消等待并释放该次调用占用资源

#### Scenario: 服务降级
- **GIVEN** 主 provider/model 不可用或持续超时
- **WHEN** 触发降级条件
- **THEN** 自动 degrade 切换到备用 provider/model，保证调用链路不中断

#### Scenario: 连接复用
- **GIVEN** 多次连续模型调用
- **WHEN** 发起请求
- **THEN** 复用底层 connection / keep-alive 连接，减少握手开销，连接失效时自动重建

#### Scenario: 流式断流处理
- **GIVEN** stream 流式响应进行中
- **WHEN** 流意外中断
- **THEN** 判定断流，已接收内容可部分返回或触发重试，避免调用方无限挂起

#### Scenario: 超时与重试缺省不变且可配置覆盖
- **GIVEN** 未注入 `timeout` / `max_retries`，或注入配置解析所得的值（如 `30.0` / `1`）
- **WHEN** 构造 LLM 实现并发出调用
- **THEN** 未注入时取缺省单次超时 `60.0` 秒、最多重试 `3` 次（与既有实现**逐字一致**）；
  注入后以注入值生效（单次等待上限与重试次数随之改变）
