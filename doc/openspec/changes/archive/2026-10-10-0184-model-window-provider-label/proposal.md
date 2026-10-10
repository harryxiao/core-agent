# 变更提案 — 已知模型窗口表与 provider 审计标签（change 0184）

## 为什么

`known-risk.md` §1 **E97** 余项之二（与 change `0183` 同源，同一批用户裁决「E97 余项 = 全做」）：

- **无模型 → 窗口映射。** `llm.context_window` 未配置（缺省 `0`）时，`loop_limits()`
  （`src/core/configuration/manager.py:506-509`）**直接回落常量 `65536`** ⇒ 不论跑的是
  `gpt-4o`（128k）还是 `claude-*`（200k），token 预算恒为 `65536 − 8192`。用户不显式配
  `context_window` 就永远拿不到模型真实窗口 ⇒ 预算闸门**偏早**（保守，但白白浪费窗口），
  且与「模型换了、窗口随之变」的直觉不符。
- **provider 审计标签是死标签。** `LLMResponse.provider` 在 `_map_response`
  （`src/core/llm_provider/stdlib_provider.py:257`）**硬编码 `"stdlib"`**；`StdlibLLMProvider`
  构造（`src/core/runtime.py:314-318`）**不传** provider ⇒ 即便配置面写 `llm.provider: litellm`
  （配置项本身**必填**，`manager.py:369-374` 校验非空），响应上的审计标签仍是 `"stdlib"`。
  规格「模型调用审计」要求「标注 provider / model 与调用结果」⇒ **标注与实际不符**。

## 改什么

| 面 | 变更 |
|---|---|
| 新模块 `configuration/model_windows.py` | `_KNOWN_CONTEXT_WINDOWS`（模型名子串 → 窗口，**小而有据**）+ `known_window(model) -> int`（未命中返回 `0`） |
| `configuration/manager.py` | `loop_limits()` 窗口来源改为「显式 `context_window` **优先**，否则表推导，否则缺省 `65536`」 |
| `llm_provider/stdlib_provider.py` | `StdlibLLMProvider(provider=…)` 构造参数（缺省 `"stdlib"`）；`_map_response` 用实例值标注 |
| `runtime.py` | `StdlibLLMProvider(..., provider=app.llm.provider)` |
| 规格 | `configuration` **MODIFIED**「LLM 提供商配置（必选）」（窗口来源优先级 + 表纪律）+ 3 Scenario；`llm-provider` **MODIFIED**「模型调用审计」（标签真实性）+ 1 Scenario |
| 测试 | 表命中 / 未命中回落 / 显式优先（回归）/ provider 标签反映配置值（+ 缺省回落） |

## 影响

- **行为变更（有意）**：未配置 `context_window` 且模型在表内 ⇒ token 预算**变大**（更接近真实窗口）。
  下表外的模型**逐字不变**（仍 `65536`）；显式配置 `context_window` 的用户**逐字不变**（显式值优先）。
- **行为变更（有意）**：`LLMResponse.provider` 反映 `llm.provider` 配置值。未注入 provider 的构造点
  （测试替身 / 第三方直接构造）**逐字不变**（仍 `"stdlib"`）。
- 无新增第三方依赖；无配置键新增（表是常量，不是配置面）；无 import 方向变化；
  `exclude_source_prefixes=("beast.","pet")` **逐字不动**。
