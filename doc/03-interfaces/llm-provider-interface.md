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

    async def acompletion(self, request: LLMRequest) -> LLMResponse: ...
    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...
    async def aembedding(self, texts: list[str]) -> list[Embedding]: ...
```

- 六入口：`completion` / `stream` / `embedding`（同步）+ `acompletion` / `astream` / `aembedding`（异步）；异步为主、同步为薄壳（内部 `asyncio.run` 桥接），支持事件循环内非阻塞与真并发。
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
    reasoning_effort: str | None = None  # 推理档位 low/medium/high；None 不下发

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int

@dataclass
class ToolCall:
    tool_id: str         # function.name
    arguments: str       # 参数 JSON 字符串（流式片段为增量）
    call_id: str | None = None
    index: int = 0       # 流式片段归属索引

@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage
    finish_reason: str
    provider: str        # 审计标注：实际响应的 provider
    model: str           # 审计标注：实际使用的 model
    tool_calls: list[ToolCall] | None = None  # 原生 function call（缺失走 content 协议）

@dataclass
class LLMChunk:
    content: str
    tool_calls: list[ToolCall] | None = None  # delta.tool_calls 增量片段（index 分组）
```

---

## 3. StdlibLLMProvider（默认实现）

```python
class StdlibLLMProvider(LLMProvider):
    """默认实现：stdlib 直连 OpenAI 兼容端点（零第三方运行时依赖）。"""

    def completion(self, request: LLMRequest) -> LLMResponse:
        # urllib.request 发 OpenAI 兼容 HTTP，映射请求模型
        ...

    def stream(self, request: LLMRequest) -> Iterator[LLMChunk]:
        # SSE 流式，逐块产出
        ...

    def embedding(self, texts: list[str]) -> list[Embedding]:
        # urllib.request 发 /embeddings
        ...

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        # asyncio.to_thread + urllib.request，映射请求模型
        ...

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        # run_in_executor + asyncio.Queue 桥接 SSE，逐块产出
        ...

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        # asyncio.to_thread + urllib.request 发 /embeddings
        ...
```

- 配置归一化：任意 OpenAI 兼容 API Key + Base URL（含 /v1）配置即路由到对应端点。

### 3.1 传输层与连接复用（change `0066`）

```python
class HTTPTransport(Protocol):
    def send(self, request: Request, *, timeout: float) -> AbstractContextManager[Any]: ...

class HTTPConnectionPool:            # 默认传输：同 origin 复用 keep-alive 连接
    def __init__(self) -> None: ...

StdlibLLMProvider(..., transport: HTTPTransport | None = None)   # 注入接缝
```

- **连接复用**（规格「模型调用可靠性」场景「连接复用」）：三次调用路径（chat / embedding / SSE）统一经
  `transport.send(...)`；空闲连接存 `threading.local()`，**线程内按 origin 复用** —— 连续调用不再重复 TCP + TLS 握手。
- **回落 `urlopen`**：环境配了该 scheme 的代理（`http.client` 不读代理环境变量）、或响应为 3xx（`http.client`
  不跟随重定向）时，交回 `urlopen`，保持既有代理 / 重定向语义。
- **失效自动重建**：复用到的连接在「发请求 / 读状态行」阶段失效（服务端空闲超时、reset、管道已断）→ 关闭后**换新连接重发一次**；
  未收到任何响应字节才重发，故不重复计费副作用。
- **错误口径不变**：非 2xx 转 `urllib.error.HTTPError` 抛出 ⇒ 既有状态码映射（§5）继续生效；
  `http.client` 连接层异常（无 urllib 包装）由 `map_http_error` 归一到 `LLMNetworkError`（可重试），**不泄漏裸 `OSError`**。
- **读尽才归还**：未读尽的响应（如 SSE 中途停止）关闭丢弃，不回池。
- 换传输实现（连接复用策略 / 自定义代理隧道 / 测试替身）只改注入点，provider 本体零改动 —— 对齐 ADR-0040 / ADR-0064。

---

## 4. 注册与工厂（依赖注入）

```python
class LLMProviderRegistry:
    """Provider 注册中心。内核按名称 / 模型前缀解析，注册即生效。"""

    def register(self, name: str, provider: LLMProvider) -> None: ...
    def resolve(self, name_or_model_prefix: str) -> LLMProvider: ...
    def default(self) -> LLMProvider: ...   # 未命中时回落 StdlibLLMProvider
```

- 替换默认实现 / 接入自研后端：仅 `register` 一处变更，内核与调用方零改动。

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
