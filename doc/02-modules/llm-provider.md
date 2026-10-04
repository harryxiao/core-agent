# 模块设计：LLM Provider（三方大模型归一化接入）

> 对应规格：`doc/openspec/specs/llm-provider/spec.md` ｜ 接口：`doc/03-interfaces/llm-provider-interface.md`

---

## 1. 模块定位

LLM Provider 让 core-agent 通过统一 LLMProvider 抽象接口调用任意三方大模型：配置任意模型的 API Key 与 URL 即自动路由接入，内核 loop 只依赖抽象接口、不感知具体供应商。LiteLLM 作默认实现，经依赖注入隔离可无缝替换或自研，调用方零改动。

- **归一化接入**：任意三方模型（OpenAI / Anthropic / DeepSeek / 通义等）API Key + URL 配置即用，模块自动解析各平台协议差异，无需逐家编写适配代码。
- **接口为重心**：内核只面向 LLMProvider 抽象（completion / stream / embedding），不绑定 LiteLLM。
- **依赖注入可替换**：替换 LiteLLM 或接入自研后端时，内核 loop 及所有调用方零改动。

---

## 2. 架构

```
L3 Loop ──► LLMProvider（抽象接口）──► LiteLLMProvider（默认实现）──► 三方模型 API
                 ▲                          ▲
                 │                          │
                 └──── 注册 / 工厂（依赖注入）──┘
```

- **LLMProvider**：抽象接口，定义 completion / stream / embedding 三入口 + 统一请求 / 响应模型。
- **LiteLLMProvider**：默认实现，负责协议映射（100+ provider 归一化）、配置归一化、错误归一化。
- **注册与工厂**：依赖注入容器，内核只依赖接口；替换实现仅改注册处。

---

## 3. 关键设计

### 3.1 抽象接口为重心

- 三入口：`completion`（同步补全）/ `stream`（流式补全）/ `embedding`（向量化）。
- 统一请求模型：消息列表 + 参数（temperature / max_tokens 等）；统一响应模型：内容 + 令牌统计 + finish_reason。

### 3.2 LiteLLM 默认实现

- 协议映射：LiteLLM 统一 100+ 模型协议，覆盖 OpenAI / Anthropic / DeepSeek / 通义等主流平台。
- 配置归一化：任意三方 API Key + Base URL 配置即自动路由到对应 provider 协议。

### 3.3 依赖注入可替换

- 内核只依赖 LLMProvider 接口，替换 LiteLLM 或接入自研后端不改调用方。
- 注册工厂：Provider 注册进工厂，按名称 / 模型前缀解析，注册即生效。

### 3.4 错误归一化

- 超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义，不泄漏供应商原始错误结构。

### 3.5 模型调用审计

- 复用 observability 链路，标注 provider / model 与调用结果，任意一次模型调用可追溯。

### 3.6 连接复用（change `0066`）

- 传输走 `HTTPConnectionPool`：**同 origin 复用 keep-alive 连接**（空闲连接存 `threading.local()`，线程内复用、无锁），
  连续调用省去重复 TCP + TLS 握手；连接失效（服务端空闲超时 / reset）时**自动重建一次**。
- 代理环境或 3xx 重定向回落 `urlopen`（保 stdlib 语义）；未读尽的响应（如 SSE 中途停止）连接关闭丢弃，不回池。
- 注入接缝：`StdlibLLMProvider(transport=...)`，换传输策略不改 provider（ADR-0064）。

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
