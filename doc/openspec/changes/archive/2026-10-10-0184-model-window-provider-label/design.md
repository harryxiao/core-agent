# 设计 — 已知模型窗口表与 provider 审计标签（change 0184 / ADR-0175 / 台账 E121）

## 决策

### D1 新模块 `configuration/model_windows.py`：小而有据的**有序**表

```python
_KNOWN_CONTEXT_WINDOWS: tuple[tuple[str, int], ...] = (
    ("claude", 200_000),      # Anthropic Claude 3/4 系（消息 API 上限）
    ("gpt-4o", 128_000),
    ("gpt-4.1", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-3.5", 16_385),
    ("deepseek", 65_536),
    ("glm-4", 128_000),
)


def known_window(model: str) -> int:
    """按模型名子串推导上下文窗口；未命中返回 ``0``（调用方据此回落缺省）。"""
```

- **有序元组 + 首个命中胜出**：`gpt-4o` 同时含 `gpt-4`（若收录）⇒ 顺序即特异性，避免为长前缀写特判。
  故**不**用 `dict`（字典序不表达优先级）。
- **子串匹配（大小写不敏感）**：模型 id 形如 `gpt-4o-2024-08-06` / `anthropic/claude-sonnet-4` /
  `openai/gpt-4.1-mini` —— 前缀 / 命名空间都会命中。代价：`gpt-4o` 也能命中 `my-gpt-4o-clone`
  （见局限②）。
- **只收录有据可查的常见族**，不猜测。`known_window` 返回 `0` 而非「随便给一个数」：**0 是「不知道」**
  的诚实表达，由调用方统一回落 `65536`（既有缺省），不引入新的魔法值。
- **模块归属 `configuration`**：窗口是**配置语义**（`llm.context_window` 的推导来源），
  且 `loop_limits()` 在 `configuration` 内 ⇒ 不跨层、不需要新 import 方向。

### D2 `loop_limits()`：窗口来源三态，**显式优先**

```python
window = self._config.llm.context_window
if window <= 0:
    window = known_window(self._config.llm.model)
resolve_window = window if window > 0 else _DEFAULT_CONTEXT_WINDOW   # 65536
return max_rounds, resolve_window - reserve
```

- **逐字兼容的三条路径**：① 显式 `context_window > 0` ⇒ 与变更前**逐字相同**；② 表未命中 ⇒
  回落 `65536`，与变更前**逐字相同**；③ 表命中 ⇒ **唯一**有意的行为变更。
- **`_window_reserve_errors` 不动**：它校验的是**显式配置**的窗口（`config.llm.context_window`）。
  表推导出的窗口是我们自己的常量、不经用户配置面，无需校验。
- 既有 `if window > 0: ... else: return _DEFAULT_TOKEN_BUDGET` 的分支结构改为**先归一窗口**再
  统一做减法 —— 分叉减少、口径统一（**不变量**：减法只有一处）。

### D3 `StdlibLLMProvider(provider=…)`：标签由构造注入，缺省回落自身身份

```python
def __init__(self, ..., provider: str = "stdlib") -> None:
    ...
    self._provider = provider or "stdlib"
```

`_map_response` 的 `provider="stdlib"` → `provider=self._provider`。

- **`provider or "stdlib"` 而非裸 `provider`**：`llm.provider` 是**必填**（校验非空），但
  `StdlibLLMProvider()` 的**裸构造**（registry 的 `default()`、测试替身）不传该参 ⇒ 必须回落自身身份。
  空串同理（不把空标签写进审计）。
- **为什么改在 provider 而不在 runtime 事后改写**：`LLMResponse` 由 provider 产出、经 `_audit` 回调
  与调用方消费 ⇒ 生产点说谎，下游全在说谎。改生产点是**唯一**能保证「响应面所见即配置面所见」的位置。
- 其他 `LLMProvider` 实现（若有）不受影响：这是 `StdlibLLMProvider` 的构造参数，规格只要求
  「实际使用的 provider 标识」由实现给出。

### D4 规格落点：两处 MODIFIED，各带 Scenario

- `configuration`「LLM 提供商配置（必选）」：`context_window` 句中「未配置时回落内置缺省」→
  「未配置时 SHALL 按 `model` 从内置表推导（子串匹配），未命中回落内置缺省」，并**新增一段**
  写优先级（显式 > 表 > 缺省）与表纪律（只收录有据模型 / 不新增配置键 / 非第二真源）。
  新 Scenario ×3：「未配置窗口时按模型推导」「未命中内置表回落缺省」「显式窗口优先于表推导」。
- `llm-provider`「模型调用审计」：补一句「`LLMResponse.provider` SHALL 反映实际使用的 provider 标识」
  + 新 Scenario「审计标签反映配置的 provider」。既有「调用留痕」Scenario **逐字保留**。

## 与既有条款的关系

| 既有条款 | 本 change |
|---|---|
| 「循环预算配置」交叉校验 `llm.context_window > loop.output_reserve` | **不动**（只校验显式配置；表推导不经该闸门——见局限③） |
| `_llm_context_window` 解析与非法取值阻断 | **不动**（`0` 仍是「未配置」的合法值） |
| 「模型调用审计」调用留痕 | **保留**，只把标签从常量改为注入值 |
| `LLMResponse.provider` 的既有消费者 | **语义不变**（仍是「实际 provider 标识」的字符串；只是值变准了） |

## 不变量

- **I1** 显式 `context_window > 0` ⇒ 预算派生与变更前**逐字相同**。
- **I2** 表未命中 ⇒ 预算回落 `65536`，与变更前**逐字相同**。
- **I3** 减法只有一处（归一窗口后统一 `window - reserve`）。
- **I4** 表是纯常量 + 纯函数，**不新增** ConfigSpec / CLI / env / yaml 面。
- **I5** 未注入 `provider` 的 `StdlibLLMProvider` ⇒ `LLMResponse.provider == "stdlib"`（逐字不变）。
- **I6** 无新第三方依赖；无 import 方向变化；`exclude_source_prefixes=("beast.","pet")` 逐字不动。

## 测试设计

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_known_window_matches_model_families` | `gpt-4o-2024-08-06` / `anthropic/claude-sonnet-4` / `deepseek-chat` 各命中预期窗口；大小写不敏感 |
| 2 | `test_known_window_unknown_model_is_zero` | 未收录模型（`my-local-model`）⇒ `0`（「不知道」的诚实表达） |
| 3 | `test_loop_limits_derives_window_from_model` | 未配窗口 + `model: gpt-4o` ⇒ 预算 `128000 − 8192`（**不再**恒 `65536`） |
| 4 | `test_loop_limits_explicit_window_wins` | 配 `context_window: 32768` + `model: gpt-4o` ⇒ 预算 `32768 − 8192`（回归锚） |
| 5 | `test_loop_limits_unknown_model_falls_back` | 未配窗口 + 未收录模型 ⇒ 预算 `65536`（逐字兼容回归锚） |
| 6 | `test_response_provider_label_reflects_configuration` | `StdlibLLMProvider(provider="litellm")` ⇒ `LLMResponse.provider == "litellm"` |
| 7 | `test_response_provider_defaults_to_identity` | 不传 ⇒ `"stdlib"`（缺省回归锚） |
| 8 | `test_build_runtime_labels_provider_from_config` | 组合根按 `llm.provider` 注入（接线） |

基线 **2176**；本 change 预计 **+8 ~ +10**。
