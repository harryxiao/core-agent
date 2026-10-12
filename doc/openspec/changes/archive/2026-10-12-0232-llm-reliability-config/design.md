# Design 0232: LLM 调用超时 / 重试可配置

## 背景与根因

`StdlibLLMProvider.__init__` 的 `timeout` / `max_retries` 构造参**早已存在**，但无配置键、组合根未传
⇒ 恒取实现类缺省（`60.0` / `3`）。2026-10-12 实跑：一轮轮末 maintenance 记忆调用打到 `glm-5.3`
超时 ⇒ **4 次串行 60s ≈ 232s**，期间 TUI 表现为卡死。该调用走的正是**主 provider**。

## 决策

- **D1 新增两个可调控点，单一真源仍是 ConfigSpec**：`llm.timeout`（`default=60.0`）、
  `llm.max_retries`（`default=3`），`exposure=ADVANCED`、`map_to` 同名 ⇒ 三面自动生成。
- **D2 校验期阻断，不静默强转**：两个镜像 `_llm_context_window` 的解析器（结构化段 ⇒ 构建前
  `raise ConfigurationError`）。`timeout` 须 `> 0` 数值、`max_retries` 须 `≥ 0` 整数
  （`bool` / 小数 / 负数 / 非数值一律拒）。
- **D3 缺省 = 实现类缺省 ⇒ 行为零改变**：dataclass / ConfigSpec / 解析器回落三处同为 `60.0` / `3`。
- **D4 两处 `LLMConfig` 构造点同步**：`_build_config` 与 `apply_change` **都**接线 ——
  只改一处会让 `config set llm.timeout` 看似生效、实际被静默丢弃。
- **D5「重试进度可见」不属本 change**：跨 4 层 + 新增接口契约 + 改 `astream` 并发 ⇒ 另立。
- **D6 `embed_provider` / `JEVProvider` 不接同名键**；`llm.fallback_models` / `llm.backoff` /
  `constraints.retry_attempts` 亦不新增。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/configuration/models.py` | `LLMConfig` 加 `timeout: float = 60.0`、`max_retries: int = 3` |
| `src/core/configuration/manager.py` | `_CONFIG_SPECS` ＋2；`_build_config` / `apply_change` 两处接线；新增 `_llm_timeout` / `_llm_max_retries` |
| `src/core/runtime.py` | 主 `StdlibLLMProvider` 加 `timeout=app.llm.timeout, max_retries=app.llm.max_retries` |
| 测试 | 新 `tests/test_llm_reliability_config.py`（17）；`test_rag_wiring.py` / `test_phase13.py` 桩补两参 |

## 反证（实测）

- **(A)** 拆 `runtime.py` 两行传参 ⇒ **1 红**（接线用例）。
- **(B1)** 两处 ConfigSpec `default` → `0.0` / `0` ⇒ **1 红**（spec 声明用例）。
- **(B2)** 两解析器回落值 → `1.0` / `9` ⇒ **2 红**（缺省不变用例）。
- **(B0)** dataclass 缺省 → `0.0` / `0` ⇒ **17 全绿** —— 配置路径上管理器恒经解析器显式注入，
  dataclass 缺省**不可观测**（见局限①）；该组不采用。
- 复原 ⇒ 三文件 `md5sum` 逐字节相同。

## 局限

① dataclass 缺省在配置路径上不可观测（真实锚点 = ConfigSpec default ＋ 解析器回落）；
② 不改 provider 层重试语义（退避 / 降级 / `fallback_models` 不动）；
③ 不给 `embed_provider` / `JEVProvider` 接线；④ 不做「重试进度可见」；
⑤ `constraints.retry_attempts` 未动（不同轴）。
