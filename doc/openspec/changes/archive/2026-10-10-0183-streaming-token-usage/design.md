# 设计 — 流式令牌用量与请求侧输出上限（change 0183 / ADR-0174 / 台账 E120）

## 决策

### D1 用量字段位置：`LLMChunk.usage`，缺省 `None`（**不**以零冒充）

`LLMChunk` 增 `usage: TokenUsage | None = None`。既有字段（`content` / `tool_calls` /
`thinking` / `finish_reason`）位置与语义**逐字不动**；新字段带缺省值 ⇒ 所有现有构造点
（`_map_chunk` 的早返分支、第三方替身、测试里手搓的 chunk）**不需改**即兼容。

`None` 与 `TokenUsage(0, 0)` 语义不同：前者是「该增量块未携带用量」，后者会被消费方误读为
「提示词 0 token」并**压低**下界（`max(估算, 0)` 虽不致死，但会让「端点未上报」与「端点报零」
在观测面失真）。故规格明文：**SHALL NOT 以零值冒充实报**。

### D2 解析点在 `choices` 早返**之前**（本轮唯一的实现陷阱）

现有 `_map_chunk`：

```python
choices = cast(list[Any], part.get("choices", []))
if not choices:
    return LLMChunk(content="")          # ← 早返
```

OpenAI 兼容端点在开启用量上报时，把 `usage` 放在**末块**，而该末块的 `choices` 是**空数组**
（该块只报账、不产内容）。若照现状早返，用量**永远**丢失 —— 解析正确但链路不通。

修法：新增 `_map_usage(part) -> TokenUsage | None`，**两处**调用 —— 早返分支
`return LLMChunk(content="", usage=self._map_usage(part))`，正常分支同样带上。早返分支的
`content=""` 与既有行为逐字一致（消费方 `if not chunk.content: continue` 仍跳过它），故
**事件面零变化**，只是这类块现在**携带**了用量。

### D3 `_map_usage` 归一：缺失 / `null` ⇒ `None`

```python
usage = part.get("usage")
if not isinstance(usage, dict):
    return None
return TokenUsage(prompt_tokens=int(usage.get("prompt_tokens", 0)),
                  completion_tokens=int(usage.get("completion_tokens", 0)))
```

与 `_map_response`（非流式）的取值口径同源（`usage.get(..., 0)`），但**不做**「缺 `usage` 时
造零值」—— 非流式响应体**总是**带 `usage`，流式则否（端点可能未开启上报）。故非流式那条路径
逐字保留（规格明文：SHALL NOT 改变非流式 `LLMResponse.usage` 的既有解析）。

### D4 请求侧：流式**才**要用量，非流式**不发**

`_build_body` 尾部：

```python
if stream:
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}   # 新增
```

非流式请求体**不**带 `stream_options`（规格 Scenario 明文）。已知局限：拒绝该字段的端点会在
流式路径报错 —— 走既有 `LLMError` 路径（**响亮失败**，非静默降级）。

### D5 消费方：实报抬升下界（与非流式同口径）+ 完成量纯观测

`LLMPlanner.astream` 循环体**首行**消费用量（在 `if not chunk.content: continue` **之前** ——
否则末块（`content=""`）的用量会被跳过）：

```python
async for chunk in self._llm.astream(request):
    self._observe_usage(getattr(chunk, "usage", None))   # 新增
    finish_reason = ...
```

```python
def _observe_usage(self, usage: TokenUsage | None) -> None:
    if usage is None:
        return
    self._last_prompt_tokens = max(self._last_prompt_tokens, usage.prompt_tokens)
    self._last_completion_tokens = usage.completion_tokens
```

- **口径与非流式逐字一致**：`_complete` 已有的 `max(self._last_prompt_tokens,
  response.usage.prompt_tokens)` 是同一句话的两种到达方式（一次性 vs 增量），合并后两条路径
  **同一语义**。
- `getattr(chunk, "usage", None)`：第三方替身产出自有形块（无该字段）时退化为 `None`、不破
  —— 与既有 `finish_reason` 的 `getattr` 处置同型。
- `completion_tokens` 只进 `_last_completion_tokens` + 新增观测探针 `last_completion_tokens()`
  （与 `last_prompt_tokens()` 同型 duck-typing），**SHALL NOT** 参与终止语义/预算闸门 ——
  预算闸门看的是**下一轮**的提示词占用（`prompt_tokens`），完成量是本轮的**已花出**、
  无可行动作，记它只为观测与审计。

### D6 `max_tokens` 注入点：构造期可选，`> 0` 才下发

`LLMPlanner.__init__` 增 `max_tokens: int | None = None`（**注入面**，非配置读取 —— planner 不
import configuration）。归一：

```python
self._max_tokens = max_tokens if (max_tokens is not None and max_tokens > 0) else None
```

