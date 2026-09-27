# Change: LLM Provider 通用接口（三方大模型归一化接入）

## Why

core-agent 内核 loop 需要调用大模型完成推理，但当前没有统一的 LLM 接入层。实际使用中，用户需要能配置任意三方模型的 API Key 与 URL（OpenAI / Anthropic / DeepSeek / 通义 / 各类国产模型等），由模块自动解析各平台协议差异，而不是每接入一家就改一处代码。

业界在该场景的事实标准组件是 LiteLLM（MIT license，统一 100+ 模型协议）。但若把 LiteLLM 硬编码进内核，等于把供应商锁定进架构；未来想换回自研后端或替换其他组件，会牵动内核大量修改。

因此新增 `llm-provider` capability：**以 LLMProvider 抽象接口为重心**，LiteLLM 作为默认实现，通过依赖注入隔离。内核只依赖接口、不感知具体实现；后续可无缝替换 LiteLLM、或接入自研后端，调用方零改动。

## What Changes

- 新增 `llm-provider` capability：定义 LLMProvider 抽象接口（completion / stream / embedding）
- LiteLLM 作为默认 Provider 实现：配置任意三方 API Key + Base URL 即可自动路由接入
- 依赖注入容器管理 Provider 生命周期，内核只依赖接口、不依赖具体实现
- 配置归一化：单一配置入口声明模型 / 密钥 / 端点，运行时自动解析
- 错误归一化：超时 / 限流 / 鉴权 / 网络异常统一为领域异常

## Impact

- **Affected specs**：`llm-provider`（新增 capability）
- **Affected specs (integration)**：`loop`（内核推理调用点复用同一 Provider 接口，调用方零改动）、`observability`（模型调用审计）
- **Affected code**：新增 `src/llm_provider/`（LLMProvider 抽象、LiteLLMProvider 实现、注册与工厂）；内核 loop 调用点不改动
- **Dependencies**：依赖 0001 主轴（L1 工具层）+ 0002 横切（复用 observability 审计模型调用）；引入第三方依赖 `litellm`（MIT）
