# Tasks

## 1. LLMProvider 抽象接口（P1）

- [ ] 1.1 定义 LLMProvider 抽象接口（completion / stream / embedding 三个入口）
- [ ] 1.2 定义统一请求 / 响应数据模型（消息、参数、令牌统计）
- [ ] 1.3 定义 Provider 注册与工厂（依赖注入，内核只依赖接口）

## 2. LiteLLM 默认实现（P1）

- [ ] 2.1 实现 LiteLLMProvider（completion / stream / embedding 协议映射）
- [ ] 2.2 实现配置归一化（任意三方 API Key + Base URL 自动路由）
- [ ] 2.3 实现错误归一化（超时 / 限流 / 鉴权统一为领域异常）

## 3. 集成与验证（P2）

- [ ] 3.1 内核调用点接入 Provider（调用方零改动）
- [ ] 3.2 模型调用审计（observability 标注 provider / model）
- [ ] 3.3 端到端用例（配置 → 路由 → 调用 → 回包 → 审计）