`_build_request` 填 `max_tokens=self._max_tokens`。**`≤ 0` 与 `None` 同义**（不下发）：`≤ 0` 是
配置面能写出的合法值（校验只要求 ≥0），语义上「上界为 0」会让模型无法产出 ⇒ 视为**未注入**
比「下发 `max_tokens: 0` 让端点 400」更诚实。缺省 `None` ⇒ 请求 `max_tokens=None` ⇒
`_build_body` 的 `if request.max_tokens is not None` **不**入 body ⇒ 请求形状**逐字不变**。

**为什么 `> 0` 就下发是安全的**：`loop.output_reserve` 已经是预算派生的**同一个量**
（`token_budget = context_window − output_reserve`，规格「循环预算配置」）。派生本已假设
「输出至多占预留这么多」，下发只是把这个**记账假设**变成**端点上界** ⇒ 记账与实际上界一致。
配置错（预留 > 模型输出上限）时端点是**响亮 400**，且该配置本已使预算派生错误 ⇒ 本条让配置
错误**提前暴露**而非引入新风险。

### D7 组合根注入 + 访问器（**无**新配置键、**无**规格变更）

`runtime.py`：`LLMPlanner(..., max_tokens=config.output_reserve())`。

`ConfigurationManager.output_reserve()` 是**新独立访问器**，读既有键 `loop.output_reserve`
（缺省 `_DEFAULT_OUTPUT_RESERVE = 8192`）。**不加 ConfigSpec**（键已声明于 change 0115 的
「循环预算配置」）、**不改 `loop_limits()` 的 arity**（该二元组的解包断言在多个测试里钉住）——
与 `history_turns()`（change 0115）/`compact_steps()`（change 0182）同一条纪律：**独立访问器，
不动既有聚合访问器的签名**。故本 change 的规格 delta **只动 `llm-provider`**。

## 与既有条款的关系

| 既有条款 | 本 change |
|---|---|
| 「流式增量携带终止原因」（change 0170） | **不冲突**：同型扩展（增量块多一个可选字段），解析点由 `choice` 侧扩到 `part` 顶层；`finish_reason` 语义逐字不变 |
| 非流式 `LLMResponse.usage` 解析 | **逐字保留**（规格明文） |
| `loop_limits()` 二元组 arity | **不动**（新独立访问器） |
| 预算闸门（`prompt_tokens` 为下界） | **不动**：抬升只使下界更准，闸门语义不变 |
| 输出预留的记账角色 | **加强**：从假设变为端点上界（同一量） |

## 不变量

- **I1** `LLMChunk.usage` 缺省 `None`；未携带用量时**恒** `None`，无零值捏造。
- **I2** `choices` 为空的末块**仍**产出用量块；`content=""` 与既有逐字一致（事件面零变化）。
- **I3** 非流式请求体**无** `stream_options`；流式请求体**恒有** `include_usage: true`。
- **I4** 非流式 `LLMResponse.usage` 与非流式请求形状**逐字不变**。
- **I5** `max_tokens` 注入 `None` 或 `≤ 0` ⇒ 请求 `max_tokens=None` ⇒ body 无该键（逐字不变）。
- **I6** `_last_prompt_tokens` 只被 `max` **抬升**、从不被压低；`completion_tokens` 不入判定。
- **I7** 无新第三方依赖；无 import 方向变化；`exclude_source_prefixes=("beast.","pet")` 逐字不动。

## 测试设计

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_chunk_maps_usage_from_empty_choices_end_block` | 末块 `choices=[]` + `usage` ⇒ `LLMChunk.usage == TokenUsage(120, 34)`、`content == ""` |
| 2 | `test_chunk_usage_none_when_absent` | 无 `usage` 键 / `usage: null` ⇒ `usage is None`；其余字段解析逐字一致 |
| 3 | `test_stream_body_requests_include_usage` | 流式 body 有 `stream=true` 与 `stream_options={"include_usage": True}` |
| 4 | `test_body_omits_stream_options_when_non_streaming` | 非流式 body 无 `stream_options` 键 |
| 5 | `test_planner_stream_raises_prompt_floor_from_usage` | 估算 `E` < 实报 `P` ⇒ `last_prompt_tokens() == P`；实报缺失 ⇒ `== E` |
| 6 | `test_planner_records_completion_tokens` | 末块用量 ⇒ `last_completion_tokens()` 为该值；未上报 ⇒ `0` |
| 7 | `test_planner_injects_max_tokens` / `test_planner_omits_max_tokens_when_non_positive` | 注入 `8192` ⇒ 请求 `max_tokens == 8192`；`None` / `0` / `-1` ⇒ `None` |
| 8 | `test_runtime_injects_output_reserve_as_max_tokens` | 组合根接线：`config` 缺省 ⇒ planner 下发 `8192` |

基线 **2163**；本 change 预计 **+8 ~ +12**。
