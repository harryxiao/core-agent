# Design

## Context

core-agent 内核 loop 需要调用大模型，但尚无统一 LLM 接入层，接入新模型即改代码、供应商锁定风险高。用户诉求是「配置任意三方模型 API Key 和 URL，模块自动解析处理」——这正是归一化接口的典型场景。业界事实标准组件是 LiteLLM（MIT license，59k+ stars，统一 100+ 模型协议，兼容 OpenAI / Anthropic / DeepSeek / 通义等）。

但直接硬编码 LiteLLM 会把供应商锁进架构。因此本设计以 **LLMProvider 抽象接口为重心**，LiteLLM 仅作默认实现，通过依赖注入隔离：内核只依赖接口，后续替换 LiteLLM 或接入自研后端时调用方零改动。

## Research / 参考资料

- **LiteLLM**：`github.com/BerriAI/litellm`（主库 MIT license，enterprise/ 目录独立授权），59k+ stars，统一 100+ 模型协议，兼容 OpenAI / Anthropic / DeepSeek / 通义等。pyproject 依赖 `litellm>=1.101.0`。
- **备选方案对比**：各家原生 SDK 直连（OpenAI / Anthropic / DeepSeek SDK，接入新模型即改代码、供应商锁定）→ 否决；LangChain（框架耦合重、引入范围大，超出归一化接入层职责）→ 否决；LiteLLM（事实标准归一化层，社区活跃）→ 采用为默认实现，并经 LLMProvider 抽象接口隔离，保证后续可自研替代而不改调用方。

## Decisions

- **LLMProvider 抽象接口为重心**：定义 completion / stream / embedding 三个入口 + 统一请求 / 响应模型；内核 loop 只依赖该接口，不感知具体供应商。
- **LiteLLM 作默认实现**：默认 Provider 用 LiteLLM 屏蔽各平台协议差异；任意三方模型只需配置 API Key + Base URL 即可路由接入。
- **依赖注入隔离**：Provider 经注册 / 工厂按配置装配，内核只注入接口实例；替换 LiteLLM 或自研后端只需新增一个实现类并改装配配置，调用方零改动。
- **配置归一化**：单一配置入口声明模型 / 密钥 / 端点，运行时自动解析路由，不散落硬编码。
- **错误归一化**：超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义。

## Risks / Trade-offs

- **供应商锁定**：直接依赖 LiteLLM 会锁定后端——用抽象接口 + 依赖注入隔离，替换成本收敛到单个实现类。
- **依赖体积与复杂度**：LiteLLM 依赖面较广——按需引入、懒加载，避免拖累内核启动。
- **License 边界**：LiteLLM 主库为 MIT，但其 enterprise/ 目录为独立授权——只依赖主库、不引入 enterprise 部分。
- **国产模型兼容性**：DeepSeek / 通义等国产模型 LiteLLM 原生支持，但个别私有协议需实测；抽象接口保证不兼容时可换自研实现兜底。

## Open Questions

- 初版是否三入口（completion / stream / embedding）全覆盖，还是先 completion + stream。
- 模型配置并入 config.yaml（**已决**，见 change 0025-configuration / ADR-0034），不再保留独立 llm.yaml 配置块。
- 是否支持多 Provider 按模型前缀路由（如 `deepseek/*` 走 A、`gpt-*` 走 B）。
