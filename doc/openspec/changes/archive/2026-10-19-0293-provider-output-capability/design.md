# 设计 — 0293 供应商输出上限能力适配

## D1 能力表放在 `configuration` 底座层

表是**模型方言知识**，provider 与配置校验都要用：

- provider 需要它决定请求字段与钳制；
- 配置校验需要它产生告警。

架构测试禁止底座模块（`configuration`）反向依赖能力层（`llm_provider`），因此表落在
`src/core/configuration/model_capabilities.py`，provider 作为能力层 import 底座（允许）。
与 `model_windows.py` 并列：窗口表回答「上下文多大」，能力表回答「输出字段与上限」。

```python
@dataclass(frozen=True)
class ModelCapability:
    max_output_tokens: int      # 0 = 不知道（不钳制）
    max_tokens_field: str = "max_tokens"
    supports_reasoning_effort: bool | None = None  # None = 不知道

_KNOWN_CAPABILITIES: tuple[tuple[str, ModelCapability], ...] = (
    # 顺序即特异性：更具体的子串在前，首个命中胜出
    ("gpt-5", ModelCapability(128_000, "max_completion_tokens", True)),
    ("o4-mini", ModelCapability(100_000, "max_completion_tokens", True)),
    ("o3", ModelCapability(100_000, "max_completion_tokens", True)),
    ("o1", ModelCapability(100_000, "max_completion_tokens", True)),
    ("gpt-4o", ModelCapability(16_384, "max_tokens", False)),
    ("gpt-4.1", ModelCapability(32_768, "max_tokens", False)),
    ("gpt-4-turbo", ModelCapability(4_096, "max_tokens", False)),
    ("gpt-3.5", ModelCapability(4_096, "max_tokens", False)),
    ("deepseek", ModelCapability(8_192, "max_tokens", False)),
    ("glm-5", ModelCapability(0, "max_tokens", True)),
)
```

纪律（同 ADR-0175）：只收有据可查的族；未命中返回 `None`（不钳制、不告警）；纯常量、
纯函数、无配置键。`max_output_tokens=0` 与 `supports_reasoning_effort=None` 都是
「不知道」的诚实表达，不编造数字。

## D2 钳制与字段选择在 provider 请求体构建处

```python
if request.max_tokens is not None:
    body[max_tokens_field(model)] = effective_output_tokens(model, request.max_tokens)
```

- `effective_output_tokens`：未收录 / 上限 `0` ⇒ 原值；否则 `min(请求值, 上限)`。
- 只**向下**收紧，绝不抬高用户配置。
- 字段只发一个：`max_tokens` 或 `max_completion_tokens`；不发第三个字段。
- 未收录模型：字段与数值都与变更前逐字一致。
- 不改变 `planner` / 组合根：`output_reserve` 的注入点与语义不动，适配全在协议边界。

## D3 终止原因别名归一

```python
_TRUNCATION_ALIASES = {"max_tokens", "max_output_tokens"}

def _normalize_finish_reason(value: object) -> str:
    text = "" if value is None else str(value)
    return "length" if text.strip().lower() in _TRUNCATION_ALIASES else text
```

- 大小写与首尾空白不敏感（`MAX_TOKENS` ⇒ `length`）。
- 非截断值原样保留，不折叠成 `stop`；缺失沿用既有口径（流式空串 / 非流式 `stop`）。
- 同时用于 `_map_response` 与 `_map_chunk`。0292 的 `_parse` 只认 `length`，本归一让
  各家别名都能命中截断诊断。

## D4 配置期告警（不阻断）

`validate_schema` 追加 `_model_capability_warnings`：

1. `output_reserve > cap.max_output_tokens > 0` ⇒ 告警「请求将按模型上限钳制」；
2. `llm.reasoning_effort` 非空且 `cap.supports_reasoning_effort is False` ⇒ 告警
   「仍会照常下发，端点可能拒绝」。

未收录 / 未知能力不告警。告警不回显 endpoint 或密钥。**不**因告警改变 `ok`。

## 被拒方案

- **按 tokenizer 逐家计算上限**：维护不可持续，且上限是协议常量而非分词结果。
- **启动期探测 `/models`**：引入网络依赖、启动不确定性与鉴权面（ADR-0175 已拒）。
- **同时发 `max_tokens` 与 `max_completion_tokens`**：严格端点 400，宽松网关可能取其一。
- **按能力表丢弃 `reasoning_effort`**：用户显式配置被静默改写；只告警更诚实。
- **新增 `llm.max_output_tokens` 配置键**：当前主流族可由表覆盖；先不加键，避免第二真源。
- **在 `length` 时自动加倍重试**：成本/延迟不可控，且仍可能超模型上限。

## 局限

1. 表是**静态常量**，新模型族需改代码（与 ADR-0175 同）；
2. 子串匹配无边界语义，自建模型名含 `gpt-4o` 等子串会被误纳入（表小而实，风险有界）；
3. 未收录的自研网关无法通过配置表达更低上限（本 change 不加键）；
4. `reasoning_effort` 只告警不拦截，已知不支持的端点仍会 400；
5. 不修 `known_window` 的窗口值，`gpt-4.1` 等窗口口径保持既有（表更新是另一件事）；
6. 能力表不覆盖 Anthropic / Gemini **原生协议**（仓库只走 OpenAI 兼容端点）。
