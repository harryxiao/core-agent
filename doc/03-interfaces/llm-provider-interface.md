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
    provider: str        # 审计标注：实际响应的 provider（由构造注入，见 §2.4）
    model: str           # 审计标注：实际使用的 model
    tool_calls: list[ToolCall] | None = None  # 原生 function call（缺失走 content 协议）
    thinking: str = ""                        # 推理原文（归一化后；缺省空串，见 §2.1）

@dataclass
class LLMChunk:
    content: str
    tool_calls: list[ToolCall] | None = None  # delta.tool_calls 增量片段（index 分组）
    thinking: str = ""                        # 推理原文增量（归一化后；缺省空串，见 §2.1）
    finish_reason: str = ""                   # 终止原因（该块未携带时为空串，见 §2.2）
    usage: TokenUsage | None = None           # 令牌用量（该块未携带时为 None，见 §2.3）
```

### 2.4 provider 审计标签的真实性（change `0184` / ADR-0175 / 账本 E121）

`LLMResponse.provider` 此前在 `_map_response` **硬编码 `"stdlib"`**、组合根构造 `StdlibLLMProvider`
**不传** provider ⇒ 即便 `llm.provider: litellm`（该键**必填**），审计标签仍是 `"stdlib"` ——
规格「模型调用审计」要求标注 provider，**标注与实际不符**（死标签）。

- **构造注入**：`StdlibLLMProvider(..., provider: str = "stdlib")`；`self._provider = provider or "stdlib"`，
  `_map_response` 以 `provider=self._provider` 标注。组合根按 `app.llm.provider` 注入。
- **为什么改生产点**：`LLMResponse` 由 provider 产出、经 `_audit` 回调与调用方消费 ⇒ 生产点说谎则
  下游全在说谎；**只有**改生产点能保证「响应面所见即配置面所见」（runtime 事后改写不做）。
- **自守**：`provider or "stdlib"` —— 裸构造（registry `default()` / 测试替身）不传该参、配置面理论上
  不会给空串，但接口面**不**把空标签写进审计。缺省值使未注入的构造点行为**逐字不变**。
- **不变量**：未注入 provider ⇒ `LLMResponse.provider == "stdlib"`（与既有行为**逐字一致**）。

### 2.3 流式令牌用量与请求侧输出上限（change `0183` / ADR-0174 / 账本 E120）

流式是**默认推理路径** ⇒ 端点实报的用量此前进不了内核，记账下界只有装配估算。本 change 补上两件事：

- **`LLMChunk.usage`**：取增量块**顶层** `usage` 对象；**该块未携带时为 `None`**（SHALL NOT 以
  `TokenUsage(0, 0)` 冒充实报 —— 「端点未上报」与「端点报零」在观测面必须可分辨）。**键位陷阱**：
  OpenAI 兼容端点在开启用量上报时把 `usage` 放在**末块**，而该末块 `choices` 是**空数组** ⇒
  provider 在 `choices` 为空的早返分支**之前**取用量，此类块 `content` 仍为空串（事件面零变化）。
- **请求侧**：流式请求体带 `stream_options: {"include_usage": true}`（要求端点上报）；**非流式**
  请求体**不含**该字段（其响应本就携带 `usage`）。
- **`LLMRequest.max_tokens`**：由组合根按**输出预留**（`loop.output_reserve`）注入 `LLMPlanner`
  的构造期注入点 ⇒ `> 0` 时填入每次请求（provider 据此下发 `max_tokens`），`None` 或 `≤ 0` 时
  **不**下发（请求形状逐字不变）。该注入使「预留」从**记账假设**变为**端点上界**（预算派生
  `窗口 − 预留` 本已假设输出至多占预留这么多）。
- **消费面**（`LLMPlanner`）：`prompt_tokens` 与装配估算取**较大者**为记账下界（与非流式同口径），
  `completion_tokens` **仅**记观测（`last_completion_tokens()`），**不参与**任何判定。

### 2.2 流式增量的终止原因（`finish_reason`，change `0170` / ADR-0161）

`LLMResponse.finish_reason` **早已存在**（非流式路径，`choices[0].finish_reason`，缺省 `"stop"`）；
流式路径此前**丢弃**该字段 ⇒ 消费方（planner）无从判断输出是否被**截断**。本 change 补上：

- **键位**：`LLMChunk.finish_reason` 取 `choices[0].finish_reason`，**该块未携带时为空串**（OpenAI
  兼容端点通常在**末块**携带，如 `stop` / `length`）；与 `content` / `thinking` 同为**归一化后的字符串**。
- **只读不解释**：provider **只透传**该值，不解读语义；「`length` ⇒ 输出被截断」的**归因**由消费方
  （`LLMPlanner._parse(..., finish_reason=…)`）完成 ⇒ 提示成因可辨（见 §3.1）。
- **尾字段带缺省**：缺省空串 ⇒ 全部既有构造点零改动；`getattr` 取值 ⇒ 第三方 provider 自有的形块
  不致破。

### 2.1 思考原文归一（`thinking`，change `0145` / ADR-0137 / 账本 E56）

`thinking` 是**推理原文**（reasoning content）的统一内部字段，承载模型的思考过程（如 GLM / DeepSeek
的 `reasoning_content`、OpenAI o 系的 `reasoning`）。两家字段名差异**只在此处归一**，下游
（loop / UI）只见 `thinking`，无需知道来源厂商。

- **键位**：`reasoning_content` **优先**，`reasoning` **兜底**；两者皆缺或非字符串 ⇒ 空串。
- **不与 `content` 拼接**：思考原文与回复正文是**两个语义**，`thinking` 与 `content` **互不掺和**
  —— 否则思考文本会被下游当作回复落进转录（红线）。
- **非流式与流式均携带**：`LLMResponse.thinking` 为该次响应的**终态全文**；`LLMChunk.thinking`
  为**增量片段**（逐 chunk 追加即得全文）。

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

- **流式空闲超时**（change 0256 / ADR-0247）：`astream` 对**相邻增量**的等待上限为 `timeout`
  （与构造参同一口径，缺省 `60` 秒）。超过上限未收到任何 `data:` 帧 ⇒ 尽力关闭响应并抛
  `LLMTimeoutError`；已交付的增量**不回滚、不重试**。该上限覆盖「连接活着但只发 SSE 注释 /
  keep-alive」的端点（socket 读超时管不到），按相邻间隔而非总时长设限，合法长生成不被误杀。
- 配置归一化：任意 OpenAI 兼容 API Key + Base URL（含 /v1）配置即路由到对应端点。
- **审计标签构造注入**（change `0184`／ADR-0175）：
  `StdlibLLMProvider(..., provider: str = "stdlib")` —— 组合根按 `llm.provider` 注入，`_map_response`
  以此为 `LLMResponse.provider`。空（未注入）⇒ `provider or "stdlib"` 回落实现自身身份
  ⇒ 裸构造 / 测试替身**逐字不变**。此前是硬编码 `"stdlib"`（配置面说什么都不听）—— 见 §2.4。

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
