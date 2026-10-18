# 模块设计：LLM Provider（三方大模型归一化接入）

> 对应规格：`doc/openspec/specs/llm-provider/spec.md` ｜ 接口：`doc/03-interfaces/llm-provider-interface.md`

---

## 1. 模块定位

LLM Provider 让 core-agent 通过统一 LLMProvider 抽象接口调用任意三方大模型：配置任意模型的 API Key 与 URL 即自动路由接入，内核 loop 只依赖抽象接口、不感知具体供应商。StdlibLLMProvider（OpenAI 兼容 stdlib，零三方依赖）作默认实现，经依赖注入隔离可无缝替换或自研，调用方零改动。

- **归一化接入**：任意三方模型（OpenAI / Anthropic / DeepSeek / 通义等）API Key + URL 配置即用，模块自动解析各平台协议差异，无需逐家编写适配代码。
- **接口为重心**：内核只面向 LLMProvider 抽象（completion / stream / embedding），不绑定具体实现。
- **依赖注入可替换**：替换默认实现或接入自研后端时，内核 loop 及所有调用方零改动。

---

## 2. 架构

```
L3 Loop ──► LLMProvider（抽象接口）──► StdlibLLMProvider（默认实现）──► 三方模型 API
                 ▲                          ▲
                 │                          │
                 └──── 注册 / 工厂（依赖注入）──┘
```

- **LLMProvider**：抽象接口，定义 completion / stream / embedding 三入口 + 统一请求 / 响应模型。
- **StdlibLLMProvider**：默认实现（`urllib.request` 直连 OpenAI 兼容端点 + 手写 SSE 解析，零三方依赖），负责协议 / 配置 / 错误归一化（ADR-0044）。
- **注册与工厂**：依赖注入容器，内核只依赖接口；替换实现仅改注册处。

---

## 3. 关键设计

### 3.1 抽象接口为重心

- 三入口：`completion`（同步补全）/ `stream`（流式补全）/ `embedding`（向量化）。
- 统一请求模型：消息列表 + 参数（temperature / max_tokens 等）；统一响应模型：内容 + 令牌统计 + finish_reason。
- **同步/异步桥接**（change `0290` / ADR-0280）：同步入口为薄壳。无运行事件循环 ⇒ `asyncio.run`
  对应异步实现；运行中事件循环内 ⇒ 在**一次性工作线程**的新循环执行同一异步实现并等待
  （`_run_sync` 接收**协程工厂**，桥接失败不留孤儿协程）。两种上下文均为阻塞语义；一次性线程
  意味着该路径的 HTTP 连接池 thread-local 连接不复用。`stream` 仍为缓冲式。

### 3.2 stdlib 默认实现（OpenAI 兼容）

- 协议映射：统一按 OpenAI 兼容 chat/completions + embeddings 形状收发（覆盖 OpenAI / DeepSeek / 通义等兼容端点），不依赖任何三方 SDK。
- 配置归一化：任意 OpenAI 兼容 API Key + Base URL 配置即自动路由到对应端点。

### 3.3 依赖注入可替换

- 内核只依赖 LLMProvider 接口，替换默认实现或接入自研后端不改调用方。
- 注册工厂：Provider 注册进工厂，按名称 / 模型前缀解析，注册即生效。

### 3.4 错误归一化

- 超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义，不泄漏供应商原始错误结构。

### 3.5 模型调用审计

- 复用 observability 链路，标注 provider / model 与调用结果，任意一次模型调用可追溯。
- **标签真实性**（change `0184`／ADR-0175）：`LLMResponse.provider` **不是**硬编码常量 ——
  `StdlibLLMProvider(provider=…)` 构造期接受注入（组合根按 `llm.provider` 注入），`_map_response`
  用实例值标注 ⇒ **响应面所见即配置面所见**。注入值为空（未提供）⇒ 回落实现自身身份 `"stdlib"`
  （裸构造 / 测试替身行为**逐字不变**）。`provider or "stdlib"` 的自守使空串不会写进审计。

### 3.6 连接复用（change `0066`）

- 传输走 `HTTPConnectionPool`：**同 origin 复用 keep-alive 连接**（空闲连接存 `threading.local()`，线程内复用、无锁），
  连续调用省去重复 TCP + TLS 握手；连接失效（服务端空闲超时 / reset）时**自动重建一次**。
- 代理环境或 3xx 重定向回落 `urlopen`（保 stdlib 语义）；未读尽的响应（如 SSE 中途停止）连接关闭丢弃，不回池。
- 注入接缝：`StdlibLLMProvider(transport=...)`，换传输策略不改 provider（ADR-0064）。

### 3.7 流式令牌用量与请求侧输出上限（change `0183` / ADR-0174 / 账本 E120）

- **用量归一**：`LLMChunk.usage: TokenUsage | None`（未携带 ⇒ `None`，不以零值冒充实报）。**键位陷阱**：
  端点在开启上报时把 `usage` 放在 `choices` 为**空数组**的**末块** ⇒ `_map_chunk` 在早返**之前**取用量，
  此类块 `content` 仍为空串（事件面零变化）。非流式 `LLMResponse.usage` 解析**逐字不动**。
- **请求侧形状**：流式请求体增 `stream_options: {"include_usage": true}`；**非流式不含**该字段。
  `LLMRequest.max_tokens` 由组合根按输出预留注入 ⇒ `> 0` 才下发（见 §3.2 的请求体构建）。
- 无新增三方依赖（仍 `urllib` 直连 + 手写 SSE）。

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| 底层超时 | 归一化为 `LLM_TIMEOUT` 领域异常 |
| 底层限流 | 归一化为 `LLM_RATE_LIMITED`，可重试 |
| 底层鉴权失败 | 归一化为 `LLM_AUTH_ERROR` |
| 网络异常 | 归一化为 `LLM_NETWORK_ERROR`（含连接池路径的 `http.client` / `OSError` 连接层异常） |
| 连接失效（复用连接被服务端关闭） | 自动重建并重发一次，调用方无感 |
| 未知 provider / model | 路由失败，返回 `UNKNOWN_PROVIDER` |
| 替换实现注册 | 走同一工厂，调用方零改动 |

---

## 5. 关联

- 规格：`doc/openspec/specs/llm-provider/spec.md`
- 接口：`doc/03-interfaces/llm-provider-interface.md`
- 内核 loop 调用点：`doc/02-modules/loop.md`
- 横切：`doc/02-modules/observability.md`（调用审计）
- 测试：`doc/04-testing/test-cases.md`（LLM Provider 系列）
- ADR：`doc/01-architecture/adr.md`（ADR-0021、ADR-0044、ADR-0064）
