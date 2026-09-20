# 接口设计：LLM Provider 接口（LLM Provider Interface）

> 横切 ｜ 对应规格 `llm-provider/spec.md` ｜ 模块 `02-modules/llm-provider.md`

---

## 1. LLMProvider 抽象接口

```python
class LLMProvider(ABC):
    """三方大模型归一化抽象接口。内核只依赖此接口，不感知具体供应商实现。"""

    def completion(self, request: LLMRequest) -> LLMResponse: ...
    def stream(self, request: LLMRequest) -> Iterator[LLMChunk]: ...
    def embedding(self, texts: list[str]) -> list[Embedding]: ...
```

- 三入口：`completion`（同步补全）/ `stream`（流式补全）/ `embedding`（向量化）。
- 调用方（内核 loop 及所有消费方）只面向此接口，替换实现零改动。

---

## 2. 统一请求 / 响应模型

```python
@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str

@dataclass
class LLMRequest:
    messages: list[Message]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    tools: list[ToolDef] | None = None

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int

@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    finish_reason: str
    provider: str        # 审计标注：实际响应的 provider
    model: str           # 审计标注：实际使用的 model
```

---

## 3. LiteLLMProvider（默认实现）

```python
class LiteLLMProvider(LLMProvider):
    """默认实现：委托 LiteLLM 统一 100+ 模型协议。"""

    def completion(self, request: LLMRequest) -> LLMResponse:
        # 委托 litellm.completion，映射请求模型 + 归一化协议差异
        ...

    def stream(self, request: LLMRequest) -> Iterator[LLMChunk]:
        # 委托 litellm.completion(stream=True)，逐块产出
        ...

    def embedding(self, texts: list[str]) -> list[Embedding]:
        # 委托 litellm.embedding
        ...
```

- 配置归一化：任意三方 API Key + Base URL 配置即自动路由到对应 provider 协议。

---

## 4. 注册与工厂（依赖注入）

```python
class LLMProviderRegistry:
    """Provider 注册中心。内核按名称 / 模型前缀解析，注册即生效。"""

    def register(self, name: str, provider: LLMProvider) -> None: ...
    def resolve(self, name_or_model_prefix: str) -> LLMProvider: ...
    def default(self) -> LLMProvider: ...   # 未命中时回落 LiteLLMProvider
```

- 替换 LiteLLM / 接入自研后端：仅 `register` 一处变更，内核与调用方零改动。

---

## 5. 领域异常

```python
class LLMError(Exception): ...                    # 基类，上层只处理此类语义
class LLMTimeoutError(LLMError): ...              # 超时
class LLMRateLimitedError(LLMError): ...          # 限流，可重试
class LLMAuthError(LLMError): ...                 # 鉴权失败
class LLMNetworkError(LLMError): ...              # 网络异常
class UnknownProviderError(LLMError): ...         # 未知 provider / model
```

- 归一化原则：底层供应商原始错误统一映射为上述领域异常，不向上泄漏。

---

## 6. 调用流程

```
L3 Loop.reason(...)
  → LLMProviderRegistry.resolve(model)      # 依赖注入解析
  → LLMProvider.completion(request)         # 抽象接口调用
  → 归一化错误 → observability.record(provider, model, result)  # 调用审计
```

---

## 7. 关联

- 模块：`02-modules/llm-provider.md`
- 内核 loop 调用点：`02-modules/loop.md`
- 横切：`observability-interface.md`（调用审计）
- 规格：`openspec/specs/llm-provider/spec.md`
