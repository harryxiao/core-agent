# Proposal 0232: LLM 调用超时 / 重试可配置

## Why

2026-10-12 用户实跑 core-agent TUI 时，一轮末尾的 maintenance 记忆调用打到 `glm-5.3` **超时**，
经 provider 缺省 `timeout=60.0, max_retries=3` ⇒ **4 次串行 60s 尝试（≈232s）**，期间 UI 表现为
「卡死」（表象收尾问题由 change `0231` 治理；**长等待本身**是本 change 的对象）。

根因：`StdlibLLMProvider` 的构造参 `timeout` / `max_retries` **早已存在**，但：
- **无配置键** —— `_CONFIG_SPECS` 无 `llm.timeout` / `llm.max_retries`；
- **组合根未传** —— `runtime.py` 构造主 provider 时只传 `api_key / base_url / model / provider`。

⇒ 恒取实现类缺省，操作者**无法**收窄「单次调用等待上限」。而该 maintenance / 摘要调用走的正是
**主 provider**（`_llm_text` → `llm.completion`），故这两个键**直接**为本次卡死时长设上限。

## What Changes

1. `LLMConfig` 增 `timeout: float = 60.0`、`max_retries: int = 3`（**缺省 = provider 类缺省**）。
2. `_CONFIG_SPECS` 增 `llm.timeout`（`default=60.0`）与 `llm.max_retries`（`default=3`），均
   `exposure=ADVANCED`、`map_to` 同名 ⇒ CLI / env / yaml 三面由单一真源生成。
3. `_build_config` 接线两键；新增两个**镜像 `_llm_context_window`** 的解析器（校验期当场
   `raise ConfigurationError`）：`timeout` 须 `> 0`、`max_retries` 须 `≥ 0` 的整数（布尔非法）。
4. 组合根 `runtime.py` 把两值注入主 `StdlibLLMProvider`。

**缺省零行为改变**：`LLMConfig` 缺省 = provider 类缺省（`60.0` / `3`）⇒ 未配置时组合根传入值与
原先逐字相同。

明确不做：`embed_provider` / `JEVProvider` 的同名键（各自独立语义，留默认）；`llm.fallback_models`
（备用模型降级仍不可经配置启用）；`llm.backoff`；`constraints.retry_attempts`（属容错中间件，另一轴）；
「重试进度可见」（新事件面 + `astream` 并发改造，另立 change）。

## Impact

- **影响规格**：`doc/openspec/specs/configuration/spec.md`（「LLM 提供商配置（必选）」MODIFIED ＋
  2 Scenario）、`doc/openspec/specs/llm-provider/spec.md`（「模型调用可靠性」MODIFIED ＋ 1 Scenario）。
- **影响代码**：`src/core/configuration/models.py`、`src/core/configuration/manager.py`、
  `src/core/runtime.py`。
- **兼容性**：未配置 ⇒ 行为逐字不变；新增两键为**可调控点**（非 kill-switch）。
- **测试**：三面声明、缺省不变、非法阻断（`timeout∈{0,-1,"abc",true}` / `max_retries∈{-1,1.5,true}`）、
  接线（配置 30 / 1 ⇒ provider 收到 30.0 / 1）。
