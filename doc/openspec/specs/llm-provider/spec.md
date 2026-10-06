# LLM Provider Specification

## Purpose

LLM Provider（三方大模型归一化接入）让 core-agent 通过统一 LLMProvider 抽象接口调用任意三方大模型：配置任意模型 API Key 与 URL 即自动路由接入，StdlibLLMProvider（OpenAI 兼容 stdlib）作默认实现、经依赖注入隔离可无缝替换或自研，调用方零改动。接口同步（completion / stream / embedding）与异步（acompletion / astream / aembedding）同构：异步为主、同步为薄壳，支持事件循环内非阻塞与真并发调用。

## Requirements

### Requirement: LLMProvider 抽象接口
系统 SHALL 提供统一的 LLMProvider 抽象接口（completion / stream / embedding 三个入口与统一请求 / 响应模型），内核只依赖该接口、不感知具体供应商实现。

#### Scenario: 统一接口调用
- **GIVEN** 内核 loop 需要调用大模型
- **WHEN** 经 LLMProvider 接口发起请求
- **THEN** 内核无需关心底层供应商协议，仅面向统一请求 / 响应模型

### Requirement: 默认实现与配置归一化
系统 SHALL 提供 OpenAI 兼容 stdlib 默认实现，任意 OpenAI 兼容 API Key + URL 配置即路由到对应端点，无需逐家编写适配代码。
响应归一化 SHALL **保留推理原文（thinking）**：统一响应模型 `LLMResponse` 与流式增量 `LLMChunk` SHALL 各携带 `thinking` 字段（provider 归一化后的推理文本；端点未返回该字段时为空串，SHALL NOT 以缺省值报错）。归一化 SHALL 覆盖**两家既有口径** —— 智谱 GLM 系与 OpenAI 兼容端点在非流式 `message` 与流式 `delta` 上的推理字段（`reasoning_content` / `reasoning`），流式 SHALL 逐 delta 同口径归一。
`thinking` SHALL NOT 掺入 `content`（回复正文与推理原文分属两字段，SHALL NOT 互相拼接），SHALL NOT 改变 `tool_calls` / `usage` / `finish_reason` 的既有解析。

#### Scenario: 任意三方模型接入
- **GIVEN** 用户配置某三方模型的 API Key 与 URL
- **WHEN** 发起模型调用
- **THEN** 系统自动解析并路由到对应 provider 协议，返回归一化结果

#### Scenario: 原生工具调用解析
- **GIVEN** 请求携带工具（tools 字段）且端点以原生 tool_calls 形式返回（而非 system prompt 约定的 content JSON）
- **WHEN** 收到补全响应或流式增量
- **THEN** 系统把 message.tool_calls / delta.tool_calls 片段归一为 ToolCall（流式按 index 累积 name 与 arguments），上层 planner 据此产出工具 Action，content 协议与原生协议并存兼容

#### Scenario: 推理原文归一（流式与非流式同口径）
- **GIVEN** 端点返回推理原文（`reasoning_content` 或 `reasoning`）
- **WHEN** 该字段出现在非流式响应的 `message` 中，或出现在流式增量的 `delta` 中
- **THEN** 归一化后 `LLMResponse.thinking` / `LLMChunk.thinking` 携带该推理文本，且 `content` 逐字不受影响（两者分属两字段、互不拼接）

#### Scenario: 端点未返回推理字段时为空串
- **GIVEN** 端点响应不含任何推理字段（既有行为）
- **WHEN** 归一化该响应或增量
- **THEN** `thinking` 为空串，`content` / `tool_calls` / `usage` / `finish_reason` 的解析与既有实现**逐字一致**（零回归）

### Requirement: 依赖注入可替换
系统 SHALL 通过依赖注入隔离 LLMProvider 实现，替换默认实现或接入自研后端时，内核 loop 及所有调用方无需改动即可切换。

#### Scenario: 替换底层实现
- **GIVEN** 需要替换默认实现为自研或其他后端
- **WHEN** 注册新的 Provider 实现
- **THEN** 内核 loop 及所有调用方无需改动即可切换

### Requirement: 错误归一化
系统 SHALL 将超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义。

#### Scenario: 底层异常归一
- **GIVEN** 底层供应商返回超时 / 限流 / 鉴权等不同错误
- **WHEN** 调用失败
- **THEN** 统一映射为对应领域异常，不泄漏供应商原始错误结构

### Requirement: 模型调用审计
系统 SHALL 对模型调用做可观测审计，标注 provider / model 与调用结果，复用既有 observability 链路。

#### Scenario: 调用留痕
- **GIVEN** 任意一次模型调用
- **WHEN** 调用结束
- **THEN** 审计记录标注 provider / model 与结果，可追溯

### Requirement: 模型调用可靠性
系统 SHALL 保障模型调用的可靠性：调用失败自动重试（retry，指数退避）、超时（timeout）控制、服务降级（degrade 切换备用 provider/model）、底层连接复用（connection reuse / keep-alive）、流式（stream）响应断流可恢复。

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

### Requirement: 异步调用接口
系统 SHALL 提供异步调用入口 acompletion / astream / aembedding，与同步入口（completion / stream / embedding）共用统一请求 / 响应模型；异步入口支持事件循环内非阻塞调用与真并发，同步入口保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

#### Scenario: 异步调用入口
- **GIVEN** 内核 loop 运行于事件循环中，需并发调用多个大模型
- **WHEN** 经 acompletion / astream / aembedding 发起请求
- **THEN** 调用不阻塞事件循环，返回 awaitable / 异步迭代器，多个调用可并发执行

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 completion / stream / embedding 同步入口
- **THEN** 语义与对应异步入口一致，内部经事件循环桥接（asyncio.run）完成调用，调用方无需改动、无需感知事件循环

#### Scenario: 真并发执行
- **GIVEN** 多个相互独立的模型调用
- **WHEN** 经异步入口并发发起
- **THEN** 各调用真并发执行（非串行阻塞），总耗时约等于最慢单个调用而非各调用耗时之和
