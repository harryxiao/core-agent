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
`LLMResponse.provider` SHALL 反映**实际使用的 provider 标识**：实现 SHALL 接受构造期注入的
provider 名（组合根按 `llm.provider` 注入），并 SHALL NOT 硬编码字面量；注入值为空（未提供）时
SHALL 回落实现自身的身份标识（`"stdlib"`）。这样「审计标签」与配置面所见一致，不再是与
`llm.provider` 无关的常量。

#### Scenario: 调用留痕
- **GIVEN** 任意一次模型调用
- **WHEN** 调用结束
- **THEN** 审计记录标注 provider / model 与结果，可追溯

#### Scenario: 审计标签反映配置的 provider
- **GIVEN** 组合根按 `llm.provider: litellm` 构造 stdlib 实现
- **WHEN** 该实现完成一次补全
- **THEN** `LLMResponse.provider` 为 `"litellm"`（配置面所见即响应面所见）；未注入 provider 时
  仍为 `"stdlib"`（与既有行为**逐字一致**）
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
### Requirement: 流式增量携带终止原因

流式增量模型 `LLMChunk` SHALL 携带 `finish_reason` 字段（字符串；该增量块未携带该信息时为空串，
SHALL NOT 以缺省值报错）。provider 归一化 SHALL 从流式增量块的 `choices[0].finish_reason` 取值
（OpenAI 兼容端点通常在**末块**携带，取值如 `stop` / `length`），SHALL NOT 因该字段缺失而丢弃该块
或改写其余字段。归一化 SHALL NOT 改变 `content` / `tool_calls` / `thinking` 的既有语义，
亦 SHALL NOT 改变非流式 `LLMResponse.finish_reason` 的既有解析。

「终止原因」是消费方（如循环的推理解析）判定**输出是否被 provider 截断**的权威信号；
该字段 SHALL 仅供归因与提示，SHALL NOT 参与内容拼装。

#### Scenario: 流式末块携带终止原因

- **GIVEN** provider 流式返回若干增量块，其中末块携带 `choices[0].finish_reason = "length"`
- **WHEN** 归一化为 `LLMChunk`
- **THEN** 该 `LLMChunk.finish_reason` 为 `"length"`，且其 `content` / `tool_calls` / `thinking` 逐字不受影响

#### Scenario: 未携带终止原因的增量块为零值

- **GIVEN** 某增量块不含 `finish_reason`（既有行为）
- **WHEN** 归一化该增量块
- **THEN** `LLMChunk.finish_reason` 为空串，不报错，其余字段解析与既有实现逐字一致
### Requirement: 流式增量携带令牌用量

流式增量模型 `LLMChunk` SHALL 携带 `usage` 字段（类型 `TokenUsage | None`；该增量块未携带用量时
为 `None`，SHALL NOT 以零值冒充实报）。provider 归一化 SHALL 从流式增量块的顶层 `usage` 对象取值
（OpenAI 兼容端点在**开启用量上报**时于**末块**携带，该末块的 `choices` 可为**空数组** —— 归一化
SHALL 在此形态下仍然产出携带 `usage` 的增量块，SHALL NOT 因 `choices` 为空而丢弃用量）；
往返字段缺失（无 `usage`、或 `usage` 为 `null`）SHALL 归一为 `None`，SHALL NOT 报错。
归一化 SHALL NOT 改变 `content` / `tool_calls` / `thinking` / `finish_reason` 的既有语义，
亦 SHALL NOT 改变**非流式** `LLMResponse.usage` 的既有解析（缺省零值口径逐字保留）。

provider 在**流式**请求上 SHALL 要求端点上报用量（OpenAI 兼容 `stream_options.include_usage`），
且 SHALL NOT 对**非流式**请求下发该字段（非流式响应本就携带 `usage`）。

消费方（`LLMPlanner`）SHALL 在流式路径上消费该用量：`prompt_tokens` SHALL 与装配估算取**较大者**
作为提示词占用的**下界**（与既有非流式口径逐字一致），`completion_tokens` SHALL 仅作**观测**记录，
SHALL NOT 参与任何判定（终止语义 / 预算闸门均不改）。

#### Scenario: 流式末块携带用量

- **GIVEN** provider 流式返回若干增量块，其中末块 `choices` 为空数组且顶层携带
  `usage = {"prompt_tokens": 120, "completion_tokens": 34}`
- **WHEN** 归一化为 `LLMChunk`
- **THEN** 该增量块 `usage` 为 `TokenUsage(prompt_tokens=120, completion_tokens=34)`，其 `content`
  为空串，其余字段不受影响

#### Scenario: 未携带用量的增量块为 None

- **GIVEN** 某增量块不含顶层 `usage`（或该值为 `null`）
- **WHEN** 归一化该增量块
- **THEN** `LLMChunk.usage` 为 `None`（不报错，也不以 `TokenUsage(0, 0)` 冒充），其余字段解析与
  既有实现逐字一致

#### Scenario: 流式请求要求端点上报用量

- **GIVEN** 一次流式调用
- **WHEN** provider 构建请求体
- **THEN** 请求体携带 `stream: true` 与 `stream_options.include_usage: true`；**非流式**请求体
  不携带 `stream_options`（逐字保留既有形状）

#### Scenario: 消费方以实报抬升提示词下界且不改判定

- **GIVEN** 装配估算为 `E`，末块实报 `prompt_tokens = P`
- **WHEN** 流式推理结束
- **THEN** 提示词观测为 `max(E, P)`（实报为**下界**、只抬升）；`completion_tokens` 可经观测探针读取，
  但不改变终止语义与预算闸门
### Requirement: 请求侧输出上限按预留注入

统一补全请求 `LLMRequest.max_tokens` SHALL 由组合根按**输出预留**（`loop.output_reserve`）注入：
`LLMPlanner` SHALL 提供构造期注入点，取值 **> 0** 时 SHALL 填入每次请求的 `max_tokens`（provider
据此下发 `max_tokens`）；注入点缺省 `None` **或**取值 **≤ 0** 时 SHALL NOT 下发该字段（既有请求形状
逐字不变 —— 端点不支持 / 上限更低时零影响）。

该注入使「预留」从**记账假设**变为**端点上界**：预算派生（`窗口 − 预留`）本已假设输出至多占预留
这么多 token，下发后模型侧不再可能越界产出 ⇒ 记账与实际上界一致。

#### Scenario: 注入正预留即下发输出上限

- **GIVEN** `LLMPlanner` 经构造注入 `max_tokens = 8192`
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `8192`，provider 请求体携带 `max_tokens: 8192`

#### Scenario: 未注入或非正预留不下发

- **GIVEN** `LLMPlanner` 未注入 `max_tokens`（缺省），或注入值 `≤ 0`
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `None`，provider 请求体**不含** `max_tokens` 键（与既有实现逐字一致）
